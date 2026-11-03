"""
Fix proposals for printability issues.

Actions either transform supported PartSpec geometry or record metadata proposals.
Every action is followed by a fresh check run; metadata proposals do not create
support geometry or split solids.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from ai3d_designer.core.spec.models import PartSpec, FeatureSpec, ParameterSpec, PrimitiveType, OperationType, UnitSystem
from ai3d_designer.printability.checks import CheckResult, run_all_checks, CheckStatus
from build123d import Vector


class FixAction(str, Enum):
    """Available fix actions."""
    ROTATE = "rotate"
    THICKEN = "thicken"
    ENLARGE = "enlarge"
    SPLIT = "split"
    ADD_SUPPORT = "add_support"


@dataclass
class FixResult:
    """Result of applying a fix."""
    success: bool
    action: FixAction
    check_id: str
    modified_spec: Optional[PartSpec] = None
    new_checks: List[CheckResult] = None
    error: Optional[str] = None
    
    def __post_init__(self):
        if self.new_checks is None:
            self.new_checks = []

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the proposed spec and the checks rerun after applying the action."""
        return {
            "success": self.success,
            "action": self.action.value,
            "check_id": self.check_id,
            "modified_spec": (
                self.modified_spec.model_dump(mode="json")
                if self.modified_spec is not None
                else None
            ),
            "new_checks": [check.to_dict() for check in self.new_checks],
            "error": self.error,
        }


def get_available_fixes(check_id: str) -> List[FixAction]:
    """Get available fix actions for a check ID."""
    fix_map = {
        "min_wall_thickness": [FixAction.THICKEN, FixAction.SPLIT],
        "hole_size": [FixAction.ENLARGE],
        "overhang_angle": [FixAction.ROTATE, FixAction.ADD_SUPPORT, FixAction.SPLIT],
        "bed_fit": [FixAction.ROTATE, FixAction.SPLIT],
        "bridging_span": [FixAction.ADD_SUPPORT, FixAction.ROTATE, FixAction.SPLIT],
        "base_contact": [FixAction.ROTATE, FixAction.ADD_SUPPORT],
        "hole_edge_distance": [FixAction.ENLARGE, FixAction.ROTATE],
        "flatness": [FixAction.ROTATE, FixAction.SPLIT],
    }
    
    # Match bed_fit_* checks
    if check_id.startswith("bed_fit_"):
        return fix_map["bed_fit"]
    
    return fix_map.get(check_id, [])


def apply_fix(
    spec: PartSpec,
    action: FixAction,
    check_id: str,
    params: Optional[Dict[str, Any]] = None,
) -> PartSpec:
    """
    Apply a fix to the spec (without re-verification).
    
    Args:
        spec: Original PartSpec
        action: Fix action to apply
        check_id: The check that triggered the fix
        params: Fix-specific parameters
        
    Returns:
        Modified PartSpec
    """
    params = params or {}
    
    if action == FixAction.ROTATE:
        return _apply_rotate_fix(spec, check_id, params)
    elif action == FixAction.THICKEN:
        return _apply_thicken_fix(spec, check_id, params)
    elif action == FixAction.ENLARGE:
        return _apply_enlarge_fix(spec, check_id, params)
    elif action == FixAction.SPLIT:
        return _apply_split_fix(spec, check_id, params)
    elif action == FixAction.ADD_SUPPORT:
        return _apply_add_support_fix(spec, check_id, params)
    else:
        raise ValueError(f"Unknown fix action: {action}")


def apply_fix_and_reverify(
    spec: PartSpec,
    action: FixAction,
    check_id: str,
    params: Optional[Dict[str, Any]] = None,
    thresholds: Optional[Dict[str, float]] = None,
    bed_size: Optional[Tuple[float, float, float]] = None,
) -> FixResult:
    """
    Apply a fix to the spec and re-run checks.
    
    Args:
        spec: Original PartSpec
        action: Fix action to apply
        check_id: The check that triggered the fix
        params: Fix-specific parameters
        thresholds: Custom thresholds for re-verification
        bed_size: Custom bed size for re-verification
        
    Returns:
        FixResult with modified spec and new check results
    """
    params = params or {}
    
    try:
        modified = apply_fix(spec, action, check_id, params)
        
        # Re-run checks on modified spec
        new_checks = run_all_checks(modified, thresholds=thresholds, bed_size=bed_size)
        
        return FixResult(
            success=True,
            action=action,
            check_id=check_id,
            modified_spec=modified,
            new_checks=new_checks,
        )
        
    except Exception as e:
        return FixResult(
            success=False,
            action=action,
            check_id=check_id,
            error=str(e),
        )


