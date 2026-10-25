"""
Export module for STEP, STL, and other formats with validation.
"""

import os
import tempfile
from dataclasses import dataclass
from typing import Optional, List
from pathlib import Path

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
