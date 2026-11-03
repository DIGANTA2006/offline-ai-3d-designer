"""
CuraEngine wrapper for slicing STL files to G-code.
"""

import os
import subprocess
import tempfile
import shutil
import json
import math
import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path


@dataclass
class SliceSettings:
    """Settings for slicing."""
    layer_height: float = 0.2
    wall_thickness: float = 1.2
    infill_density: float = 20.0
    support_enabled: bool = False
    support_pattern: str = "grid"
    support_angle: float = 45.0
    adhesion_type: str = "brim"
    print_speed: float = 50.0
    nozzle_temp: float = 200.0
    bed_temp: float = 60.0
    infill_pattern: str = "grid"
    initial_layer_height: float = 0.2
    initial_layer_speed: float = 20.0
    travel_speed: float = 150.0
    retraction_enable: bool = True
    retraction_distance: float = 5.0
    retraction_speed: float = 40.0
    # Printer profile overrides
    machine_width: float = 220.0
    machine_depth: float = 220.0
    machine_height: float = 250.0
    machine_nozzle_size: float = 0.4
    material_diameter: float = 1.75
    # Alias for nozzle_diameter
    nozzle_diameter: float = 0.4

    def __post_init__(self):
        # Support nozzle_diameter as alias for machine_nozzle_size
        if hasattr(self, 'nozzle_diameter') and self.nozzle_diameter != 0.4:
            self.machine_nozzle_size = self.nozzle_diameter

    def validate(self) -> List[str]:
        """Validate slice settings and return list of errors."""
        errors = []
        if self.layer_height <= 0:
            errors.append("layer_height must be positive")
        if self.infill_density < 0 or self.infill_density > 100:
            errors.append("infill_density must be between 0 and 100")
        if self.machine_nozzle_size <= 0 or not isinstance(self.machine_nozzle_size, (int, float)) or self.machine_nozzle_size != self.machine_nozzle_size:  # NaN check
            errors.append("nozzle_diameter must be a positive finite number")
        if self.wall_thickness <= 0:
            errors.append("wall_thickness must be positive")
        if self.print_speed <= 0:
            errors.append("print_speed must be positive")
        if self.travel_speed <= 0:
            errors.append("travel_speed must be positive")
        if self.initial_layer_height <= 0:
            errors.append("initial_layer_height must be positive")
        if self.initial_layer_speed <= 0:
            errors.append("initial_layer_speed must be positive")
        if self.retraction_distance < 0:
            errors.append("retraction_distance must be non-negative")
        if self.retraction_speed <= 0:
            errors.append("retraction_speed must be positive")
        if self.support_angle < 0 or self.support_angle > 90:
            errors.append("support_angle must be between 0 and 90")
        if self.machine_width <= 0 or self.machine_depth <= 0 or self.machine_height <= 0:
            errors.append("machine dimensions must be positive")
        if self.material_diameter <= 0:
            errors.append("material_diameter must be positive")
        return errors

    def validation_errors(self) -> List[str]:
        """Alias for validate() for backward compatibility."""
        return self.validate()

    @classmethod
    def from_preset(cls, preset: str) -> "SliceSettings":
        """Create SliceSettings from a named preset."""
        presets = {
            "Quick": cls(
                layer_height=0.3,
                wall_thickness=0.8,
                infill_density=10.0,
                support_enabled=False,
                print_speed=60.0,
                initial_layer_height=0.3,
                initial_layer_speed=25.0,
            ),
            "Balanced": cls(
                layer_height=0.2,
                wall_thickness=1.2,
                infill_density=20.0,
                support_enabled=False,
                print_speed=50.0,
                initial_layer_height=0.2,
                initial_layer_speed=20.0,
            ),
            "Strong": cls(
                layer_height=0.15,
                wall_thickness=1.6,
                infill_density=40.0,
                support_enabled=True,
                support_pattern="grid",
                support_angle=45.0,
                print_speed=40.0,
                initial_layer_height=0.2,
                initial_layer_speed=15.0,
            ),
        }
        if preset not in presets:
            raise ValueError(f"Unknown preset: {preset}. Available: {list(presets.keys())}")
        return presets[preset]


