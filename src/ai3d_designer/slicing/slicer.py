"""Production-oriented CuraEngine adapter.

This module never fabricates placeholder G-code. A slice succeeds only if CuraEngine
produces a non-empty file that passes basic structural and extrusion checks. These
checks do not replace reviewing the slicer preview and printer-specific settings.
"""
from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import trimesh


@dataclass
class SliceSettings:
    """FDM print settings. Dimensions are millimeters and speeds are mm/s."""

    printer_name: str = "Generic"
    bed_size_x: float = 220.0
    bed_size_y: float = 220.0
    bed_size_z: float = 250.0
    layer_height: float = 0.2
    initial_layer_height: float = 0.2
    wall_thickness: float = 1.2
    top_bottom_thickness: float = 0.8
    infill_density: float = 20.0
    infill_pattern: str = "grid"
    print_speed: float = 50.0
    infill_speed: float = 50.0
    wall_speed: float = 30.0
    travel_speed: float = 150.0
    initial_layer_speed: float = 20.0
    nozzle_temp: float = 200.0
    bed_temp: float = 60.0
    initial_layer_bed_temp: float = 60.0
    nozzle_diameter: float = 0.4
    filament_diameter: float = 1.75
    # Used only when Cura reports length but omits mass; the resulting mass is approximate.
    filament_density_g_cm3: float = 1.24
    flow_rate: float = 100.0
    adhesion_type: str = "brim"
    brim_width: float = 8.0
    brim_line_count: int = 5
    support_enabled: bool = False
    support_pattern: str = "zigzag"
    support_density: float = 15.0
    support_z_distance: float = 0.2
    support_xy_distance: float = 0.7
    retraction_enabled: bool = True
    retraction_distance: float = 5.0
    retraction_speed: float = 40.0
    fan_enabled: bool = True
    fan_speed: float = 100.0
    fan_speed_max: float = 100.0
    enable_prime_tower: bool = False
    wipe_tower_enabled: bool = False

    def validate(self) -> list[str]:
        """Return actionable validation errors before calling the external slicer."""
        errors: list[str] = []
        positive = {
            "bed_size_x": self.bed_size_x,
            "bed_size_y": self.bed_size_y,
            "bed_size_z": self.bed_size_z,
            "layer_height": self.layer_height,
            "initial_layer_height": self.initial_layer_height,
            "wall_thickness": self.wall_thickness,
            "top_bottom_thickness": self.top_bottom_thickness,
            "print_speed": self.print_speed,
            "infill_speed": self.infill_speed,
            "wall_speed": self.wall_speed,
            "travel_speed": self.travel_speed,
            "initial_layer_speed": self.initial_layer_speed,
            "nozzle_diameter": self.nozzle_diameter,
            "filament_diameter": self.filament_diameter,
            "filament_density_g_cm3": self.filament_density_g_cm3,
        }
        for name, value in positive.items():
            if not math.isfinite(float(value)) or value <= 0:
                errors.append(f"{name} must be a finite number greater than zero.")
        if self.layer_height > 1.0 or self.initial_layer_height > 1.0:
            errors.append("Layer heights over 1.0 mm are rejected; verify the printer and nozzle profile.")
        for name, value in {
            "infill_density": self.infill_density,
            "support_density": self.support_density,
            "flow_rate": self.flow_rate,
            "fan_speed": self.fan_speed,
            "fan_speed_max": self.fan_speed_max,
        }.items():
            upper = 200.0 if name == "flow_rate" else 100.0
            if not math.isfinite(float(value)) or not 0 <= value <= upper:
                errors.append(f"{name} must be between 0 and {upper:g}.")
        for name, value, upper in (
            ("nozzle_temp", self.nozzle_temp, 400),
            ("bed_temp", self.bed_temp, 200),
            ("initial_layer_bed_temp", self.initial_layer_bed_temp, 200),
        ):
            if not math.isfinite(float(value)) or not 0 <= value <= upper:
                errors.append(f"{name} must be between 0 and {upper} °C.")
        for name, value in {
            "brim_width": self.brim_width,
            "retraction_distance": self.retraction_distance,
            "retraction_speed": self.retraction_speed,
            "support_z_distance": self.support_z_distance,
            "support_xy_distance": self.support_xy_distance,
        }.items():
            if not math.isfinite(float(value)) or value < 0:
                errors.append(f"{name} must be a finite non-negative number.")
        if not isinstance(self.brim_line_count, int) or self.brim_line_count < 0:
            errors.append("brim_line_count must be a non-negative integer.")
        if self.infill_pattern not in {"grid", "lines", "triangles", "cubic", "gyroid"}:
            errors.append("Unsupported infill_pattern.")
        if self.adhesion_type not in {"none", "skirt", "brim", "raft"}:
            errors.append("Unsupported adhesion_type.")
        if self.support_pattern not in {"zigzag", "grid", "triangles", "concentric"}:
            errors.append("Unsupported support_pattern.")
        return errors

    def to_cura_json(self) -> dict[str, Any]:
        """Compatibility method returning flat setting overrides, not a definition JSON."""
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
            "machine_nozzle_size": self.nozzle_diameter,
            "material_diameter": self.filament_diameter,
            "material_flow": self.flow_rate,
            "adhesion_type": self.adhesion_type,
            "brim_width": self.brim_width,
            "brim_line_count": self.brim_line_count,
            "support_enable": self.support_enabled,
            "support_structure": self.support_pattern,
            "support_density": self.support_density,
            "support_top_distance": self.support_z_distance,
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
    """Slicer result; success means real, structurally checked G-code was produced."""

    success: bool
    gcode_path: Optional[str] = None
    print_time: Optional[float] = None
    filament_used: Optional[float] = None
    layers: Optional[int] = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    filament_length_m: Optional[float] = None
    filament_weight_estimated: bool = False


