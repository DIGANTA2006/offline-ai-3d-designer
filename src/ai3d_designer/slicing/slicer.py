
"""
Slicing module for 3D printing. Produces G-code only through a configured CuraEngine.
"""
import os
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import trimesh

@dataclass
class SliceSettings:
    """3D printing slice settings."""
    # Printer
    printer_name: str = "Generic"
    bed_size_x: float = 220.0
    bed_size_y: float = 220.0
    bed_size_z: float = 250.0
    
    # Quality
    layer_height: float = 0.2
    initial_layer_height: float = 0.2
    wall_thickness: float = 1.2
    top_bottom_thickness: float = 0.8
    
    # Infill
    infill_density: float = 20.0
    infill_pattern: str = "grid"  # grid, lines, triangles, cubic, gyroid
    
    # Speed
    print_speed: float = 50.0
    infill_speed: float = 50.0
    wall_speed: float = 30.0
    travel_speed: float = 150.0
    initial_layer_speed: float = 20.0
    
    # Temperature
    nozzle_temp: float = 200.0
    bed_temp: float = 60.0
    initial_layer_bed_temp: float = 60.0
    
    # Material
    filament_diameter: float = 1.75
    flow_rate: float = 100.0
    
    # Adhesion
    adhesion_type: str = "brim"  # none, skirt, brim, raft
    brim_width: float = 8.0
    brim_line_count: int = 5
    
    # Support
    support_enabled: bool = False
    support_pattern: str = "zigzag"
    support_density: float = 15.0
    support_z_distance: float = 0.2
    support_xy_distance: float = 0.7
    
    # Retraction
    retraction_enabled: bool = True
    retraction_distance: float = 5.0
    retraction_speed: float = 40.0
    
    # Cooling
    fan_enabled: bool = True
    fan_speed: float = 100.0
    fan_speed_max: float = 100.0
    
    # Advanced
    enable_prime_tower: bool = False
    wipe_tower_enabled: bool = False
    
    def validation_errors(self) -> List[str]:
        """Validate machine and material settings before invoking a slicer."""
        errors: List[str] = []
        numeric = {
            "bed_size_x": self.bed_size_x,
            "bed_size_y": self.bed_size_y,
            "bed_size_z": self.bed_size_z,
            "layer_height": self.layer_height,
            "initial_layer_height": self.initial_layer_height,
            "wall_thickness": self.wall_thickness,
            "top_bottom_thickness": self.top_bottom_thickness,
            "infill_density": self.infill_density,
            "print_speed": self.print_speed,
            "infill_speed": self.infill_speed,
            "wall_speed": self.wall_speed,
            "travel_speed": self.travel_speed,
            "initial_layer_speed": self.initial_layer_speed,
            "nozzle_temp": self.nozzle_temp,
            "bed_temp": self.bed_temp,
            "initial_layer_bed_temp": self.initial_layer_bed_temp,
            "filament_diameter": self.filament_diameter,
            "flow_rate": self.flow_rate,
            "brim_width": self.brim_width,
            "support_density": self.support_density,
            "support_z_distance": self.support_z_distance,
            "support_xy_distance": self.support_xy_distance,
            "retraction_distance": self.retraction_distance,
            "retraction_speed": self.retraction_speed,
            "fan_speed": self.fan_speed,
            "fan_speed_max": self.fan_speed_max,
        }
        for key, value in numeric.items():
            if not math.isfinite(float(value)):
                errors.append(f"{key} must be a finite number.")

        for key in ("bed_size_x", "bed_size_y", "bed_size_z", "layer_height", "initial_layer_height",
                    "wall_thickness", "top_bottom_thickness", "print_speed", "infill_speed",
                    "wall_speed", "travel_speed", "initial_layer_speed", "filament_diameter",
                    "flow_rate", "retraction_speed"):
            if math.isfinite(float(numeric[key])) and numeric[key] <= 0:
                errors.append(f"{key} must be greater than zero.")

        for key in ("infill_density", "support_density", "fan_speed", "fan_speed_max"):
            if math.isfinite(float(numeric[key])) and not 0 <= numeric[key] <= 100:
                errors.append(f"{key} must be between 0 and 100 percent.")

        if math.isfinite(float(self.nozzle_temp)) and not 0 < self.nozzle_temp <= 400:
            errors.append("nozzle_temp must be between 0 and 400 °C.")
        for key in ("bed_temp", "initial_layer_bed_temp"):
            value = getattr(self, key)
            if math.isfinite(float(value)) and not 0 <= value <= 200:
                errors.append(f"{key} must be between 0 and 200 °C.")
        if self.adhesion_type not in {"none", "skirt", "brim", "raft"}:
            errors.append("adhesion_type must be none, skirt, brim, or raft.")
        if self.infill_pattern not in {"grid", "lines", "triangles", "cubic", "gyroid", "concentric", "zigzag", "cross", "trihexagon"}:
            errors.append("Unsupported infill_pattern.")
        if self.retraction_distance < 0 or self.support_z_distance < 0 or self.support_xy_distance < 0:
            errors.append("Retraction and support clearances cannot be negative.")
        if self.brim_width < 0 or self.brim_line_count < 0:
            errors.append("Brim dimensions cannot be negative.")
        return errors

    def to_cura_settings(self) -> Dict[str, Any]:
        """Return flat CuraEngine setting overrides, not a fabricated definitions file."""
        return {
            "layer_height": self.layer_height,
            "layer_height_0": self.initial_layer_height,
            "wall_thickness": self.wall_thickness,
            "top_bottom_thickness": self.top_bottom_thickness,
            "infill_sparse_density": self.infill_density,
            "infill_pattern": self.infill_pattern,
            "speed_print": self.print_speed,
            "speed_infill": self.infill_speed,
            "speed_wall": self.wall_speed,
            "speed_travel": self.travel_speed,
            "speed_layer_0": self.initial_layer_speed,
            "material_print_temperature": self.nozzle_temp,
            "material_bed_temperature": self.bed_temp,
            "material_bed_temperature_layer_0": self.initial_layer_bed_temp,
            "material_diameter": self.filament_diameter,
            "material_flow": self.flow_rate,
            "adhesion_type": self.adhesion_type,
            "brim_width": self.brim_width,
            "brim_line_count": self.brim_line_count,
            "support_enable": self.support_enabled,
            "support_pattern": self.support_pattern,
            "support_density": self.support_density,
            "support_z_distance": self.support_z_distance,
            "support_xy_distance": self.support_xy_distance,
            "retraction_enable": self.retraction_enabled,
            "retraction_amount": self.retraction_distance,
            "retraction_speed": self.retraction_speed,
            "cool_fan_enabled": self.fan_enabled,
            "cool_fan_speed": self.fan_speed,
            "cool_fan_speed_max": self.fan_speed_max,
        }