@dataclass
class SliceResult:
    """Result of a slicing operation."""
    success: bool
    gcode_path: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    print_time: Optional[float] = None
    filament_used: Optional[float] = None  # grams
    filament_length_m: Optional[float] = None  # meters
    layers: Optional[int] = None
    filament_weight_estimated: bool = False
    filament_length_source: Optional[str] = None
    extrusion_length_mm: Optional[float] = None
    deposition_moves: int = 0


class Slicer:
    """Wrapper around CuraEngine for slicing STL files."""
    
    def __init__(self, cura_engine_path: Optional[str] = None):
        self.cura_engine_path = cura_engine_path or self._find_cura_engine()
        self._definitions_dir = self._find_definitions_dir()
        self._printer_def_path, self._extruder_def_path = self._resolve_definition_paths()
        self.cura_available = self.cura_engine_path is not None
    
    def _find_cura_engine(self) -> Optional[str]:
        """Find CuraEngine executable."""
        # Check common locations
        candidates = [
            "CuraEngine",
            "/usr/bin/CuraEngine",
            "/usr/local/bin/CuraEngine",
            "CuraEngine.exe",
            r"C:\Program Files\Ultimaker Cura 5.x\CuraEngine.exe",
        ]
        
        for candidate in candidates:
            if shutil.which(candidate):
                return candidate
            if os.path.isfile(candidate):
                return candidate
        
        return None  # Not found
    
    def _find_definitions_dir(self) -> Optional[str]:
        """Find Cura definitions directory."""
        # Check bundled definitions first (repo's python-backend/cura_resources/definitions)
        bundled = Path(__file__).parent.parent.parent.parent / "python-backend" / "cura_resources" / "definitions"
        if bundled.exists() and bundled.is_dir():
            return str(bundled)
        
        # Check environment variable
        env_defs = os.environ.get("CURA_DEFINITIONS_DIR")
        if env_defs and Path(env_defs).exists():
            return env_defs
        
        # Check common Cura installation paths
        common_paths = [
            Path("/usr/share/cura/resources/definitions"),
            Path("/usr/local/share/cura/resources/definitions"),
            Path.home() / ".local/share/cura/definitions",
            Path("C:/Program Files/Ultimaker Cura 5.x/resources/definitions"),
            Path("C:/Program Files/Ultimaker Cura 5.x/resources/definitions"),
        ]
        
        for path in common_paths:
            if path.exists() and path.is_dir():
                return str(path)
        
        return None
    
    def _resolve_definition_paths(self) -> tuple[Optional[str], Optional[str]]:
        """
        Resolve printer and extruder definition paths.
        Priority: CURA_PRINTER_DEFINITION env var > bundled definitions > definitions_dir
        """
        # Check CURA_PRINTER_DEFINITION env var (format: "printer_path;extruder_path" or just "printer_path")
        cura_printer_def = os.environ.get("CURA_PRINTER_DEFINITION", "").strip()
        if cura_printer_def:
            parts = [p.strip() for p in cura_printer_def.split(";") if p.strip()]
            if len(parts) >= 2:
                printer_path = parts[0]
                extruder_path = parts[1]
                if Path(printer_path).exists() and Path(extruder_path).exists():
                    return printer_path, extruder_path
            elif len(parts) == 1:
                printer_path = parts[0]
                if Path(printer_path).exists():
                    # Try to find matching extruder in same directory
                    printer_dir = Path(printer_path).parent
                    extruder_path = printer_dir / "generic_fdm_extruder.def.json"
                    if extruder_path.exists():
                        return printer_path, str(extruder_path)
        
        # Fall back to bundled definitions in definitions_dir
        if self._definitions_dir:
            printer_def = Path(self._definitions_dir) / "generic_fdm_printer.def.json"
            extruder_def = Path(self._definitions_dir) / "generic_fdm_extruder.def.json"
            if printer_def.exists() and extruder_def.exists():
                return str(printer_def), str(extruder_def)
        
        return None, None
    
    def slice(
        self,
        stl_path: str,
        output_path: str,
        settings: Optional[SliceSettings] = None,
        timeout_seconds: float = 60.0,
    ) -> SliceResult:
        """
        Slice an STL file to G-code using CuraEngine.
        
        Args:
            stl_path: Path to input STL file
            output_path: Path for output G-code file
            settings: SliceSettings object with slicing parameters
            timeout_seconds: Maximum time to wait for slicing
            
        Returns:
            SliceResult with success status and metadata
        """
        if settings is None:
            settings = SliceSettings()

        settings_errors = settings.validate()
        if settings_errors:
            return SliceResult(
                success=False,
                errors=["Invalid slicing settings: " + "; ".join(settings_errors)],
            )

        errors = []
        warnings = []
        
        # Validate input file
        if not os.path.isfile(stl_path):
            return SliceResult(success=False, errors=[f"Input STL not found: {stl_path}"])
        
        if os.path.getsize(stl_path) == 0:
            return SliceResult(success=False, errors=["Input STL is empty"])
        
        # Validate output path is different from input
        if os.path.abspath(stl_path) == os.path.abspath(output_path):
            return SliceResult(success=False, errors=["Output G-code path must be different from the source STL"])
        
        # Ensure output directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Check CuraEngine availability
        if not self.cura_engine_path:
            errors.append("CuraEngine was not found. No placeholder G-code was generated.")
            return SliceResult(success=False, errors=errors)
        
        # Build CuraEngine command
        cmd = self._build_command(stl_path, output_path, settings)
        
        try:
            # Run CuraEngine
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            
            if result.returncode != 0:
                stderr = result.stderr.strip() if result.stderr else "Unknown error"
                errors.append(f"CuraEngine failed (exit {result.returncode}): {stderr}")
                return SliceResult(success=False, errors=errors)
            
            # Verify output file
            if not os.path.isfile(output_path):
                errors.append("CuraEngine did not produce output G-code file")
                return SliceResult(success=False, errors=errors)
            
            if os.path.getsize(output_path) == 0:
                errors.append("CuraEngine produced empty G-code file")
                return SliceResult(success=False, errors=errors)

            # A zero-exit process is not sufficient: reject malformed or placeholder output.
            gcode_validation = self.validate_gcode(output_path)
            if not gcode_validation["valid"]:
                try:
                    os.remove(output_path)
                except OSError:
                    pass
                errors.append(
                    "CuraEngine output failed structural validation: "
                    + str(gcode_validation["error"] or "unknown G-code validation error")
                )
                return SliceResult(success=False, errors=errors)

            # Parse G-code for metadata only after the structural check passes.
            metadata = self._parse_gcode_metadata(output_path)
            extrusion_length_mm = float(gcode_validation["stats"]["extrusion_length_mm"])
            if extrusion_length_mm > 0:
                metadata["filament_length_m"] = extrusion_length_mm / 1000.0
                metadata["filament_length_source"] = "gcode_e_axis"

            return SliceResult(
                success=True,
                gcode_path=output_path,
                warnings=warnings,
                print_time=metadata.get("print_time"),
                filament_used=metadata.get("filament_used"),
                filament_length_m=metadata.get("filament_length_m"),
                layers=metadata.get("layers"),
                filament_weight_estimated=metadata.get("filament_weight_estimated", False),
                filament_length_source=metadata.get("filament_length_source"),
                extrusion_length_mm=gcode_validation["stats"]["extrusion_length_mm"],
                deposition_moves=gcode_validation["stats"]["deposition_moves"],
            )
            
        except subprocess.TimeoutExpired:
            errors.append(f"Slicing timed out after {timeout_seconds} seconds")
            return SliceResult(success=False, errors=errors)
        except FileNotFoundError:
            errors.append("CuraEngine was not found. No placeholder G-code was generated.")
            return SliceResult(success=False, errors=errors)
        except Exception as e:
            errors.append(f"Slicing failed: {str(e)}")
            return SliceResult(success=False, errors=errors)
    
    def _build_command(
        self,
        stl_path: str,
        output_path: str,
        settings: SliceSettings,
    ) -> List[str]:
        """Build CuraEngine command line."""
        cmd = [self.cura_engine_path, "slice"]
        
        # CuraEngine needs the inherited base definitions loaded as well as
        # the project's generic child profiles. Parent definitions must be
        # available before the children that refer to them by ID.
        if self._definitions_dir:
            base_printer = Path(self._definitions_dir) / "fdmprinter.def.json"
            base_extruder = Path(self._definitions_dir) / "fdmextruder.def.json"
            for definition in (base_printer, base_extruder):
                if definition.is_file():
                    cmd.extend(["-j", str(definition)])

        if self._printer_def_path:
            cmd.extend(["-j", self._printer_def_path])
        if self._extruder_def_path:
            cmd.extend(["-j", self._extruder_def_path])
        
        # Add STL input
        cmd.extend(["-l", stl_path])
        
        # Add output
        cmd.extend(["-o", output_path])
        
        # Add settings
        cmd.extend(self._settings_to_args(settings))
        
        return cmd
    
    def _settings_to_args(self, settings: SliceSettings) -> List[str]:
        """Convert SliceSettings to CuraEngine command arguments."""
        args = []
        
        # Layer settings
        args.extend(["-s", f"layer_height={settings.layer_height}"])
        args.extend(["-s", f"initial_layer_height={settings.initial_layer_height}"])
        args.extend(["-s", f"wall_thickness={settings.wall_thickness}"])
        args.extend(["-s", f"infill_sparse_density={settings.infill_density}"])
        args.extend(["-s", f"infill_pattern={settings.infill_pattern}"])
        
        # Speed settings
        args.extend(["-s", f"speed_print={settings.print_speed}"])
        args.extend(["-s", f"speed_travel={settings.travel_speed}"])
        args.extend(["-s", f"speed_initial_layer={settings.initial_layer_speed}"])
        
        # Temperature settings
        args.extend(["-s", f"material_print_temperature={settings.nozzle_temp}"])
        args.extend(["-s", f"material_bed_temperature={settings.bed_temp}"])
        
        # Support settings
        args.extend(["-s", f"support_enable={str(settings.support_enabled).lower()}"])
        if settings.support_enabled:
            args.extend(["-s", f"support_pattern={settings.support_pattern}"])
            args.extend(["-s", f"support_angle={settings.support_angle}"])
        
        # Adhesion
        args.extend(["-s", f"adhesion_type={settings.adhesion_type}"])
        
        # Retraction
        args.extend(["-s", f"retraction_enable={str(settings.retraction_enable).lower()}"])
        if settings.retraction_enable:
            args.extend(["-s", f"retraction_amount={settings.retraction_distance}"])
            args.extend(["-s", f"retraction_speed={settings.retraction_speed}"])
        
        # Machine settings
        args.extend(["-s", f"machine_width={settings.machine_width}"])
        args.extend(["-s", f"machine_depth={settings.machine_depth}"])
        args.extend(["-s", f"machine_height={settings.machine_height}"])
        args.extend(["-s", f"machine_nozzle_size={settings.machine_nozzle_size}"])
        args.extend(["-s", f"material_diameter={settings.material_diameter}"])
        
        return args
    
    def _parse_gcode_metadata(self, gcode_path: str) -> Dict[str, Any]:
        """Parse G-code for print time, filament usage, and layer count."""
        metadata = {
            "print_time": None,
            "filament_used": None,
            "filament_length_m": None,
            "layers": None,
            "filament_weight_estimated": False,
        }
        
        try:
            with open(gcode_path, "r") as f:
                for line in f:
                    line = line.strip()
                    
                    # CuraEngine comments with metadata
                    if line.startswith(";TIME:"):
                        try:
                            metadata["print_time"] = float(line[6:])
                        except ValueError:
                            pass
                    elif line.startswith(";Filament used:"):
                        # Format: ;Filament used: 12.34m, 5.67g OR ;Filament used: 5000mm, 15.5g
                        try:
                            parts = line[15:].split(",")
                            for part in parts:
                                part = part.strip()
                                if part.endswith("mm"):
                                    length_m = float(part[:-2]) / 1000.0
                                    if length_m > 0:
                                        metadata["filament_length_m"] = length_m
                                        metadata["filament_length_source"] = "cura_metadata"
                                elif part.endswith("m"):
                                    length_m = float(part[:-1])
                                    if length_m > 0:
                                        metadata["filament_length_m"] = length_m
                                        metadata["filament_length_source"] = "cura_metadata"
                                elif part.endswith("g"):
                                    grams = float(part[:-1])
                                    if grams > 0:
                                        metadata["filament_used"] = grams
                                        metadata["filament_weight_estimated"] = True
                        except ValueError:
                            pass
                    elif line.startswith(";LAYER_COUNT:"):
                        try:
                            metadata["layers"] = int(line[13:])
                        except ValueError:
                            pass
                    elif line.startswith(";LAYER:"):
                        # Only count LAYER if LAYER_COUNT not present
                        if metadata["layers"] is None:
                            metadata["layers"] = 0
                            metadata["layers"] += 1
                        
        except Exception:
            pass  # Metadata parsing is best-effort
        
        return metadata

    @staticmethod
    def _analyze_gcode_extrusion(content: str) -> Dict[str, Any]:
        """Measure positive filament extrusion from G-code E-axis movement.

        M82/M83 select absolute/relative extrusion. G92 resets an absolute
        coordinate without consuming filament. M200 volumetric E values are
        converted back to filament length when a filament diameter is supplied.
        A positive E coordinate by itself is not proof of extrusion: the
        validator separately requires at least one positive E move coordinated
        with an XYZ move.
        """
        absolute_e = True
        e_mode_explicit = False
        volumetric_diameter_mm: Optional[float] = None
        active_tool = 0
        e_positions: Dict[int, float] = {}
        total_extrusion_mm = 0.0
        deposition_extrusion_mm = 0.0
        positive_extrusion_moves = 0
        deposition_moves = 0

        for raw_line in content.splitlines():
            # Remove semicolon and parenthetical comments before parsing words.
            code = raw_line.split(";", 1)[0]
            code = re.sub(r"\([^)]*\)", "", code).strip().upper()
            if not code:
                continue
            code = re.sub(r"^N\d+\s*", "", code)
            command_match = re.match(r"^(G\d+|M\d+|T\d+)", code)
            if not command_match:
                continue

            command = command_match.group(1)
            arguments = code[command_match.end():]
            words: Dict[str, float] = {}
            for letter, raw_value in re.findall(
                r"([A-Z])\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))",
                arguments,
            ):
                try:
                    words[letter] = float(raw_value)
                except ValueError:
                    continue

            if command == "M82":
                absolute_e = True
                e_mode_explicit = True
                continue
            if command == "M83":
                absolute_e = False
                e_mode_explicit = True
                continue
            # On common Marlin/RepRap profiles G90/G91 also select E mode
            # until an explicit M82/M83 overrides it.
            if command == "G90" and not e_mode_explicit:
                absolute_e = True
                continue
            if command == "G91" and not e_mode_explicit:
                absolute_e = False
                continue
            if command == "M200":
                diameter = words.get("D")
                volumetric_diameter_mm = diameter if diameter and diameter > 0 else None
                continue
            if command.startswith("T"):
                try:
                    active_tool = int(command[1:])
                except ValueError:
                    continue
                continue
            if command == "G92":
                if "E" in words:
                    e_positions[active_tool] = words["E"]
                continue
            if command not in {"G0", "G1", "G2", "G3"} or "E" not in words:
                continue

            e_value = words["E"]
            if absolute_e:
                previous_e = e_positions.get(active_tool, 0.0)
                delta_e = e_value - previous_e
                e_positions[active_tool] = e_value
            else:
                delta_e = e_value
                e_positions[active_tool] = e_positions.get(active_tool, 0.0) + e_value

            if delta_e <= 1e-6:
                continue

            if volumetric_diameter_mm:
                filament_area_mm2 = math.pi * (volumetric_diameter_mm / 2.0) ** 2
                filament_length_mm = delta_e / filament_area_mm2
            else:
                filament_length_mm = delta_e

            if not math.isfinite(filament_length_mm) or filament_length_mm <= 0:
                continue

            total_extrusion_mm += filament_length_mm
            positive_extrusion_moves += 1
            if any(axis in words for axis in ("X", "Y", "Z")):
                deposition_extrusion_mm += filament_length_mm
                deposition_moves += 1

        return {
            "extrusion_length_mm": total_extrusion_mm,
            "deposition_extrusion_mm": deposition_extrusion_mm,
            "positive_extrusion_moves": positive_extrusion_moves,
            "deposition_moves": deposition_moves,
            "e_mode": "absolute" if absolute_e else "relative",
            "volumetric_extrusion": volumetric_diameter_mm is not None,
        }

    def validate_gcode(self, gcode_path: str) -> Dict[str, Any]:
        """Validate G-code structure and require real positive extrusion moves."""
        result = {
            "valid": False,
            "error": None,
            "stats": {
                "has_home": False,
                "has_extrusion": False,
                "layers": 0,
                "has_temp": False,
                "max_x": 0.0,
                "max_y": 0.0,
                "extrusion_length_mm": 0.0,
                "deposition_extrusion_mm": 0.0,
                "positive_extrusion_moves": 0,
                "deposition_moves": 0,
                "e_mode": "absolute",
                "volumetric_extrusion": False,
            },
        }

        try:
            with open(gcode_path, "r", encoding="utf-8", errors="replace") as handle:
                content = handle.read()
        except Exception as exc:
            result["error"] = f"Failed to read G-code file: {exc}"
            return result

        if "PREVIEW only" in content or "preview only" in content.lower():
            result["error"] = "Placeholder/preview-only G-code detected"
            return result

        layer_count = 0
        has_home = False
        has_temp = False
        max_x = 0.0
        max_y = 0.0
        last_z: Optional[float] = None
        z_layer_threshold = 0.01
        has_layer_count = False
        has_layer_markers = False

        for raw_line in content.splitlines():
            code = raw_line.split(";", 1)[0].strip()
            if not code:
                stripped = raw_line.strip()
                if stripped.startswith(";LAYER_COUNT:"):
                    try:
                        layer_count = int(stripped[13:])
                        has_layer_count = True
                    except ValueError:
                        pass
                elif stripped.startswith(";LAYER:"):
                    has_layer_markers = True
                    if not has_layer_count:
                        layer_count += 1
                continue

            code = re.sub(r"^N\d+\s*", "", code).strip()
            if re.match(r"^G28\b", code):
                has_home = True
            if re.match(r"^M1(0[49]|4[09])\b", code):
                has_temp = True

            if re.match(r"^G[012]\b", code):
                for axis in ("X", "Y"):
                    match = re.search(rf"{axis}([+-]?(?:\d+(?:\.\d*)?|\.\d+))", code)
                    if match:
                        value = abs(float(match.group(1)))
                        if axis == "X":
                            max_x = max(max_x, value)
                        else:
                            max_y = max(max_y, value)

                z_match = re.search(r"Z([+-]?(?:\d+(?:\.\d*)?|\.\d+))", code)
                if z_match and not has_layer_count and not has_layer_markers:
                    z_value = float(z_match.group(1))
                    if last_z is not None and z_value > last_z + z_layer_threshold:
                        layer_count += 1
                    last_z = z_value

            stripped = raw_line.strip()
            if stripped.startswith(";LAYER_COUNT:"):
                try:
                    layer_count = int(stripped[13:])
                    has_layer_count = True
                except ValueError:
                    pass
            elif stripped.startswith(";LAYER:"):
                has_layer_markers = True
                if not has_layer_count:
                    layer_count += 1

        if not has_layer_count and not has_layer_markers and layer_count == 0 and last_z is not None and last_z > 0:
            layer_count = 1

        extrusion = self._analyze_gcode_extrusion(content)
        has_extrusion = extrusion["deposition_moves"] > 0 and extrusion["deposition_extrusion_mm"] > 0.01

        result["stats"].update({
            "has_home": has_home,
            "has_extrusion": has_extrusion,
            "has_temp": has_temp,
            "layers": layer_count,
            "max_x": max_x,
            "max_y": max_y,
            **extrusion,
        })

        if not has_home:
            result["error"] = "G-code missing required commands (homing G28)"
            return result
        if not has_extrusion:
            result["error"] = "G-code has no positive extrusion on a coordinated print move"
            return result
        if layer_count <= 0:
            result["error"] = "G-code has no layers"
            return result

        result["valid"] = True
        return result

    @staticmethod
    def _parse_cura_output(output: str) -> tuple:
        """Parse CuraEngine output for print time, filament grams, and layers."""
        print_time = None
        filament_grams = None
        layers = None
        
        # Parse TIME
        time_match = re.search(r';TIME:(\d+(?:\.\d+)?)', output)
        if time_match:
            print_time = float(time_match.group(1))
        
        # Parse LAYER_COUNT
        layer_match = re.search(r';LAYER_COUNT:(\d+)', output)
        if layer_match:
            layers = int(layer_match.group(1))
        
        # Parse Filament used (length in mm)
        filament_length_match = re.search(r';Filament used:\s*([\d.]+)mm', output)
        if filament_length_match:
            length_mm = float(filament_length_match.group(1))
            # Convert to meters
            pass  # We'll return length separately
        
        # Parse Filament weight
        filament_weight_match = re.search(r';Filament weight\s*=\s*([\d.]+)g', output)
        if filament_weight_match:
            filament_grams = float(filament_weight_match.group(1))
        
        # Also check for "Filament: X.XXm Y.YYg" format
        filament_summary_match = re.search(r'Filament:\s*([\d.]+)m\s*([\d.]+)g', output)
        if filament_summary_match:
            if filament_grams is None:
                filament_grams = float(filament_summary_match.group(2))
        
        # Parse print time in "Print time: Xm Ys" format
        time_summary_match = re.search(r'Print time:\s*(\d+)m\s*(\d+)s', output)
        if time_summary_match and print_time is None:
            print_time = int(time_summary_match.group(1)) * 60 + int(time_summary_match.group(2))
        
        return print_time, filament_grams, layers

    @staticmethod
    def _parse_filament_length_m(output: str) -> Optional[float]:
        """Parse filament length in meters from CuraEngine output."""
        # Check for "Filament used: X.XXmm" format
        match = re.search(r';Filament used:\s*([\d.]+)mm', output)
        if match:
            return float(match.group(1)) / 1000.0
        
        # Check for "Filament: X.XXm" format
        match = re.search(r'Filament:\s*([\d.]+)m', output)
        if match:
            return float(match.group(1))
        
        return None


