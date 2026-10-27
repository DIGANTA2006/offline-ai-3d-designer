"""
Export module for STEP, STL, 3MF, and other formats with validation.
"""

import os
import tempfile
import zipfile
import json
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime

from build123d import Part
from build123d import export_step as b123d_export_step
from build123d import export_stl as b123d_export_stl
import trimesh
import manifold3d
import numpy as np


@dataclass
class ExportResult:
    """Result of an export operation."""
    success: bool
    file_path: str
    format: str
    file_size: int
    validation_errors: List[str]
    warnings: List[str]


def export_step(part: Part, file_path: str, validate: bool = True) -> ExportResult:
    """
    Export part to STEP format (AP242).
    
    Args:
        part: build123d Part to export
        file_path: Output file path
        validate: Whether to validate the exported file
        
    Returns:
        ExportResult with success status and validation info
    """
    errors = []
    warnings = []
    
    try:
        # Ensure directory exists
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Export STEP
        b123d_export_step(part, file_path)
        
        file_size = os.path.getsize(file_path)
        
        # Validate if requested
        if validate:
            val_errors, val_warnings = _validate_step(file_path)
            errors.extend(val_errors)
            warnings.extend(val_warnings)
        
        success = len(errors) == 0
        
    except Exception as e:
        errors.append(f"Export failed: {str(e)}")
        file_size = 0
        success = False
    
    return ExportResult(
        success=success,
        file_path=file_path,
        format="STEP",
        file_size=file_size,
        validation_errors=errors,
        warnings=warnings,
    )


def export_stl(part: Part, file_path: str, validate: bool = True, 
               angular_tolerance: float = 0.1, tolerance: float = 0.01) -> ExportResult:
    """
    Export part to STL format.
    
    Args:
        part: build123d Part to export
        file_path: Output file path
        validate: Whether to validate the exported file
        angular_tolerance: Angular tolerance for tessellation (degrees)
        tolerance: Linear tolerance for tessellation (mm)
        
    Returns:
        ExportResult with success status and validation info
    """
    errors = []
    warnings = []
    
    try:
        # Ensure directory exists
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Export STL
        b123d_export_stl(part, file_path, angular_tolerance=angular_tolerance, tolerance=tolerance)
        
        file_size = os.path.getsize(file_path)
        
        # Validate if requested
        if validate:
            val_errors, val_warnings = _validate_stl(file_path)
            errors.extend(val_errors)
            warnings.extend(val_warnings)
        
        success = len(errors) == 0
        
    except Exception as e:
        errors.append(f"Export failed: {str(e)}")
        file_size = 0
        success = False
    
    return ExportResult(
        success=success,
        file_path=file_path,
        format="STL",
        file_size=file_size,
        validation_errors=errors,
        warnings=warnings,
    )


def export_3mf(part: Part, file_path: str, validate: bool = True,
               angular_tolerance: float = 0.1, tolerance: float = 0.01) -> ExportResult:
    """
    Export part to 3MF format.
    
    Args:
        part: build123d Part to export
        file_path: Output file path
        validate: Whether to validate the exported file
        angular_tolerance: Angular tolerance for tessellation (degrees)
        tolerance: Linear tolerance for tessellation (mm)
        
    Returns:
        ExportResult with success status and validation info
    """
    errors = []
    warnings = []
    
    try:
        # Ensure directory exists
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Export 3MF using trimesh - tessellate returns (vertices, faces) where vertices are Vector objects
        vertices, faces = part.tessellate(angular_tolerance)
        # Convert Vector vertices to numpy array
        vertex_array = np.array([[v.X, v.Y, v.Z] for v in vertices], dtype=np.float64)
        face_array = np.array(faces, dtype=np.int32)
        
        mesh = trimesh.Trimesh(
            vertices=vertex_array,
            faces=face_array,
            process=False
        )
        mesh.export(file_path, file_type='3mf')
        
        file_size = os.path.getsize(file_path)
        
        # Validate if requested
        if validate:
            val_errors, val_warnings = _validate_3mf(file_path)
            errors.extend(val_errors)
            warnings.extend(val_warnings)
        
        success = len(errors) == 0
        
    except Exception as e:
        errors.append(f"3MF export failed: {str(e)}")
        file_size = 0
        success = False
    
    return ExportResult(
        success=success,
        file_path=file_path,
        format="3MF",
        file_size=file_size,
        validation_errors=errors,
        warnings=warnings,
    )