@dataclass
class SliceResult:
    """Result of slicing operation."""
    success: bool
    gcode_path: Optional[str] = None
    print_time: Optional[float] = None  # seconds
    filament_used: Optional[float] = None  # grams
    layers: Optional[int] = None
    warnings: List[str] = None
    errors: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
        if self.errors is None:
            self.errors = []


class Slicer:
    """3D printing slicer - uses CuraEngine if available, otherwise basic slicing."""
    
    def __init__(self, cura_engine_path: Optional[str] = None):
        """
        Initialize slicer.
        
        Args:
            cura_engine_path: Path to CuraEngine executable. If None, tries to find it.
        """
        self.cura_engine_path = cura_engine_path or self._find_cura_engine()
        self.cura_available = self.cura_engine_path is not None
        
        # Default settings
        self.settings = SliceSettings()
    
    def _find_cura_engine(self) -> Optional[str]:
        """Find a real CuraEngine executable by PATH or common installation path."""
        possible_paths = ["CuraEngine", "curaengine", "/usr/bin/CuraEngine", "/usr/local/bin/CuraEngine"]
        for root in (
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")),
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")),
        ):
            for company in ("UltiMaker Cura", "Ultimaker Cura", "Cura"):
                install_root = root / company
                if install_root.is_dir():
                    possible_paths.extend(str(item) for item in install_root.glob("*/CuraEngine.exe"))
                    possible_paths.extend(str(item) for item in install_root.glob("CuraEngine.exe"))

        for candidate in possible_paths:
            located = shutil.which(candidate)
            executable = located or candidate
            if not located and not Path(executable).is_file():
                continue
            try:
                result = subprocess.run([executable, "--version"], capture_output=True, timeout=5, check=False)
                if result.returncode == 0:
                    return executable
            except (OSError, subprocess.TimeoutExpired):
                continue
        return None

    def _find_cura_definitions_dir(self) -> Optional[Path]:
        """Locate Cura's installed machine/extruder definition resources."""
        search_dirs: List[Path] = []
        env_dirs = os.environ.get("CURA_ENGINE_SEARCH_PATH", "")
        search_dirs.extend(Path(part) for part in env_dirs.split(os.pathsep) if part.strip())

        engine = self.cura_engine_path
        if engine:
            resolved = shutil.which(engine) or engine
            try:
                parent = Path(resolved).resolve().parent
                search_dirs.extend([
                    parent / "resources" / "definitions",
                    parent / "share" / "cura" / "resources" / "definitions",
                    parent.parent / "share" / "cura" / "resources" / "definitions",
                    parent.parent / "resources" / "definitions",
                ])
            except OSError:
                pass

        search_dirs.extend([
            Path("/usr/share/cura/resources/definitions"),
            Path("/usr/local/share/cura/resources/definitions"),
            Path("/usr/share/cura-engine/resources/definitions"),
        ])
        for root in (Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")),
                     Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))):
            for company in ("UltiMaker Cura", "Ultimaker Cura"):
                install_root = root / company
                if install_root.is_dir():
                    search_dirs.extend(install_root.glob("*/share/cura/resources/definitions"))
                    search_dirs.extend(install_root.glob("*/resources/definitions"))

        for directory in search_dirs:
            if (directory / "fdmprinter.def.json").is_file() and (directory / "fdmextruder.def.json").is_file():
                return directory
        return None

    def slice(
        self,
        stl_path: str,
        output_path: str,
        settings: Optional[SliceSettings] = None,
        printer_definition: Optional[str] = None,
    ) -> SliceResult:
        """Slice a mesh with CuraEngine; never emit placeholder G-code as a successful result."""
        settings = settings or self.settings
        settings_errors = settings.validation_errors()
        if settings_errors:
            return SliceResult(success=False, errors=settings_errors)

        source = Path(stl_path)
        if not source.is_file():
            return SliceResult(success=False, errors=["The source STL file does not exist."])
        if source.suffix.lower() != ".stl":
            return SliceResult(success=False, errors=["Only STL input is currently supported by the slicer."])

        try:
            mesh = trimesh.load(str(source), force="mesh")
        except Exception as exc:
            return SliceResult(success=False, errors=[f"Could not read STL mesh: {exc}"])
        if mesh.is_empty or len(mesh.faces) == 0 or len(mesh.vertices) == 0:
            return SliceResult(success=False, errors=["STL mesh is empty or has no triangles."])
        if not mesh.is_watertight:
            return SliceResult(
                success=False,
                errors=["STL is not watertight. Repair and validate the mesh before slicing."],
            )
        extents = mesh.extents
        if extents[0] > settings.bed_size_x or extents[1] > settings.bed_size_y or extents[2] > settings.bed_size_z:
            return SliceResult(
                success=False,
                errors=[
                    "The model exceeds the configured printer build volume "
                    f"({extents[0]:.2f} × {extents[1]:.2f} × {extents[2]:.2f} mm model; "
                    f"{settings.bed_size_x:.2f} × {settings.bed_size_y:.2f} × {settings.bed_size_z:.2f} mm bed)."
                ],
            )

        output = Path(output_path).expanduser()
        if output.resolve() == source.resolve():
            return SliceResult(success=False, errors=["G-code output path must be different from the source STL path."])
        if output.suffix.lower() not in {".gcode", ".gco", ".gc"}:
            return SliceResult(success=False, errors=["Choose a G-code output filename ending in .gcode, .gco, or .gc."])
        if not self.cura_engine_path:
            return SliceResult(
                success=False,
                errors=[
                    "CuraEngine was not found. No G-code was generated because the old fallback only wrote "
                    "a few rectangular preview moves and was not safe or complete for printing. Install CuraEngine "
                    "with its definition resources before slicing."
                ],
            )

        definitions_dir = self._find_cura_definitions_dir()
        if not definitions_dir:
            return SliceResult(
                success=False,
                errors=[
                    "CuraEngine was found, but fdmprinter.def.json and fdmextruder.def.json were not found. "
                    "Install the matching Cura definition resources or set CURA_ENGINE_SEARCH_PATH."
                ],
            )

        definition_files = [
            definitions_dir / "fdmprinter.def.json",
            definitions_dir / "fdmextruder.def.json",
        ]
        if printer_definition:
            custom_definition = Path(printer_definition).expanduser()
            if not custom_definition.is_file():
                return SliceResult(success=False, errors=["The selected printer definition file does not exist."])
            if custom_definition.resolve() not in {item.resolve() for item in definition_files}:
                definition_files.append(custom_definition)

        if output.exists():
            try:
                output.unlink()
            except OSError as exc:
                return SliceResult(success=False, errors=[f"Cannot replace existing G-code output: {exc}"])
        return self._slice_with_cura(source, output, settings, definition_files)

    def _slice_with_cura(
        self,
        stl_path: Path,
        output_path: Path,
        settings: SliceSettings,
        definition_files: List[Path],
    ) -> SliceResult:
        """Invoke CuraEngine with its machine/extruder definitions and explicit overrides."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [self.cura_engine_path, "slice", "-v"]
        for definition in definition_files:
            command.extend(["-j", str(definition)])

        # Apply machine settings globally, then print settings at mesh-group scope.
        command.extend([
            "-s", f"machine_width={settings.bed_size_x}",
            "-s", f"machine_depth={settings.bed_size_y}",
            "-s", f"machine_height={settings.bed_size_z}",
            "-g",
        ])
        for key, value in settings.to_cura_settings().items():
            if isinstance(value, bool):
                serialized = "true" if value else "false"
            else:
                serialized = str(value)
            command.extend(["-s", f"{key}={serialized}"])

        command.extend(["-o", str(output_path), "-l", str(stl_path)])
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
        except subprocess.TimeoutExpired:
            return SliceResult(success=False, errors=["CuraEngine slicing timed out after 300 seconds."])
        except OSError as exc:
            return SliceResult(success=False, errors=[f"Could not launch CuraEngine: {exc}"])

        combined_output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        if result.returncode != 0:
            return SliceResult(
                success=False,
                errors=[f"CuraEngine failed with exit code {result.returncode}: {combined_output[-3000:]}"],
            )
        if not output_path.is_file() or output_path.stat().st_size == 0:
            return SliceResult(success=False, errors=["CuraEngine returned success but did not produce a G-code file."])

        validation = self.validate_gcode(str(output_path))
        if not validation.get("valid"):
            return SliceResult(
                success=False,
                errors=[str(validation.get("error", "Generated G-code failed validation."))],
            )
        stats = validation["stats"]
        required_checks = {
            "home command": stats.get("has_home"),
            "hotend temperature command": stats.get("has_temp"),
            "extrusion move": stats.get("has_extrusion"),
        }
        missing_checks = [label for label, passed in required_checks.items() if not passed]
        if missing_checks:
            return SliceResult(
                success=False,
                errors=["Generated G-code failed safety checks: missing " + ", ".join(missing_checks) + "."],
            )

        print_time, filament_used, layers = self._parse_cura_output(combined_output)
        warnings: List[str] = []
        if print_time is None or filament_used is None or layers is None:
            warnings.append("CuraEngine did not report all print statistics in its captured output.")
        return SliceResult(
            success=True,
            gcode_path=str(output_path),
            print_time=print_time,
            filament_used=filament_used,
            layers=layers,
            warnings=warnings,
        )

    def _parse_cura_output(self, output: str) -> tuple:
        """Parse CuraEngine output for print statistics."""
        print_time = None
        filament_used = None
        layers = None
        
        for line in output.split('\n'):
            if "Print time:" in line:
                # Format: "Print time: 1h 30m 45s"
                try:
                    time_str = line.split("Print time:")[1].strip()
                    print_time = self._parse_time_string(time_str)
                except:
                    pass
            elif "Filament used:" in line:
                # Format: "Filament used: 12.5g"
                try:
                    fil_str = line.split("Filament used:")[1].strip().replace('g', '')
                    filament_used = float(fil_str)
                except:
                    pass
            elif "Layers:" in line:
                try:
                    layers = int(line.split("Layers:")[1].strip())
                except:
                    pass
        
        return print_time, filament_used, layers
    
    def _parse_time_string(self, time_str: str) -> float:
        """Parse time string like '1h 30m 45s' to seconds."""
        total = 0
        parts = time_str.split()
        for part in parts:
            if part.endswith('h'):
                total += int(part[:-1]) * 3600
            elif part.endswith('m'):
                total += int(part[:-1]) * 60
            elif part.endswith('s'):
                total += int(part[:-1])
        return total
    
    def validate_gcode(self, gcode_path: str) -> Dict[str, Any]:
        """Check basic G-code structure and required print commands.

        This is a sanity check, not a substitute for validating the machine,
        firmware, extrusion calibration, material and actual printer profile.
        """
        try:
            text = Path(gcode_path).read_text(encoding="utf-8", errors="replace")
            if not text.strip():
                return {"valid": False, "error": "G-code file is empty."}

            stats = {
                "total_lines": len(text.splitlines()),
                "g_commands": 0,
                "m_commands": 0,
                "has_home": False,
                "has_temp": False,
                "has_extrusion": False,
                "max_x": 0.0, "max_y": 0.0, "max_z": 0.0,
                "min_x": 0.0, "min_y": 0.0, "min_z": 0.0,
            }
            seen_position: dict[str, bool] = {"x": False, "y": False, "z": False}
            position: dict[str, float] = {"X": 0.0, "Y": 0.0, "Z": 0.0}
            absolute_xyz = True
            absolute_e = True
            extrusion_position = 0.0

            for raw_line in text.splitlines():
                # Ignore human-readable comments so words like "E" or "G28"
                # inside comments cannot make an invalid file pass validation.
                line = raw_line.split(";", 1)[0].strip().upper()
                if not line:
                    continue

                command_match = re.match(r"^([GMT])\s*(-?\d+)", line)
                if not command_match:
                    continue
                command_type = command_match.group(1)
                command_number = int(command_match.group(2))
                command = f"{command_type}{command_number}"

                if command_type == "G":
                    stats["g_commands"] += 1
                    if command == "G90":
                        absolute_xyz = True
                    elif command == "G91":
                        absolute_xyz = False
                    elif command == "G92":
                        reset_e = re.search(r"(?<![A-Z])E\s*(-?(?:\d+(?:\.\d*)?|\.\d+))", line)
                        if reset_e:
                            extrusion_position = float(reset_e.group(1))
                    elif command == "G28":
                        stats["has_home"] = True
                        for axis in ("X", "Y", "Z"):
                            position[axis] = 0.0
                            seen_position[axis.lower()] = True

                    if command in {"G0", "G1", "G2", "G3"}:
                        values = {
                            key.upper(): float(value)
                            for key, value in re.findall(
                                r"(?<![A-Z])([XYZEF])\s*(-?(?:\d+(?:\.\d*)?|\.\d+))",
                                line,
                            )
                        }
                        for axis in ("X", "Y", "Z"):
                            if axis not in values:
                                continue
                            value = values[axis]
                            position[axis] = value if absolute_xyz else position[axis] + value
                            low_key = f"min_{axis.lower()}"
                            high_key = f"max_{axis.lower()}"
                            if not seen_position[axis.lower()]:
                                stats[low_key] = position[axis]
                                stats[high_key] = position[axis]
                                seen_position[axis.lower()] = True
                            else:
                                stats[low_key] = min(stats[low_key], position[axis])
                                stats[high_key] = max(stats[high_key], position[axis])

                        # Track extrusion mode so a retraction cannot masquerade as printing.
                        if "E" in values:
                            extrusion_value = values["E"]
                            extrusion_delta = extrusion_value - extrusion_position if absolute_e else extrusion_value
                            if absolute_e:
                                extrusion_position = extrusion_value
                            if extrusion_delta > 1e-9:
                                stats["has_extrusion"] = True
                elif command_type == "M":
                    stats["m_commands"] += 1
                    if command == "M82":
                        absolute_e = True
                    elif command == "M83":
                        absolute_e = False
                    elif command in {"M104", "M109"}:
                        stats["has_temp"] = True

            missing = []
            if not stats["has_home"]:
                missing.append("homing command (G28)")
            if not stats["has_temp"]:
                missing.append("hotend temperature command (M104/M109)")
            if not stats["has_extrusion"]:
                missing.append("extrusion move")
            if stats["g_commands"] == 0:
                missing.append("motion/control commands")

            if missing:
                return {
                    "valid": False,
                    "error": "G-code is missing required commands: " + ", ".join(missing) + ".",
                    "stats": stats,
                }
            return {"valid": True, "stats": stats}

        except OSError as exc:
            return {"valid": False, "error": f"Could not read G-code file: {exc}"}
        except Exception as exc:
            return {"valid": False, "error": f"G-code validation failed: {exc}"}


def create_default_printer_definition() -> Dict[str, Any]:
    """Create a generic printer definition for CuraEngine."""
    return {
        "id": "generic_fdm_printer",
        "name": "Generic FDM Printer",
        "version": 1,
        "inherits": "fdmprinter",
        "machine_width": {"default_value": 220},
        "machine_depth": {"default_value": 220},
        "machine_height": {"default_value": 250},
        "machine_extruder_count": {"default_value": 1},
        "machine_gcode_flavor": {"default_value": "Marlin"},
        "machine_heated_bed": {"default_value": True},
        "machine_nozzle_size": {"default_value": 0.4},
        "material_diameter": {"default_value": 1.75},
    }


if __name__ == "__main__":
    # Test
    slicer = Slicer()
    print(f"CuraEngine available: {slicer.cura_available}")
    if slicer.cura_available:
        print(f"CuraEngine path: {slicer.cura_engine_path}")
    print("Slicing module loaded successfully")