class Slicer:
    """CuraEngine wrapper. No fallback generates fake or partial print G-code."""

    def __init__(self, cura_engine_path: Optional[str] = None):
        self.cura_engine_path = cura_engine_path or self._find_cura_engine()
        self.cura_available = bool(self.cura_engine_path)
        self.settings = SliceSettings()

    @staticmethod
    def _find_cura_engine() -> Optional[str]:
        """Find CuraEngine on PATH or in common Windows installation folders."""
        for executable in ("CuraEngine", "curaengine", "CuraEngine.exe"):
            found = shutil.which(executable)
            if found:
                try:
                    result = subprocess.run([found, "--version"], capture_output=True, timeout=5, check=False)
                    if result.returncode == 0:
                        return found
                except (OSError, subprocess.TimeoutExpired):
                    continue

        candidates: list[Path] = []
        for root in (Path("C:/Program Files"), Path("C:/Program Files (x86)")):
            if root.exists():
                candidates.extend(root.glob("UltiMaker Cura*/CuraEngine.exe"))
                candidates.extend(root.glob("Ultimaker Cura*/CuraEngine.exe"))
                candidates.extend(root.glob("Cura*/CuraEngine.exe"))
        for candidate in candidates:
            try:
                result = subprocess.run([str(candidate), "--version"], capture_output=True, timeout=5, check=False)
                if result.returncode == 0:
                    return str(candidate)
            except (OSError, subprocess.TimeoutExpired):
                continue
        return None

    def slice(
        self,
        stl_path: str,
        output_path: str,
        settings: Optional[SliceSettings] = None,
        printer_definition: Optional[str] = None,
        timeout_seconds: float = 300.0,
    ) -> SliceResult:
        """Slice an STL using CuraEngine and an actual Cura printer definition."""
        settings = settings or self.settings
        errors = settings.validate()
        if errors:
            return SliceResult(success=False, errors=errors)
        model_path = Path(stl_path).expanduser()
        if not model_path.is_file():
            return SliceResult(success=False, errors=[f"Input STL does not exist: {model_path}"])
        if not self.cura_available or not self.cura_engine_path:
            return SliceResult(
                success=False,
                errors=[
                    "CuraEngine was not found. Install CuraEngine and configure a compatible printer/extruder definition JSON. No placeholder G-code was generated."
                ],
            )

        definition_value = printer_definition or os.environ.get("CURA_PRINTER_DEFINITION", "")
        if isinstance(definition_value, (list, tuple)):
            definition_names = [str(value).strip() for value in definition_value if str(value).strip()]
        else:
            # GUI supports multiple definition files separated by semicolons.
            definition_names = [part.strip() for part in str(definition_value).split(";") if part.strip()]
        definition_paths = [Path(value).expanduser() for value in definition_names]
        if not definition_paths or any(not path.is_file() for path in definition_paths):
            return SliceResult(
                success=False,
                errors=[
                    "Select valid Cura printer/extruder definition JSON file(s), separated with semicolons. Printer-specific start/end G-code and firmware settings are required; no G-code was generated."
                ],
            )

        try:
            mesh = trimesh.load(str(model_path), force="mesh")
            if not isinstance(mesh, trimesh.Trimesh) or mesh.is_empty or len(mesh.faces) == 0:
                return SliceResult(success=False, errors=["STL is empty or could not be loaded as a triangle mesh."])
            if not bool(mesh.is_watertight):
                return SliceResult(success=False, errors=["STL mesh is not watertight. Repair it before slicing."])
            if not mesh.is_volume or not math.isfinite(float(mesh.volume)) or float(mesh.volume) <= 0:
                return SliceResult(success=False, errors=["STL mesh has invalid or non-positive volume."])
            extents = mesh.extents
            if not all(math.isfinite(float(value)) for value in extents):
                return SliceResult(success=False, errors=["STL bounding box contains non-finite dimensions."])
            if extents[0] > settings.bed_size_x or extents[1] > settings.bed_size_y or extents[2] > settings.bed_size_z:
                return SliceResult(
                    success=False,
                    errors=[
                        f"Model dimensions ({extents[0]:.1f} x {extents[1]:.1f} x {extents[2]:.1f} mm) exceed configured build volume ({settings.bed_size_x:.1f} x {settings.bed_size_y:.1f} x {settings.bed_size_z:.1f} mm)."
                    ],
                )
        except Exception as exc:
            return SliceResult(success=False, errors=[f"Could not validate STL: {exc}"])

        destination = Path(output_path).expanduser()
        temporary_output: Optional[Path] = None
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                prefix=f".{destination.stem}-",
                suffix=".gcode",
                dir=str(destination.parent),
                delete=False,
            ) as temp_file:
                temporary_output = Path(temp_file.name)

            command = [str(self.cura_engine_path), "slice", "-v"]
            for definition_path in definition_paths:
                command.extend(["-j", str(definition_path.resolve())])
            command.extend(["-l", str(model_path.resolve()), "-o", str(temporary_output)])
            for key, value in settings.to_cura_json().items():
                command.extend(["-s", f"{key}={self._cura_value(value)}"])

            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=max(1.0, float(timeout_seconds)), check=False)
            except subprocess.TimeoutExpired:
                return SliceResult(success=False, errors=[f"CuraEngine slicing timed out after {max(1.0, float(timeout_seconds)):g} seconds."])
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "no diagnostic output").strip()
                return SliceResult(success=False, errors=[f"CuraEngine failed (exit {result.returncode}): {detail[-2500:]}"])
            if not temporary_output.is_file() or temporary_output.stat().st_size == 0:
                return SliceResult(success=False, errors=["CuraEngine returned success but produced no G-code file."])

            validation = self.validate_gcode(str(temporary_output))
            if not validation.get("valid"):
                return SliceResult(
                    success=False,
                    errors=[f"Generated G-code failed structural validation: {validation.get('error', 'unknown error')}"],
                )

            os.replace(temporary_output, destination)
            output_text = (result.stdout or "") + "\n" + (result.stderr or "")
            metadata_text = self._read_gcode_metrics(temporary_output)
            metric_text = output_text + "\n" + metadata_text
            print_time, filament_used, layers = self._parse_cura_output(metric_text)
            filament_length_m = self._parse_filament_length_m(metric_text)
            weight_estimated = False
            warnings: list[str] = []
            if filament_used is None and filament_length_m is not None:
                # Length and diameter yield filament volume; material density converts volume to mass.
                filament_used = round(
                    filament_length_m * math.pi * (settings.filament_diameter / 2) ** 2
                    * settings.filament_density_g_cm3,
                    3,
                )
                weight_estimated = True
                warnings.append("Filament mass is estimated from reported length, configured filament diameter, and a PLA-like density of 1.24 g/cm³; verify against your actual material.")
            if not mesh.is_winding_consistent:
                warnings.append("Input mesh orientation was not consistent; inspect the sliced preview carefully.")
            return SliceResult(
                success=True,
                gcode_path=str(destination),
                print_time=print_time,
                filament_used=filament_used,
                filament_length_m=filament_length_m,
                filament_weight_estimated=weight_estimated,
                layers=layers or validation["stats"]["layers"],
                warnings=warnings,
            )
        except Exception as exc:
            return SliceResult(success=False, errors=[f"Slicing failed safely: {exc}"])
        finally:
            try:
                if temporary_output is not None and temporary_output.exists():
                    temporary_output.unlink()
            except OSError:
                pass

    @staticmethod
    def _cura_value(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, float):
            return f"{value:.6g}"
        return str(value)

    @staticmethod
    def _parse_cura_output(output: str) -> tuple[Optional[float], Optional[float], Optional[int]]:
        """Read print time, filament mass (grams only), and layer count from real Cura output."""
        print_time: Optional[float] = None
        filament_used: Optional[float] = None
        layers: Optional[int] = None
        for line in output.splitlines():
            time_match = re.search(r"Print time:\s*(.*)", line, re.IGNORECASE)
            if time_match:
                parsed_time = Slicer._parse_time_string(time_match.group(1))
                if parsed_time is not None:
                    print_time = parsed_time
            machine_time_match = re.search(r"(?:;TIME:\s*|PRINT\.TIME:\s*)([0-9]+(?:\.[0-9]+)?)", line, re.IGNORECASE)
            if machine_time_match:
                print_time = float(machine_time_match.group(1))
            weight_match = re.search(r"(?:Filament weight|Filament used)\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*(?:g|grams)\b", line, re.IGNORECASE)
            if weight_match:
                filament_used = float(weight_match.group(1))
            layer_match = re.search(r"(?:;LAYER_COUNT:\s*|(?:Total\s+)?Layers:\s*)(\d+)", line, re.IGNORECASE)
            if layer_match:
                layers = int(layer_match.group(1))
        return print_time, filament_used, layers

    @staticmethod
    def _parse_filament_length_m(output: str) -> Optional[float]:
        """Parse filament length without mistaking millimetres or centimetres for grams."""
        length_m: Optional[float] = None
        for match in re.finditer(r"Filament used\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*(mm|cm|m)\b", output, re.IGNORECASE):
            value = float(match.group(1))
            unit = match.group(2).lower()
            length_m = value / 1000 if unit == "mm" else value / 100 if unit == "cm" else value
        return length_m

    @staticmethod
    def _read_gcode_metrics(path: Path) -> str:
        """Read only slicer metadata lines, avoiding a second whole-file memory copy."""
        needles = ("filament used", "filament weight", "print time", ";time:", "print.time", "layer_count", "total layers")
        collected: list[str] = []
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if any(needle in line.lower() for needle in needles):
                    collected.append(line)
        return "".join(collected)

    @staticmethod
    def _parse_time_string(time_string: str) -> Optional[float]:
        total = 0
        matches = list(re.finditer(r"(\d+)\s*([hms])", time_string.lower()))
        if not matches:
            return None
        for match in matches:
            amount = int(match.group(1))
            total += amount * {"h": 3600, "m": 60, "s": 1}[match.group(2)]
        return float(total)

    def validate_gcode(self, gcode_path: str) -> dict[str, Any]:
        """Heuristic structure check for generated G-code; not a firmware safety check."""
        path = Path(gcode_path)
        if not path.is_file():
            return {"valid": False, "error": "G-code file does not exist."}
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return {"valid": False, "error": f"Could not read G-code: {exc}"}
        lines = text.splitlines()
        if not lines:
            return {"valid": False, "error": "G-code file is empty."}
        lowered = text.lower()
        if "preview only" in lowered or "basic g-code generated by ai 3d designer" in lowered:
            return {"valid": False, "error": "Placeholder/preview-only G-code is not safe to use for printing."}

        stats: dict[str, Any] = {
            "total_lines": len(lines),
            "g_commands": 0,
            "m_commands": 0,
            "has_home": False,
            "has_temp": False,
            "has_extrusion": False,
            "has_layer_marker": False,
            "layers": 0,
            "min_x": math.inf, "min_y": math.inf, "min_z": math.inf,
            "max_x": -math.inf, "max_y": -math.inf, "max_z": -math.inf,
        }
        for raw_line in lines:
            stripped = raw_line.strip()
            code = stripped.split(";", 1)[0].strip()
            if re.search(r";\s*(?:LAYER:\s*\d+|LAYER\s+\d+)", stripped, re.IGNORECASE):
                stats["has_layer_marker"] = True
                stats["layers"] += 1
            if not code:
                continue
            command_match = re.match(r"([GMT]\d+)\b", code, re.IGNORECASE)
            if not command_match:
                continue
            command = command_match.group(1).upper()
            if command.startswith("G"):
                stats["g_commands"] += 1
                stats["has_home"] = stats["has_home"] or command == "G28"
            elif command.startswith("M"):
                stats["m_commands"] += 1
                stats["has_temp"] = stats["has_temp"] or command in {"M104", "M109", "M140", "M190"}
            if command in {"G0", "G1", "G2", "G3"}:
                extrusion = re.search(r"(?:^|\s)E([-+]?(?:\d+\.?\d*|\.\d+))(?=\s|$)", code, re.IGNORECASE)
                if extrusion and float(extrusion.group(1)) > 0:
                    stats["has_extrusion"] = True
            for axis in ("X", "Y", "Z"):
                coordinate = re.search(
                    rf"(?:^|\s){axis}([-+]?(?:\d+\.?\d*|\.\d+))(?=\s|$)",
                    code, re.IGNORECASE,
                )
                if coordinate:
                    value = float(coordinate.group(1))
                    stats[f"min_{axis.lower()}"] = min(stats[f"min_{axis.lower()}"], value)
                    stats[f"max_{axis.lower()}"] = max(stats[f"max_{axis.lower()}"], value)

        for axis in ("x", "y", "z"):
            if not math.isfinite(stats[f"min_{axis}"]):
                stats[f"min_{axis}"] = 0.0
                stats[f"max_{axis}"] = 0.0
        if stats["g_commands"] == 0:
            return {"valid": False, "error": "File contains no recognized G-code motion commands."}
        if not stats["has_extrusion"]:
            return {"valid": False, "error": "No positive extrusion commands were found."}
        if not stats["has_layer_marker"]:
            return {"valid": False, "error": "No layer markers were found; this may not be complete slicer output."}
        return {"valid": True, "stats": stats}