def _get_center_of_mass(part: Part) -> tuple:
    """Get center of mass from part, with fallback for different build123d versions."""
    try:
        # Try the center_of_mass property (newer versions)
        com = part.center_of_mass
        return (float(com.X), float(com.Y), float(com.Z))
    except AttributeError:
        try:
            # Try center() method
            com = part.center()
            return (float(com.X), float(com.Y), float(com.Z))
        except AttributeError:
            # Fallback: use bounding box center
            bbox = part.bounding_box()
            return (
                float((bbox.min.X + bbox.max.X) / 2),
                float((bbox.min.Y + bbox.max.Y) / 2),
                float((bbox.min.Z + bbox.max.Z) / 2)
            )


def generate_dimension_report(part: Part, part_spec: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Generate a dimension report for the part.
    
    Args:
        part: build123d Part
        part_spec: Optional PartSpec dictionary for reference dimensions
        
    Returns:
        Dictionary with dimension report
    """
    bbox = part.bounding_box()
    volume = float(part.volume)
    com_x, com_y, com_z = _get_center_of_mass(part)
    
    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "bounding_box": {
            "min": [float(bbox.min.X), float(bbox.min.Y), float(bbox.min.Z)],
            "max": [float(bbox.max.X), float(bbox.max.Y), float(bbox.max.Z)],
            "size": [float(bbox.size.X), float(bbox.size.Y), float(bbox.size.Z)],
        },
        "volume_mm3": round(volume, 3),
        "volume_cm3": round(volume / 1000.0, 3),
        "center_of_mass": [com_x, com_y, com_z],
    }
    
    if part_spec:
        report["spec"] = part_spec
    
    return report


def generate_print_guide(part: Part, settings: Optional[Dict[str, Any]] = None) -> str:
    """
    Generate a print guide markdown document.
    
    Args:
        part: build123d Part
        settings: Optional print settings
        
    Returns:
        Markdown string for print guide
    """
    bbox = part.bounding_box()
    volume = float(part.volume)
    com_x, com_y, com_z = _get_center_of_mass(part)
    
    guide = f"""# Print Guide

Generated: {datetime.utcnow().isoformat()}Z

## Part Overview
- **Volume**: {volume:.2f} mm³ ({volume/1000:.3f} cm³)
- **Dimensions**: {bbox.size.X:.1f} × {bbox.size.Y:.1f} × {bbox.size.Z:.1f} mm (X × Y × Z)
- **Center of Mass**: ({com_x:.1f}, {com_y:.1f}, {com_z:.1f}) mm

## Recommended Print Settings
"""
    
    if settings:
        guide += f"""- **Layer Height**: {settings.get('layer_height', 0.2)} mm
- **Wall Thickness**: {settings.get('wall_thickness', 1.2)} mm
- **Infill Density**: {settings.get('infill_density', 20)}%
- **Infill Pattern**: {settings.get('infill_pattern', 'grid')}
- **Print Speed**: {settings.get('print_speed', 50)} mm/s
- **Nozzle Temperature**: {settings.get('nozzle_temp', 200)}°C
- **Bed Temperature**: {settings.get('bed_temp', 60)}°C
- **Support**: {'Enabled' if settings.get('support_enabled', False) else 'Disabled'}
- **Adhesion**: {settings.get('adhesion_type', 'brim').capitalize()}
"""
    else:
        guide += """- **Layer Height**: 0.2 mm
- **Wall Thickness**: 1.2 mm
- **Infill Density**: 20%
- **Infill Pattern**: grid
- **Print Speed**: 50 mm/s
- **Nozzle Temperature**: 200°C (PLA)
- **Bed Temperature**: 60°C (PLA)
- **Support**: Disabled
- **Adhesion**: Brim
"""
    
    guide += """
## Orientation Recommendations
- Place largest flat face on build plate for best adhesion
- Minimize overhangs > 45° where possible
- Consider splitting tall parts if height > 200mm

## Post-Processing
- Remove brim/raft carefully with deburring tool
- Sand layer lines if cosmetic finish required
- Anneal PLA at 80-100°C for 30min for improved strength (optional)

## Quality Checks Before Print
- [ ] Model is watertight (validated on export)
- [ ] No non-manifold edges
- [ ] Dimensions match design intent
- [ ] Fits within printer build volume
- [ ] Adequate bed adhesion strategy selected

---
*Generated by Offline AI 3D Designer*
"""
    return guide


def export_zip_bundle(
    part: Part,
    zip_path: str,
    part_spec: Optional[Dict[str, Any]] = None,
    settings: Optional[Dict[str, Any]] = None,
    include_step: bool = True,
    include_stl: bool = True,
    include_3mf: bool = True,
    validate: bool = True,
) -> ExportResult:
    """
    Export a ZIP bundle containing STEP, STL, 3MF, dimension report, and print guide.
    
    Args:
        part: build123d Part to export
        zip_path: Output ZIP file path
        part_spec: Optional PartSpec dictionary
        settings: Optional print settings
        include_step: Include STEP file
        include_stl: Include STL file
        include_3mf: Include 3MF file
        validate: Whether to validate exported files
        
    Returns:
        ExportResult with success status
    """
    errors = []
    warnings = []
    file_size = 0
    
    try:
        Path(zip_path).parent.mkdir(parents=True, exist_ok=True)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            # Use part_spec name if available, otherwise fall back to zip file stem
            if part_spec and part_spec.get("name"):
                base_name = part_spec["name"]
            else:
                base_name = Path(zip_path).stem
            
            # Export individual formats
            exported_files = {}
            
            if include_step:
                step_path = tmpdir_path / f"{base_name}.step"
                result = export_step(part, str(step_path), validate=validate)
                if not result.success:
                    errors.extend([f"STEP: {e}" for e in result.validation_errors])
                else:
                    exported_files["step"] = step_path
                    warnings.extend([f"STEP: {w}" for w in result.warnings])
            
            if include_stl:
                stl_path = tmpdir_path / f"{base_name}.stl"
                result = export_stl(part, str(stl_path), validate=validate)
                if not result.success:
                    errors.extend([f"STL: {e}" for e in result.validation_errors])
                else:
                    exported_files["stl"] = stl_path
                    warnings.extend([f"STL: {w}" for w in result.warnings])
            
            if include_3mf:
                mf_path = tmpdir_path / f"{base_name}.3mf"
                result = export_3mf(part, str(mf_path), validate=validate)
                if not result.success:
                    errors.extend([f"3MF: {e}" for e in result.validation_errors])
                else:
                    exported_files["3mf"] = mf_path
                    warnings.extend([f"3MF: {w}" for w in result.warnings])
            
            # Generate dimension report
            report = generate_dimension_report(part, part_spec)
            report_path = tmpdir_path / "dimension_report.json"
            with open(report_path, "w", encoding="utf-8", newline="\n") as f:
                json.dump(report, f, indent=2)
            exported_files["report"] = report_path
            
            # Generate print guide
            guide = generate_print_guide(part, settings)
            guide_path = tmpdir_path / "print_guide.md"
            with open(guide_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(guide)
            exported_files["guide"] = guide_path
            
            # Create ZIP
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for name, path in exported_files.items():
                    zf.write(path, path.name)
            
            file_size = os.path.getsize(zip_path)
            success = len(errors) == 0
            
    except Exception as e:
        errors.append(f"ZIP bundle creation failed: {str(e)}")
        success = False
    
    return ExportResult(
        success=success,
        file_path=zip_path,
        format="ZIP",
        file_size=file_size,
        validation_errors=errors,
        warnings=warnings,
    )


def validate_export(part: Part, formats: List[str] = None) -> dict:
    """
    Validate a part by exporting to multiple formats and checking.
    
    Args:
        part: build123d Part to validate
        formats: List of formats to test (default: ["step", "stl"])
        
    Returns:
        Dictionary with validation results per format
    """
    if formats is None:
        formats = ["step", "stl"]
    
    results = {}
    
    with tempfile.TemporaryDirectory() as tmpdir:
        for fmt in formats:
            if fmt.lower() == "step":
                path = os.path.join(tmpdir, "validation.step")
                result = export_step(part, path, validate=True)
            elif fmt.lower() == "stl":
                path = os.path.join(tmpdir, "validation.stl")
                result = export_stl(part, path, validate=True)
            elif fmt.lower() == "3mf":
                path = os.path.join(tmpdir, "validation.3mf")
                result = export_3mf(part, path, validate=True)
            else:
                results[fmt] = {"error": f"Unknown format: {fmt}"}
                continue
            
            results[fmt] = {
                "success": result.success,
                "file_size": result.file_size,
                "errors": result.validation_errors,
                "warnings": result.warnings,
            }
    
    return results


def check_export_blockers(part_spec: Optional[Dict[str, Any]] = None) -> List[str]:
    """
    Check for export blockers (L-05: unconfirmed defaults, L-06: sprocket previews).
    
    Args:
        part_spec: Optional PartSpec dictionary
        
    Returns:
        List of blocker messages (empty if no blockers)
    """
    blockers = []
    
    if part_spec:
        # L-05: Check for unconfirmed defaults
        features = part_spec.get("features", [])
        for feature in features:
            params = feature.get("parameters", {})
            for param_name, param_data in params.items():
                if isinstance(param_data, dict):
                    source = param_data.get("source", "")
                    confirmed = param_data.get("confirmed", False)
                    if source == "default" and not confirmed:
                        blockers.append(
                            f"Export blocked: Parameter '{param_name}' in feature '{feature.get('name', feature.get('id', 'unknown'))}' "
                            f"uses an unconfirmed default value. Please confirm all default values before export."
                        )
        
        # L-06: Check for sprocket previews
        for feature in features:
            feature_type = feature.get("type", "")
            feature_name = feature.get("name", "").lower()
            feature_id = feature.get("id", "").lower()
            if "sprocket" in feature_type.lower() or "sprocket" in feature_name or "sprocket" in feature_id:
                blockers.append(
                    f"Export blocked: Sprocket feature '{feature.get('name', feature.get('id', 'unknown'))}' "
                    f"is a preview only and not engagement-certified (ISO 606 tooth form not built). "
                    f"Sprocket outputs are labelled and export is refused."
                )
    
    return blockers


def _validate_step(file_path: str) -> tuple[List[str], List[str]]:
    """Validate STEP file."""
    errors = []
    warnings = []
    
    try:
        # Check file exists and has content
        if not os.path.exists(file_path):
            errors.append("STEP file not created")
            return errors, warnings
        
        if os.path.getsize(file_path) == 0:
            errors.append("STEP file is empty")
            return errors, warnings
        
        # Basic content check - STEP files should have header
        with open(file_path, 'r') as f:
            header = f.read(100)
            if "ISO-10303" not in header and "STEP" not in header.upper():
                warnings.append("STEP file may not have standard header")
        
    except Exception as e:
        errors.append(f"STEP validation error: {str(e)}")
    
    return errors, warnings


def _validate_stl(file_path: str) -> tuple[List[str], List[str]]:
    """Validate exported STL as a non-empty, watertight, positive-volume solid."""
    errors: List[str] = []
    warnings: List[str] = []

    try:
        if not os.path.isfile(file_path):
            return ["STL file not created"], warnings
        if os.path.getsize(file_path) == 0:
            return ["STL file is empty"], warnings

        mesh = trimesh.load(file_path, force="mesh")
        if mesh.is_empty:
            return ["STL mesh is empty"], warnings
        if len(mesh.faces) == 0 or len(mesh.vertices) == 0:
            return ["STL has no usable triangles or vertices"], warnings
        if not np.isfinite(np.asarray(mesh.vertices)).all():
            errors.append("STL contains non-finite vertex coordinates.")
        if not mesh.is_watertight:
            errors.append("STL mesh is not watertight; open edges make it unsafe to treat as a printable solid.")
        if not mesh.is_winding_consistent:
            errors.append("STL face winding is inconsistent.")
        if not np.isfinite(float(mesh.volume)) or float(mesh.volume) <= 0:
            errors.append("STL has zero, negative, or non-finite volume.")
        face_areas = np.asarray(mesh.area_faces)
        degenerate_count = int(np.count_nonzero(face_areas < 1e-10))
        if degenerate_count:
            errors.append(f"STL has {degenerate_count} degenerate or near-zero-area faces.")

        # Manifold3d is a required project dependency. Treat failure to establish
        # manifold validity as a validation error rather than silently approving it.
        vertices = np.asarray(mesh.vertices, dtype=np.float32, order="C")
        faces = np.asarray(mesh.faces, dtype=np.uint32, order="C")
        manifold_mesh = manifold3d.Mesh(vert_properties=vertices, tri_verts=faces)
        manifold = manifold3d.Manifold(manifold_mesh)
        status = manifold.status()
        if status != manifold3d.Error.NoError:
            errors.append(f"Manifold3d rejected the STL mesh: {status}")
        if manifold.is_empty():
            errors.append("Manifold3d reports an empty solid.")
        else:
            manifold_volume = float(manifold.volume())
            if not np.isfinite(manifold_volume) or manifold_volume <= 0:
                errors.append("Manifold3d reports non-positive or non-finite volume.")
    except Exception as exc:
        errors.append(f"STL validation error: {exc}")

    return errors, warnings


def _validate_3mf(file_path: str) -> tuple[List[str], List[str]]:
    """Validate 3MF file."""
    errors = []
    warnings = []
    
    try:
        if not os.path.isfile(file_path):
            return ["3MF file not created"], warnings
        if os.path.getsize(file_path) == 0:
            return ["3MF file is empty"], warnings
        
        # Try to load with trimesh
        mesh = trimesh.load(file_path, force="mesh")
        if mesh.is_empty:
            return ["3MF mesh is empty"], warnings
        if len(mesh.faces) == 0 or len(mesh.vertices) == 0:
            return ["3MF has no usable triangles or vertices"], warnings
        if not np.isfinite(np.asarray(mesh.vertices)).all():
            errors.append("3MF contains non-finite vertex coordinates.")
        if not mesh.is_watertight:
            errors.append("3MF mesh is not watertight.")
        if not np.isfinite(float(mesh.volume)) or float(mesh.volume) <= 0:
            errors.append("3MF has zero, negative, or non-finite volume.")
            
    except Exception as exc:
        errors.append(f"3MF validation error: {exc}")
    
    return errors, warnings
