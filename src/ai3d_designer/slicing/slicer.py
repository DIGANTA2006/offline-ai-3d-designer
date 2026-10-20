
"""
Slicing module for 3D printing - integrates with CuraEngine or provides basic slicing.
"""
import os
import subprocess
import json
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
import trimesh
import numpy as np

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
    
    def to_cura_json(self) -> Dict[str, Any]:
        """Convert to CuraEngine JSON format."""
        return {
            "machine_settings": {
                "machine_width": {"value": self.bed_size_x},
                "machine_depth": {"value": self.bed_size_y},
                "machine_height": {"value": self.bed_size_z},
            },
            "quality": {
                "layer_height": {"value": self.layer_height},
                "initial_layer_height": {"value": self.initial_layer_height},
                "wall_thickness": {"value": self.wall_thickness},
                "top_bottom_thickness": {"value": self.top_bottom_thickness},
            },
            "infill": {
                "infill_sparse_density": {"value": self.infill_density},
                "infill_pattern": {"value": self.infill_pattern},
            },
            "speed": {
                "speed_print": {"value": self.print_speed},
                "speed_infill": {"value": self.infill_speed},
                "speed_wall": {"value": self.wall_speed},
                "speed_travel": {"value": self.travel_speed},
                "speed_initial_layer": {"value": self.initial_layer_speed},
            },
            "temperature": {
                "material_print_temperature": {"value": self.nozzle_temp},
                "material_bed_temperature": {"value": self.bed_temp},
                "material_bed_temperature_layer_0": {"value": self.initial_layer_bed_temp},
            },
            "material": {
                "material_diameter": {"value": self.filament_diameter},
                "material_flow": {"value": self.flow_rate},
            },
            "adhesion": {
                "adhesion_type": {"value": self.adhesion_type},
                "brim_width": {"value": self.brim_width},
                "brim_line_count": {"value": self.brim_line_count},
            },
            "support": {
                "support_enable": {"value": self.support_enabled},
                "support_pattern": {"value": self.support_pattern},
                "support_density": {"value": self.support_density},
                "support_z_distance": {"value": self.support_z_distance},
                "support_xy_distance": {"value": self.support_xy_distance},
            },
            "retraction": {
                "retraction_enable": {"value": self.retraction_enabled},
                "retraction_amount": {"value": self.retraction_distance},
                "retraction_speed": {"value": self.retraction_speed},
            },
            "cooling": {
                "cool_fan_enabled": {"value": self.fan_enabled},
                "cool_fan_speed": {"value": self.fan_speed},
                "cool_fan_speed_max": {"value": self.fan_speed_max},
            }
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
        """Try to find CuraEngine executable."""
        # Common locations
        possible_paths = [
            "CuraEngine",
            "curaengine",
            r"C:\Program Files\UltiMaker Cura 5.x\CuraEngine.exe",
            r"C:\Program Files\Ultimaker Cura 5.x\CuraEngine.exe",
            r"C:\Program Files\Cura\CuraEngine.exe",
            "/usr/bin/CuraEngine",
            "/usr/local/bin/CuraEngine",
        ]
        
        for path in possible_paths:
            try:
                result = subprocess.run([path, "--version"], capture_output=True, timeout=5)
                if result.returncode == 0:
                    return path
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        
        return None
    
    def slice(
        self,
        stl_path: str,
        output_path: str,
        settings: Optional[SliceSettings] = None,
        printer_definition: Optional[str] = None
    ) -> SliceResult:
        """
        Slice an STL file to G-code.
        
        Args:
            stl_path: Path to input STL file
            output_path: Path to output G-code file
            settings: Slice settings (uses defaults if None)
            printer_definition: Path to printer definition JSON (for CuraEngine)
            
        Returns:
            SliceResult with outcome
        """
        if settings is None:
            settings = self.settings
        
        if self.cura_available:
            return self._slice_with_cura(stl_path, output_path, settings, printer_definition)
        else:
            return self._slice_basic(stl_path, output_path, settings)
    
    def _slice_with_cura(
        self,
        stl_path: str,
        output_path: str,
        settings: SliceSettings,
        printer_definition: Optional[str]
    ) -> SliceResult:
        """Slice using CuraEngine."""
        try:
            # Build command
            cmd = [
                self.cura_engine_path,
                "slice",
                "-v",
                "-o", output_path,
                "-l", stl_path,
            ]
            
            # Add settings as JSON
            settings_json = settings.to_cura_json()
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(settings_json, f)
                settings_file = f.name
            
            cmd.extend(["-j", settings_file])
            
            if printer_definition:
                cmd.extend(["-j", printer_definition])
            
            # Run slicing
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            # Clean up temp file
            os.unlink(settings_file)
            
            if result.returncode != 0:
                return SliceResult(
                    success=False,
                    errors=[f"CuraEngine failed: {result.stderr}"]
                )
            
            # Parse output for stats
            print_time, filament_used, layers = self._parse_cura_output(result.stdout)
            
            return SliceResult(
                success=True,
                gcode_path=output_path,
                print_time=print_time,
                filament_used=filament_used,
                layers=layers
            )
            
        except subprocess.TimeoutExpired:
            return SliceResult(success=False, errors=["Slicing timed out"])
        except Exception as e:
            return SliceResult(success=False, errors=[str(e)])
    
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
    
    def _slice_basic(
        self,
        stl_path: str,
        output_path: str,
        settings: SliceSettings
    ) -> SliceResult:
        """
        Basic slicing fallback (very simple, for demonstration).
        In production, you'd want a proper slicer or CuraEngine.
        """
        try:
            # Load mesh
            mesh = trimesh.load(stl_path)
            
            # Basic validation
            if not mesh.is_watertight:
                return SliceResult(
                    success=False,
                    errors=["Mesh is not watertight - cannot slice reliably"]
                )
            
            # Generate very basic G-code (just for preview)
            gcode = self._generate_basic_gcode(mesh, settings)
            
            with open(output_path, 'w') as f:
                f.write(gcode)
            
            # Estimate
            bounds = mesh.bounds
            height = bounds[1, 2] - bounds[0, 2]
            layers = int(height / settings.layer_height)
            volume = mesh.volume / 1000.0  # cm³
            filament_used = volume * 1.24  # PLA density ~1.24 g/cm³
            print_time = layers * 30  # rough estimate: 30s per layer
            
            return SliceResult(
                success=True,
                gcode_path=output_path,
                print_time=print_time,
                filament_used=filament_used,
                layers=layers,
                warnings=["Using basic slicer - for preview only. Install CuraEngine for production."]
            )
            
        except Exception as e:
            return SliceResult(success=False, errors=[str(e)])
    
    def _generate_basic_gcode(self, mesh: trimesh.Trimesh, settings: SliceSettings) -> str:
        """Generate minimal G-code for preview."""
        bounds = mesh.bounds
        center_x = (bounds[0, 0] + bounds[1, 0]) / 2
        center_y = (bounds[0, 1] + bounds[1, 1]) / 2
        
        lines = [
            "; Basic G-code generated by AI 3D Designer",
            "; This is a PREVIEW only - not for actual printing!",
            f"; Model: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces",
            f"; Bounds: X{bounds[0,0]:.1f}-{bounds[1,0]:.1f} Y{bounds[0,1]:.1f}-{bounds[1,1]:.1f} Z{bounds[0,2]:.1f}-{bounds[1,2]:.1f}",
            "",
            "G21 ; Set units to mm",
            "G90 ; Absolute positioning",
            "M82 ; Absolute extrusion",
            "",
            f"M104 S{settings.nozzle_temp} ; Heat nozzle",
            f"M140 S{settings.bed_temp} ; Heat bed",
            "M190 S{settings.bed_temp} ; Wait for bed",
            "M109 S{settings.nozzle_temp} ; Wait for nozzle",
            "",
            "G28 ; Home all axes",
            "G1 Z0.2 F3000 ; Lift nozzle",
            "G1 X10 Y10 F3000 ; Move to corner",
            "G1 Z0 ; Touch bed",
            "G1 E5 F300 ; Prime nozzle",
            "G1 X50 E10 F300 ; Wipe",
            "G92 E0 ; Reset extruder",
            "",
            "; === LAYERS ===",
        ]
        
        # Add dummy layers
        height = bounds[1, 2] - bounds[0, 2]
        layer_count = int(height / settings.layer_height)
        for i in range(min(layer_count, 5)):  # Just first 5 layers for preview
            z = bounds[0, 2] + i * settings.layer_height
            lines.append(f"; Layer {i+1}/{layer_count} at Z={z:.2f}")
            lines.append(f"G1 Z{z:.2f} F{settings.print_speed * 60}")
            # Perimeter
            lines.append(f"G1 X{bounds[0,0]:.1f} Y{bounds[0,1]:.1f} F{settings.wall_speed * 60}")
            lines.append(f"G1 X{bounds[1,0]:.1f} Y{bounds[0,1]:.1f} E1")
            lines.append(f"G1 X{bounds[1,0]:.1f} Y{bounds[1,1]:.1f} E2")
            lines.append(f"G1 X{bounds[0,0]:.1f} Y{bounds[1,1]:.1f} E3")
            lines.append(f"G1 X{bounds[0,0]:.1f} Y{bounds[0,1]:.1f} E4")
        
        lines.extend([
            "",
            "; === END ===",
            "G1 Z{bounds[1,2] + 10:.1f} F3000 ; Lift nozzle",
            "G1 X0 Y0 F3000 ; Home XY",
            "M104 S0 ; Turn off nozzle",
            "M140 S0 ; Turn off bed",
            "M84 ; Disable motors",
        ])
        
        return "\n".join(lines)
    
    def validate_gcode(self, gcode_path: str) -> Dict[str, Any]:
        """Basic G-code validation."""
        try:
            with open(gcode_path, 'r') as f:
                lines = f.readlines()
            
            stats = {
                "total_lines": len(lines),
                "g_commands": 0,
                "m_commands": 0,
                "has_home": False,
                "has_temp": False,
                "has_extrusion": False,
                "max_x": 0, "max_y": 0, "max_z": 0,
                "min_x": 0, "min_y": 0, "min_z": 0,
            }
            
            for line in lines:
                line = line.strip()
                if line.startswith('G'):
                    stats["g_commands"] += 1
                    if line.startswith('G28'):
                        stats["has_home"] = True
                    # Parse coordinates
                    for axis in ['X', 'Y', 'Z']:
                        if axis in line:
                            try:
                                val = float(line.split(axis)[1].split()[0])
                                if val > stats[f"max_{axis.lower()}"]:
                                    stats[f"max_{axis.lower()}"] = val
                                if val < stats[f"min_{axis.lower()}"]:
                                    stats[f"min_{axis.lower()}"] = val
                            except:
                                pass
                elif line.startswith('M'):
                    stats["m_commands"] += 1
                    if line.startswith('M104') or line.startswith('M109'):
                        stats["has_temp"] = True
                if 'E' in line and ('G1' in line or 'G0' in line):
                    stats["has_extrusion"] = True
            
            return {"valid": True, "stats": stats}
            
        except Exception as e:
            return {"valid": False, "error": str(e)}


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
