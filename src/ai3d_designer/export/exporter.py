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
    """Validate STL file using trimesh and manifold3d."""
    errors = []
    warnings = []
    
    try:
        if not os.path.exists(file_path):
            errors.append("STL file not created")
            return errors, warnings
        
        if os.path.getsize(file_path) == 0:
            errors.append("STL file is empty")
            return errors, warnings
        
        # Load with trimesh
        mesh = trimesh.load(file_path, force='mesh')
        
        if mesh.is_empty:
            errors.append("STL mesh is empty")
            return errors, warnings
        
        # Check for degenerate faces
        if len(mesh.faces) == 0:
            errors.append("STL has no faces")
        
        # Check for non-manifold edges
        if not mesh.is_watertight:
            warnings.append("STL mesh is not watertight (may have open edges)")
        
        # Check for degenerate triangles
        face_areas = mesh.area_faces
        if len(face_areas) > 0:
            degenerate_count = sum(1 for a in face_areas if a < 1e-10)
            if degenerate_count > 0:
                warnings.append(f"STL has {degenerate_count} degenerate faces")
        
        # Validate with manifold3d - convert arrays to proper format
        try:
            vertices = np.asarray(mesh.vertices, dtype=np.float32, order='C')
            faces = np.asarray(mesh.faces, dtype=np.uint32, order='C')
            
            m3d_mesh = manifold3d.Mesh(vert_properties=vertices, tri_verts=faces)
            manifold = manifold3d.Manifold.from_mesh(m3d_mesh)
            
            if manifold.status() != manifold3d.Error.NoError:
                warnings.append(f"Manifold status: {manifold.status()}")
            
            # Check if manifold is valid (not empty)
            if manifold.is_empty():
                warnings.append("Manifold is empty (may indicate invalid geometry)")
            else:
                # Check volume
                vol = manifold.get_volume()
                if vol <= 0:
                    warnings.append("Manifold has zero or negative volume")
            
        except Exception as e:
            warnings.append(f"Manifold3d validation warning: {str(e)}")
        
        # Volume check from trimesh
        if mesh.volume <= 0:
            warnings.append("Mesh has zero or negative volume (trimesh)")
        
    except Exception as e:
        errors.append(f"STL validation error: {str(e)}")
    
    return errors, warnings