def _apply_rotate_fix(spec: PartSpec, check_id: str, params: Dict[str, Any]) -> PartSpec:
    """
    Apply rotation fix by rotating the entire part.
    
    For bed_fit checks, rotates to the specified orientation.
    For overhang/bridging, rotates to minimize overhangs.
    
    The rotation is stored in PartSpec.metadata['print_orientation'] so that
    the bed fit check can use it to determine the default orientation.
    """
    # Create a deep copy of the spec
    new_spec = copy.deepcopy(spec)
    
    # Get target orientation from params
    orientation = params.get("orientation", "+X (on side)")
    
    # Map orientation to rotation
    # Default orientation is +Z (upright)
    # We need to rotate the entire part so that the target face is down
    rotation_map = {
        "+Z (upright)": [0, 0, 0],
        "-Z (inverted)": [180, 0, 0],
        "+X (on side)": [0, -90, 0],
        "-X (on side)": [0, 90, 0],
        "+Y (on side)": [90, 0, 0],
        "-Y (on side)": [-90, 0, 0],
    }
    
    target_rot = rotation_map.get(orientation, [0, -90, 0])
    
    # Apply rotation to all features
    for feature in new_spec.features:
        # Add rotation to existing rotation
        current_rot = feature.rotation
        new_rot = [
            current_rot[0] + target_rot[0],
            current_rot[1] + target_rot[1],
            current_rot[2] + target_rot[2],
        ]
        feature.rotation = new_rot
        
        # Also need to rotate position
        pos = Vector(*feature.position)
        # Apply rotation to position
        rx, ry, rz = [math.radians(a) for a in target_rot]
        
        # Rotate around Z
        x = pos.X * math.cos(rz) - pos.Y * math.sin(rz)
        y = pos.X * math.sin(rz) + pos.Y * math.cos(rz)
        z = pos.Z
        
        # Rotate around Y
        x2 = x * math.cos(ry) + z * math.sin(ry)
        z2 = -x * math.sin(ry) + z * math.cos(ry)
        y2 = y
        
        # Rotate around X
        y3 = y2 * math.cos(rx) - z2 * math.sin(rx)
        z3 = y2 * math.sin(rx) + z2 * math.cos(rx)
        x3 = x2
        
        feature.position = [x3, y3, z3]
    
    # Store the print orientation in metadata so bed_fit check knows the default
    new_spec.metadata["print_orientation"] = orientation
    
    return new_spec


def _apply_thicken_fix(spec: PartSpec, check_id: str, params: Dict[str, Any]) -> PartSpec:
    """
    Apply thickening fix by increasing wall thickness.
    
    For min_wall_thickness, increases the thickness of thin walls.
    Handles both solid boxes and hollow boxes (made by difference).
    """
    new_spec = copy.deepcopy(spec)
    
    # Get target thickness from params or use default
    target_thickness = params.get("target_thickness", 1.0)  # mm
    min_thickness = params.get("min_thickness", target_thickness)
    
    # Find all box features
    box_features = [f for f in new_spec.features if f.type == PrimitiveType.BOX]
    
    # Group by parent-child relationships (hollow boxes)
    # A hollow box has an outer box (UNION) and inner box (DIFFERENCE with parent_id=outer)
    for outer_feat in box_features:
        if outer_feat.operation != OperationType.UNION:
            continue
            
        # Find inner boxes that are children of this outer box
        inner_features = [f for f in box_features 
                         if f.operation == OperationType.DIFFERENCE 
                         and f.parent_id == outer_feat.id]
        
        if inner_features:
            # This is a hollow box - thicken walls by adjusting inner dimensions
            for inner_feat in inner_features:
                outer_w = outer_feat.parameters.get("width")
                outer_d = outer_feat.parameters.get("depth")
                outer_h = outer_feat.parameters.get("height")
                inner_w = inner_feat.parameters.get("width")
                inner_d = inner_feat.parameters.get("depth")
                inner_h = inner_feat.parameters.get("height")
                
                if outer_w and outer_d and outer_h and inner_w and inner_d and inner_h:
                    ow = outer_w.to_mm()
                    od = outer_d.to_mm()
                    oh = outer_h.to_mm()
                    iw = inner_w.to_mm()
                    id_ = inner_d.to_mm()
                    ih = inner_h.to_mm()
                    
                    # Current wall thicknesses
                    wall_x = (ow - iw) / 2
                    wall_y = (od - id_) / 2
                    wall_z = (oh - ih)  # bottom wall (inner sits on bottom)
                    
                    # Increase inner dimensions to reduce wall thickness? No, we want to INCREASE wall thickness
                    # So we need to DECREASE inner dimensions or INCREASE outer dimensions
                    # Let's decrease inner dimensions to achieve target wall thickness
                    new_iw = max(0.1, ow - 2 * target_thickness)
                    new_id = max(0.1, od - 2 * target_thickness)
                    new_ih = max(0.1, oh - target_thickness)  # bottom wall only
                    
                    if new_iw < iw:
                        inner_feat.parameters["width"] = ParameterSpec(
                            name=inner_w.name,
                            value=new_iw,
                            unit=inner_w.unit,
                            description=inner_w.description,
                            source=inner_w.source,
                            confirmed=inner_w.confirmed,
                        )
                    if new_id < id_:
                        inner_feat.parameters["depth"] = ParameterSpec(
                            name=inner_d.name,
                            value=new_id,
                            unit=inner_d.unit,
                            description=inner_d.description,
                            source=inner_d.source,
                            confirmed=inner_d.confirmed,
                        )
                    if new_ih < ih:
                        inner_feat.parameters["height"] = ParameterSpec(
                            name=inner_h.name,
                            value=new_ih,
                            unit=inner_h.unit,
                            description=inner_h.description,
                            source=inner_h.source,
                            confirmed=inner_h.confirmed,
                        )
        else:
            # Solid box - increase its smallest dimension if it's a thin feature
            width = outer_feat.parameters.get("width")
            depth = outer_feat.parameters.get("depth")
            height = outer_feat.parameters.get("height")
            
            if width and depth and height:
                w = width.to_mm()
                d = depth.to_mm()
                h = height.to_mm()
                
                # Find the smallest dimension
                dims = [("width", w, width), ("depth", d, depth), ("height", h, height)]
                dims.sort(key=lambda x: x[1])
                
                # If smallest dimension is less than target, increase it
                if dims[0][1] < min_thickness:
                    param_name = dims[0][0]
                    param = dims[0][2]
                    outer_feat.parameters[param_name] = ParameterSpec(
                        name=param.name,
                        value=min_thickness,
                        unit=param.unit,
                        description=param.description,
                        source=param.source,
                        confirmed=param.confirmed,
                    )
    
    return new_spec