def create_default_printer_definition(definitions_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a default printer definition for CuraEngine if none exists.
    Returns the path to the created definition file.
    """
    if definitions_dir is None:
        definitions_dir = Path(__file__).parent.parent.parent.parent / "python-backend" / "cura_resources" / "definitions"
    else:
        definitions_dir = Path(definitions_dir)
    
    definitions_dir.mkdir(parents=True, exist_ok=True)
    
    # Printer definition
    printer_def = {
        "version": 2,
        "name": "Generic FDM Printer 220x220x250",
        "inherits": "fdmprinter",
        "metadata": {
            "type": "machine",
            "author": "Offline AI 3D Designer",
            "manufacturer": "Generic",
            "category": "Other",
            "file_formats": "text/x-gcode",
            "visible": True,
            "has_materials": True,
            "machine_extruder_trains": {
                "0": "generic_fdm_extruder"
            }
        },
        "overrides": {
            "machine_name": {"default_value": "Generic FDM Printer 220x220x250"},
            "machine_width": {"default_value": 220},
            "machine_depth": {"default_value": 220},
            "machine_height": {"default_value": 250},
            "machine_center_is_zero": {"default_value": False},
            "machine_heated_bed": {"default_value": True},
            "machine_extruder_count": {"default_value": 1},
            "machine_gcode_flavor": {"default_value": "Marlin"},
            "machine_start_gcode": {"default_value": "G21\nG90\nM82\nG28\nG92 E0"},
            "machine_end_gcode": {"default_value": "M104 S0\nM140 S0\nG91\nG1 E-1 F300\nG1 Z+5 F3000\nG90\nM84"}
        }
    }
    
    # Extruder definition
    extruder_def = {
        "version": 2,
        "name": "Generic FDM Extruder 0.4mm",
        "inherits": "fdmextruder",
        "metadata": {
            "type": "extruder",
            "author": "Offline AI 3D Designer",
            "manufacturer": "Generic",
            "visible": False,
            "position": "0"
        },
        "overrides": {
            "machine_nozzle_size": {"default_value": 0.4},
            "material_diameter": {"default_value": 1.75},
            "material_print_temperature": {"default_value": 200},
            "material_print_temperature_layer_0": {"default_value": 205},
            "material_bed_temperature": {"default_value": 60},
            "material_bed_temperature_layer_0": {"default_value": 60},
            "retraction_enable": {"default_value": True},
            "retraction_amount": {"default_value": 5},
            "retraction_speed": {"default_value": 40}
        }
    }
    
    printer_path = definitions_dir / "generic_fdm_printer.def.json"
    extruder_path = definitions_dir / "generic_fdm_extruder.def.json"
    
    with open(printer_path, "w") as f:
        json.dump(printer_def, f, indent=2)
    
    with open(extruder_path, "w") as f:
        json.dump(extruder_def, f, indent=2)
    
    return {
        "printer": str(printer_path),
        "extruder": str(extruder_path),
    }


def get_slicing_capability() -> Dict[str, Any]:
    """Probe the installed CuraEngine using its supported CLI and bundled definitions.

    The actual printer/extruder profile load and STL-to-G-code path are exercised
    by the Docker build smoke test; this lightweight probe is safe for /health.
    """
    try:
        slicer = Slicer()
        engine_path = slicer.cura_engine_path
        if not engine_path:
            return {
                "available": False,
                "engine": None,
                "reason": "CuraEngine was not found on PATH or in a supported installation location.",
            }

        # CuraEngine 4.13 uses the 'help' subcommand; '--version' is not supported.
        result = subprocess.run(
            [engine_path, "help"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=10,
        )
        output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
        if result.returncode != 0 or "CuraEngine slice" not in output:
            detail = output[:500] or f"CLI exited with status {result.returncode}."
            return {
                "available": False,
                "engine": None,
                "reason": f"CuraEngine CLI probe failed: {detail}",
            }

        if not slicer._printer_def_path or not slicer._extruder_def_path:
            return {
                "available": False,
                "engine": "CuraEngine",
                "reason": (
                    "Cura printer/extruder definitions were not both resolved "
                    "(CURA_PRINTER_DEFINITION or bundled definitions)."
                ),
            }

        if not slicer._definitions_dir:
            return {
                "available": False,
                "engine": "CuraEngine",
                "reason": "Cura definitions directory was not found.",
            }

        base_definitions = (
            Path(slicer._definitions_dir) / "fdmprinter.def.json",
            Path(slicer._definitions_dir) / "fdmextruder.def.json",
        )
        for definition in base_definitions:
            if not definition.is_file():
                return {
                    "available": False,
                    "engine": "CuraEngine",
                    "reason": (
                        f"Required Cura base definition is missing: {definition.name}. "
                        "Install the pinned Cura 4.13 base definitions."
                    ),
                }
            try:
                with definition.open("r", encoding="utf-8") as handle:
                    parsed = json.load(handle)
            except (OSError, json.JSONDecodeError) as exc:
                return {
                    "available": False,
                    "engine": "CuraEngine",
                    "reason": f"Cura base definition is not valid JSON ({definition.name}): {exc}",
                }
            if not isinstance(parsed, dict) or not isinstance(parsed.get("settings"), dict) or parsed.get("inherits"):
                return {
                    "available": False,
                    "engine": "CuraEngine",
                    "reason": f"Cura base definition is incomplete: {definition.name}",
                }

        for definition_path in (slicer._printer_def_path, slicer._extruder_def_path):
            definition = Path(definition_path)
            if not definition.is_file():
                return {
                    "available": False,
                    "engine": "CuraEngine",
                    "reason": f"Cura definition file is missing: {definition.name}",
                }
            try:
                with definition.open("r", encoding="utf-8") as handle:
                    parsed = json.load(handle)
            except (OSError, json.JSONDecodeError) as exc:
                return {
                    "available": False,
                    "engine": "CuraEngine",
                    "reason": f"Cura definition is not valid JSON ({definition.name}): {exc}",
                }
            if not isinstance(parsed, dict) or not parsed.get("inherits"):
                return {
                    "available": False,
                    "engine": "CuraEngine",
                    "reason": f"Cura definition is missing required inheritance metadata: {definition.name}",
                }

        return {
            "available": True,
            "engine": "CuraEngine",
            "version": "CLI help verified; version string unavailable",
            "reason": None,
        }

    except FileNotFoundError:
        return {
            "available": False,
            "engine": None,
            "reason": "CuraEngine executable could not be started.",
        }
    except subprocess.TimeoutExpired:
        return {
            "available": False,
            "engine": None,
            "reason": "CuraEngine CLI probe timed out after 10 seconds.",
        }
    except Exception as exc:
        return {
            "available": False,
            "engine": None,
            "reason": f"Slicing capability check failed: {type(exc).__name__}: {exc}",
        }