def create_default_printer_definition() -> dict[str, Any]:
    """Return a template hint; this is not a production-ready Cura printer profile."""
    return {
        "id": "generic_fdm_printer",
        "name": "Generic FDM Printer TEMPLATE — complete and verify before use",
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


def get_slicing_capability() -> dict[str, Any]:
    """Report readiness only when CuraEngine and compatible printer profiles exist."""
    engine = Slicer._find_cura_engine()
    if not engine:
        return {
            "available": False,
            "engine": None,
            "reason": "CuraEngine was not found on the backend PATH or in known installation locations.",
        }

    configured = os.environ.get("CURA_PRINTER_DEFINITION", "").strip()
    definitions = [value.strip() for value in configured.split(";") if value.strip()]
    if not definitions:
        return {
            "available": False,
            "engine": os.path.basename(engine),
            "reason": "CURA_PRINTER_DEFINITION is not configured. Add compatible Cura printer/extruder definition JSON path(s), separated with semicolons.",
        }
    missing = [value for value in definitions if not os.path.isfile(os.path.expanduser(value))]
    if missing:
        return {
            "available": False,
            "engine": os.path.basename(engine),
            "reason": "CURA_PRINTER_DEFINITION points to missing file(s): " + ", ".join(missing[:3]),
        }
    return {"available": True, "engine": os.path.basename(engine), "reason": None}