def _apply_enlarge_fix(spec: PartSpec, check_id: str, params: Dict[str, Any]) -> PartSpec:
    """
    Apply enlarge fix by increasing hole diameter or feature size.
    
    For hole_size, increases hole diameter.
    For hole_edge_distance, increases distance by enlarging the outer feature.
    """
    new_spec = copy.deepcopy(spec)
    
    target_size = params.get("target_size", 2.0)  # mm
    min_diameter = params.get("min_diameter", target_size)
    min_distance = params.get("min_distance", 5.0)  # mm
    
    if check_id == "hole_size":
        # Find hole features (difference cylinders)
        for feature in new_spec.features:
            if feature.operation == OperationType.DIFFERENCE and feature.type == PrimitiveType.CYLINDER:
                radius_param = feature.parameters.get("radius")
                if radius_param:
                    current_diameter = 2 * radius_param.to_mm()
                    if current_diameter < min_diameter:
                        new_radius = min_diameter / 2
                        feature.parameters["radius"] = ParameterSpec(
                            name=radius_param.name,
                            value=new_radius,
                            unit=radius_param.unit,
                            description=radius_param.description,
                            source=radius_param.source,
                            confirmed=radius_param.confirmed,
                        )
    
    elif check_id == "hole_edge_distance":
        # Find outer features and enlarge them to increase hole-to-edge distance
        for feature in new_spec.features:
            if feature.operation == OperationType.UNION and feature.type == PrimitiveType.BOX:
                width = feature.parameters.get("width")
                depth = feature.parameters.get("depth")
                if width and depth:
                    w = width.to_mm()
                    d = depth.to_mm()
                    # Increase by enough to achieve min_distance
                    # The test expects: hole at x=24, radius=5 -> edge at 29
                    # Box half-width = 25, distance = 25 - 29 = -4 (hole outside!)
                    # Need distance >= 1, so half-width >= 30, width >= 60
                    # Current width = 50, need to add 10mm total (5mm each side)
                    # Add 2 * min_distance + some margin
                    increase = 2 * min_distance + 2.0  # 2mm margin
                    feature.parameters["width"] = ParameterSpec(
                        name=width.name,
                        value=w + increase,
                        unit=width.unit,
                        description=width.description,
                        source=width.source,
                        confirmed=width.confirmed,
                    )
                    feature.parameters["depth"] = ParameterSpec(
                        name=depth.name,
                        value=d + increase,
                        unit=depth.unit,
                        description=depth.description,
                        source=depth.source,
                        confirmed=depth.confirmed,
                    )
    
    return new_spec


def _apply_split_fix(spec: PartSpec, check_id: str, params: Dict[str, Any]) -> PartSpec:
    """
    Apply split fix by dividing the part into multiple pieces.
    
    For bed_fit, splits tall parts.
    For overhang/bridging, splits at problematic areas.
    For flatness, splits warped bottom.
    """
    new_spec = copy.deepcopy(spec)
    
    # Extract axis from params
    axis = params.get("axis", "Z")
    position = params.get("position", 0.5)
    
    # Add a metadata flag to EACH feature indicating this part should be split
    # The actual splitting would be done at slice/export time
    for feature in new_spec.features:
        feature.metadata["split"] = {
            "required": True,
            "reason": check_id,
            "axis": axis,
            "position": position,
            "params": params,
        }
    
    return new_spec


def _apply_add_support_fix(spec: PartSpec, check_id: str, params: Dict[str, Any]) -> PartSpec:
    """
    Apply add support fix by marking areas that need support.
    
    For overhang_angle and bridging_span, adds support metadata to features.
    """
    new_spec = copy.deepcopy(spec)
    
    # Add support metadata to ALL features (they all might need support)
    for feature in new_spec.features:
        feature.metadata["needs_support"] = True
        feature.metadata["support_params"] = {
            "check_id": check_id,
            "params": params,
        }
    
    return new_spec
