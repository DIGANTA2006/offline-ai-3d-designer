"""
Eight deterministic printability checks for FDM 3D printing.

Checks:
1. Minimum wall thickness
2. Hole size (minimum diameter)
3. Overhang angle
4. Bed fit in 6 orientations
5. Bridging span
6. Base contact area
7. Hole-to-edge distance
8. Flatness (planarity of bottom face)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import acos, atan2, cos, degrees, isfinite, pi, sin, sqrt
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from build123d import Axis, Box, Face, Location, Part, Plane, Pos, Rot, Vector, Compound
from build123d.topology import Shape
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy

from ai3d_designer.core.geometry.engine import create_part_from_spec
from ai3d_designer.core.spec.models import PartSpec, UnitSystem, PrimitiveType, OperationType


class CheckStatus(str, Enum):
    """Status of a printability check."""
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class CheckResult:
    """Result of a single printability check."""
    check_id: str
    name: str
    status: CheckStatus
    value: Optional[float] = None
    threshold: Optional[float] = None
    unit: str = "mm"
    details: str = ""
    affected_features: List[str] = field(default_factory=list)
    orientation: str = ""  # For bed fit checks; empty string for non-bed-fit checks

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "name": self.name,
            "status": self.status.value,
            "value": self.value,
            "threshold": self.threshold,
            "unit": self.unit,
            "details": self.details,
            "affected_features": self.affected_features,
            "orientation": self.orientation,
        }


class PrintabilityChecker:
    """
    Runs 8 deterministic printability checks on a PartSpec.
    
    All checks return results including passes, with clear thresholds
    and affected feature references.
    """
    
    # Default thresholds (can be overridden)
    DEFAULT_THRESHOLDS = {
        "min_wall_thickness": 0.8,      # mm - minimum printable wall
        "min_hole_diameter": 2.0,       # mm - minimum reliable hole
        "max_overhang_angle": 45.0,     # degrees - without support
        "min_bridging_span": 5.0,       # mm - max bridge without support
        "min_base_contact_area": 20.0,  # mm² - minimum bed adhesion
        "min_hole_edge_distance": 1.0,  # mm - hole to wall edge
        "max_flatness_deviation": 0.2,  # mm - bottom face planarity
    }
    
    # Standard printer bed size (mm)
    DEFAULT_BED_SIZE = (220.0, 220.0, 250.0)  # X, Y, Z
    
    def __init__(
        self,
        thresholds: Optional[Dict[str, float]] = None,
        bed_size: Optional[Tuple[float, float, float]] = None,
    ):
        self.thresholds = {**self.DEFAULT_THRESHOLDS, **(thresholds or {})}
        self.bed_size = bed_size or self.DEFAULT_BED_SIZE
    
    def check_all(self, spec: PartSpec) -> List[CheckResult]:
        """Run all 8 printability checks on the specification."""
        # Build the part once
        try:
            part = create_part_from_spec(spec)
        except Exception as e:
            return [CheckResult(
                check_id="build_error",
                name="Geometry Build",
                status=CheckStatus.FAIL,
                details=f"Failed to build geometry: {e}",
            )]
        
        results = []
        
        # Check 1: Minimum wall thickness
        results.append(self._check_min_wall_thickness(part, spec))
        
        # Check 2: Hole size
        results.append(self._check_hole_size(part, spec))
        
        # Check 3: Overhang angle
        results.append(self._check_overhang_angle(part, spec))
        
        # Check 4: Bed fit in 6 orientations
        results.extend(self._check_bed_fit(part, spec))
        
        # Check 5: Bridging span
        results.append(self._check_bridging_span(part, spec))
        
        # Check 6: Base contact area
        results.append(self._check_base_contact(part, spec))
        
        # Check 7: Hole-to-edge distance
        results.append(self._check_hole_edge_distance(part, spec))
        
        # Check 8: Flatness
        results.append(self._check_flatness(part, spec))
        
        return results
    
    def _check_min_wall_thickness(self, part: Part, spec: PartSpec) -> CheckResult:
        """
        Check minimum wall thickness using bounding box analysis
        and face-pair distance sampling.
        """
        affected = []
        min_wall = float('inf')
        
        # Sample wall thickness by checking face pairs
        # For each face, find opposite parallel faces and measure distance
        faces = list(part.faces())
        
        for i, face1 in enumerate(faces):
            # Get face normal and center
            try:
                normal1 = face1.normal_at()
                center1 = face1.center()
            except Exception:
                continue
            
            for face2 in faces[i+1:]:
                try:
                    normal2 = face2.normal_at()
                    center2 = face2.center()
                except Exception:
                    continue
                
                # Check if faces are roughly parallel (opposite normals)
                dot = normal1.X * normal2.X + normal1.Y * normal2.Y + normal1.Z * normal2.Z
                if dot < -0.9:  # Opposite faces
                    # Distance between face centers projected on normal
                    dx = center2.X - center1.X
                    dy = center2.Y - center1.Y
                    dz = center2.Z - center1.Z
                    dist = abs(dx * normal1.X + dy * normal1.Y + dz * normal1.Z)
                    
                    if 0 < dist < min_wall:
                        min_wall = dist
                        # Find which features these faces belong to
                        affected = self._find_affected_features(spec, face1, face2)
        
        # Also check bounding box dimensions for thin features
        bbox = part.bounding_box()
        min_dim = min(bbox.size.X, bbox.size.Y, bbox.size.Z)
        if min_dim < min_wall:
            min_wall = min_dim
        
        threshold = self.thresholds["min_wall_thickness"]
        status = CheckStatus.PASS if min_wall >= threshold else CheckStatus.FAIL
        
        return CheckResult(
            check_id="min_wall_thickness",
            name="Minimum Wall Thickness",
            status=status,
            value=round(min_wall, 3) if isfinite(min_wall) else None,
            threshold=threshold,
            unit="mm",
            details=f"Thinnest wall: {min_wall:.3f} mm (minimum: {threshold} mm)" if isfinite(min_wall) else "Could not determine wall thickness",
            affected_features=affected,
        )
    
    def _check_hole_size(self, part: Part, spec: PartSpec) -> CheckResult:
        """
        Check minimum hole diameter by analyzing cylindrical faces
        and hole features in the spec.
        """
        affected = []
        min_hole = float('inf')
        
        # Check cylindrical faces in the geometry
        for face in part.faces():
            try:
                # Check if face is cylindrical
                if face.geom_type() == "cylinder":
                    # Get radius from cylinder geometry
                    radius = face.radius
                    diameter = 2 * radius
                    if diameter < min_hole:
                        min_hole = diameter
                        affected = self._find_affected_features(spec, face)
            except Exception:
                continue
        
        # Also check spec for explicit hole features
        for feature in spec.features:
            if feature.type.value == "cylinder" and feature.operation.value == "difference":
                # This is a hole feature
                radius_param = feature.parameters.get("radius")
                if radius_param:
                    diameter = 2 * radius_param.to_mm()
                    if diameter < min_hole:
                        min_hole = diameter
                        affected = [feature.id]
        
        threshold = self.thresholds["min_hole_diameter"]
        status = CheckStatus.PASS if min_hole >= threshold else CheckStatus.FAIL
        
        return CheckResult(
            check_id="hole_size",
            name="Minimum Hole Diameter",
            status=status,
            value=round(min_hole, 3) if isfinite(min_hole) else None,
            threshold=threshold,
            unit="mm",
            details=f"Smallest hole: {min_hole:.3f} mm (minimum: {threshold} mm)" if isfinite(min_hole) else "No holes detected",
            affected_features=affected,
        )
    
    def _check_overhang_angle(self, part: Part, spec: PartSpec) -> CheckResult:
        """
        Check maximum overhang angle by analyzing face normals
        relative to build direction (Z-axis).
        
        Overhang angle = 90° - angle from vertical.
        Vertical wall: angle from vertical = 90°, overhang = 0°
        Horizontal face (ceiling): angle from vertical = 0°, overhang = 90°
        45° overhang: angle from vertical = 45°, overhang = 45°
        
        Only faces facing UP (normal.Z > 0) are considered overhangs.
        Faces facing DOWN (normal.Z < 0) are supported by bed or previous layers.
        
        IMPORTANT: Horizontal faces at the TOP of a solid (like a box top)
        are supported by the walls below them, so they are NOT overhangs.
        We detect this by checking if there are vertical walls around
        the perimeter of the face that extend downward.
        """
        affected = []
        max_overhang = 0.0
        threshold = self.thresholds["max_overhang_angle"]
        
        # Get part's minimum Z (bed level)
        bbox = part.bounding_box()
        z_min = bbox.min.Z
        
        for face in part.faces():
            try:
                normal = face.normal_at()
                face_bbox = face.bounding_box()
                center = face.center()
                
                # Angle from vertical (Z-axis)
                # cos(angle) = |normal.Z| / |normal|
                norm_len = sqrt(normal.X**2 + normal.Y**2 + normal.Z**2)
                if norm_len == 0:
                    continue
                cos_angle = abs(normal.Z) / norm_len
                angle_from_vertical = degrees(acos(min(1.0, max(-1.0, cos_angle))))
                
                # Overhang angle = 90 - angle from vertical
                # Vertical wall (normal horizontal): angle_from_vertical = 90, overhang = 0
                # Horizontal ceiling (normal up): angle_from_vertical = 0, overhang = 90
                overhang = 90.0 - angle_from_vertical
                
                # Only consider overhangs (faces facing somewhat upward)
                # A face with normal.Z > 0 is facing up (ceiling/overhang)
                # A face with normal.Z < 0 is facing down (floor - supported by bed)
                if normal.Z > 0.1:  # Facing upward - potential overhang
                    # Check if this face is SUPPORTED from below (not a true overhang)
                    # A horizontal face at the top of a solid is supported by walls
                    supported = False
                    if normal.Z > 0.9:  # Horizontal face facing up
                        # Check if there are vertical walls around the perimeter
                        supported = self._is_top_face_supported(part, face, face_bbox)
                    
                    if not supported:
                        if overhang > max_overhang:
                            max_overhang = overhang
                            affected = self._find_affected_features(spec, face)
            except Exception:
                continue
        
        status = CheckStatus.PASS if max_overhang <= threshold else CheckStatus.WARNING
        
        return CheckResult(
            check_id="overhang_angle",
            name="Maximum Overhang Angle",
            status=status,
            value=round(max_overhang, 1),
            threshold=threshold,
            unit="degrees",
            details=f"Maximum overhang: {max_overhang:.1f}° (limit without support: {threshold}°)",
            affected_features=affected,
        )
    
    def _check_bed_fit(self, part: Part, spec: PartSpec) -> List[CheckResult]:
        """
        Check if part fits on build plate in 6 WORLD orientations:
        +X, -X, +Y, -Y, +Z, -Z (where +Z is world up / bed normal)
        
        For each orientation, rotate the part so that the specified face is down,
        compute the world-axis-aligned bounding box, and check if it fits.
        
        If spec.metadata['print_orientation'] is set, the part has already been
        rotated to that orientation by the ROTATE fix. In that case, we check
        the part AS-IS (without additional rotation) for that orientation.
        """
        results = []
        bed_x, bed_y, bed_z = self.bed_size
        
        # Get target print orientation from metadata (set by ROTATE fix)
        target_orientation = spec.metadata.get("print_orientation", "+Z (upright)")
        
        # 6 world orientations: each world axis face down on bed
        # We rotate the part so that the target world axis points down (-Z)
        orientations = [
            ("+Z (upright)",     [0, 0, 0]),
            ("-Z (inverted)",    [180, 0, 0]),
            ("+X (on side)",     [0, -90, 0]),
            ("-X (on side)",     [0, 90, 0]),
            ("+Y (on side)",     [90, 0, 0]),
            ("-Y (on side)",     [-90, 0, 0]),
        ]
        
        for orient_name, rotation in orientations:
            # If this is the target orientation and print_orientation is set,
            # the part is already rotated to this orientation by the fix.
            # Check the part AS-IS (no additional rotation).
            if orient_name == target_orientation and "print_orientation" in spec.metadata:
                rotated_part = part  # Already rotated by fix
            else:
                # Create a copy of the part rotated to this orientation
                rotated_part = self._rotate_part(part, rotation)
            
            # Get world-axis-aligned bounding box of rotated part
            bbox = rotated_part.bounding_box()
            footprint_w = bbox.size.X
            footprint_d = bbox.size.Y
            height = bbox.size.Z
            
            fits_xy = footprint_w <= bed_x and footprint_d <= bed_y
            fits_z = height <= bed_z
            fits = fits_xy and fits_z
            status = CheckStatus.PASS if fits else CheckStatus.FAIL
            
            # Create check_id with orientation - use format matching test expectations
            orient_key_map = {
                "+Z (upright)": "posZ_upright",
                "-Z (inverted)": "negZ_inverted",
                "+X (on side)": "posX_on_side",
                "-X (on side)": "negX_on_side",
                "+Y (on side)": "posY_on_side",
                "-Y (on side)": "negY_on_side",
            }
            orient_key = orient_key_map.get(orient_name, orient_name)
            
            # If this is the target orientation, mark it as primary
            is_target = (orient_name == target_orientation)
            
            results.append(CheckResult(
                check_id=f"bed_fit_{orient_key}",
                name=f"Bed Fit: {orient_name}",
                status=status,
                value=round(max(footprint_w, footprint_d, height), 1),
                threshold=round(max(bed_x, bed_y, bed_z), 1),
                unit="mm",
                details=f"Footprint: {footprint_w:.1f} × {footprint_d:.1f} mm, Height: {height:.1f} mm (bed: {bed_x} × {bed_y} × {bed_z} mm) - {'Fits' if fits else 'EXCEEDS BED'}" + (" [TARGET]" if is_target else ""),
                affected_features=[f.id for f in spec.features],
                orientation=orient_name,
            ))
        
        return results
    
    def _rotate_part(self, part: Part, rotation: List[float]) -> Part:
        """Rotate a part by Euler angles (degrees) and return new Part (copy)."""
        rx, ry, rz = rotation
        # Create rotation transform
        rot = Rot(rx, ry, rz)
        # Copy the underlying shape to avoid modifying the original
        copied_shape = BRepBuilderAPI_Copy(part.wrapped).Shape()
        # Create new Part from copied shape
        rotated_part = Part(copied_shape)
        # Apply rotation
        rotated_part.move(rot)
        return rotated_part
    
    def _check_bridging_span(self, part: Part, spec: PartSpec) -> CheckResult:
        """
        Check maximum bridging span by analyzing horizontal faces
        that are not supported from below.
        
        A bridge is a horizontal face (normal pointing up OR down) with no solid
        material directly beneath/above it within a small gap.
        
        - Upward-facing bridges: horizontal face (normal.Z > 0.9) not at bed level,
          with no support below
        - Downward-facing bridges: horizontal face (normal.Z < -0.9) not at bed level,
          with no support above (this is the actual bridge span in FDM)
        
        Excludes the bottom-most face (which sits on the bed).
        Excludes top faces of solids that are supported by walls from below.
        """
        affected = []
        max_bridge = 0.0
        threshold = self.thresholds["min_bridging_span"]
        
        # Get part's minimum Z (bed level)
        bbox = part.bounding_box()
        z_min = bbox.min.Z
        
        # Get all faces and their bounding boxes
        for face in part.faces():
            try:
                face_bbox = face.bounding_box()
                center = face.center()
                normal = face.normal_at()
                
                # Horizontal face facing UP (normal.Z > 0.9) - ceiling/overhang
                if normal.Z > 0.9:
                    # Skip bottom face (on build plate)
                    if abs(face_bbox.min.Z - z_min) < 0.1:
                        continue
                    
                    # Check if supported from below (by walls or other geometry)
                    supported = self._is_top_face_supported(part, face, face_bbox)
                    if not supported:
                        # Bridge span = max dimension of face in XY plane
                        span = max(face_bbox.size.X, face_bbox.size.Y)
                        if span > max_bridge:
                            max_bridge = span
                            affected = self._find_affected_features(spec, face)
                
                # Horizontal face facing DOWN (normal.Z < -0.9) - potential bridge
                # This is the actual bridge in FDM: a horizontal span printed in mid-air
                elif normal.Z < -0.9:
                    # Skip bottom face (on build plate)
                    if abs(face_bbox.min.Z - z_min) < 0.1:
                        continue
                    
                    # Check if supported from above (by walls or other geometry)
                    # A downward-facing face is a bridge if there's nothing above it
                    supported = self._is_bottom_face_supported(part, face, face_bbox)
                    if not supported:
                        # Bridge span = max dimension of face in XY plane
                        span = max(face_bbox.size.X, face_bbox.size.Y)
                        if span > max_bridge:
                            max_bridge = span
                            affected = self._find_affected_features(spec, face)
            except Exception:
                continue
        
        status = CheckStatus.PASS if max_bridge <= threshold else CheckStatus.WARNING
        
        return CheckResult(
            check_id="bridging_span",
            name="Maximum Bridging Span",
            status=status,
            value=round(max_bridge, 1) if max_bridge > 0 else None,
            threshold=threshold,
            unit="mm",
            details=f"Longest unsupported bridge: {max_bridge:.1f} mm (reliable limit: {threshold} mm)" if max_bridge > 0 else "No significant bridges detected",
            affected_features=affected,
        )
    
    def _check_base_contact(self, part: Part, spec: PartSpec) -> CheckResult:
        """
        Check base contact area on build plate (Z-min face).
        Sum area of all HORIZONTAL faces at minimum Z that face downward.
        Only counts faces with normal.Z < -0.9 (truly horizontal).
        """
        affected = []
        base_area = 0.0
        
        # Find faces at minimum Z
        bbox = part.bounding_box()
        z_min = bbox.min.Z
        tolerance = 0.01  # mm
        
        for face in part.faces():
            try:
                face_bbox = face.bounding_box()
                # Face touches build plate if its minimum Z is at part's minimum Z
                if abs(face_bbox.min.Z - z_min) < tolerance:
                    # This face touches the build plate
                    # Only count truly horizontal faces facing DOWN (normal.Z < -0.9)
                    normal = face.normal_at()
                    if normal.Z < -0.9:
                        area = face.area
                        base_area += area
                        affected = self._find_affected_features(spec, face)
            except Exception:
                continue
        
        threshold = self.thresholds["min_base_contact_area"]
        status = CheckStatus.PASS if base_area >= threshold else CheckStatus.WARNING
        
        return CheckResult(
            check_id="base_contact",
            name="Base Contact Area",
            status=status,
            value=round(base_area, 1),
            threshold=threshold,
            unit="mm²",
            details=f"Build plate contact: {base_area:.1f} mm² (minimum recommended: {threshold} mm²)",
            affected_features=affected,
        )
    
    def _check_hole_edge_distance(self, part: Part, spec: PartSpec) -> CheckResult:
        """
        Check minimum distance from holes to part edges.
        Uses spec features for accurate hole positions.
        """
        affected = []
        min_distance = float('inf')
        
        # Get all hole features from spec (difference cylinders)
        hole_features = [f for f in spec.features 
                        if f.operation.value == "difference" and f.type.value == "cylinder"]
        
        # Get outer boundary features (union boxes/cylinders)
        outer_features = [f for f in spec.features if f.operation.value == "union"]
        
        for hole_feat in hole_features:
            hole_center = Vector(*hole_feat.position)
            hole_radius_param = hole_feat.parameters.get("radius")
            if not hole_radius_param:
                continue
            hole_r = hole_radius_param.to_mm()
            
            # Check distance to each outer feature boundary
            for outer_feat in outer_features:
                if outer_feat.type == PrimitiveType.BOX:
                    # Box centered at position
                    cx, cy, cz = outer_feat.position
                    width = outer_feat.parameters.get("width")
                    depth = outer_feat.parameters.get("depth")
                    if width and depth:
                        w = width.to_mm()
                        d = depth.to_mm()
                        # Distance from hole center to box edges
                        dist_x = min(abs(hole_center.X - (cx - w/2)), abs(hole_center.X - (cx + w/2)))
                        dist_y = min(abs(hole_center.Y - (cy - d/2)), abs(hole_center.Y - (cy + d/2)))
                        # Distance from hole edge to wall = distance to wall - hole radius
                        edge_dist_x = dist_x - hole_r
                        edge_dist_y = dist_y - hole_r
                        dist = min(edge_dist_x, edge_dist_y)
                        if dist < min_distance:
                            min_distance = dist
                            affected = [hole_feat.id, outer_feat.id]
                
                elif outer_feat.type == PrimitiveType.CYLINDER:
                    # Outer cylinder - distance from hole to cylinder wall
                    cx, cy, cz = outer_feat.position
                    radius_param = outer_feat.parameters.get("radius")
                    if radius_param:
                        outer_r = radius_param.to_mm()
                        # Distance from hole center to cylinder center
                        center_dist = sqrt((hole_center.X - cx)**2 + (hole_center.Y - cy)**2)
                        # Distance from hole edge to outer wall
                        dist = outer_r - center_dist - hole_r
                        if dist < min_distance:
                            min_distance = dist
                            affected = [hole_feat.id, outer_feat.id]
        
        # Fallback: use geometry analysis if spec-based didn't find anything
        if min_distance == float('inf'):
            for face in part.faces():
                try:
                    if face.geom_type() == "cylinder":
                        center = face.center()
                        radius = face.radius
                        
                        bbox = part.bounding_box()
                        dist_x = min(center.X - bbox.min.X, bbox.max.X - center.X) - radius
                        dist_y = min(center.Y - bbox.min.Y, bbox.max.Y - center.Y) - radius
                        dist = min(dist_x, dist_y)
                        
                        if dist < min_distance:
                            min_distance = dist
                            affected = self._find_affected_features(spec, face)
                except Exception:
                    continue
        
        threshold = self.thresholds["min_hole_edge_distance"]
        # FAIL if hole intersects or is too close to edge (distance < threshold)
        # PASS if distance >= threshold
        status = CheckStatus.PASS if min_distance >= threshold else CheckStatus.FAIL
        
        return CheckResult(
            check_id="hole_edge_distance",
            name="Hole-to-Edge Distance",
            status=status,
            value=round(min_distance, 3) if isfinite(min_distance) else None,
            threshold=threshold,
            unit="mm",
            details=f"Minimum hole-to-edge: {min_distance:.3f} mm (minimum: {threshold} mm)" if isfinite(min_distance) else "No holes near edges detected",
            affected_features=affected,
        )
    
    def _check_flatness(self, part: Part, spec: PartSpec) -> CheckResult:
        """
        Check flatness of bottom face (planarity deviation).
        Samples Z values on ALL downward-facing faces at the bottom of the part
        and computes max deviation across all.
        """
        affected = []
        all_z_values = []
        
        # Find bottom faces - faces facing down (normal.Z < -0.5) that are at or near the bottom
        bbox = part.bounding_box()
        z_min = bbox.min.Z
        tolerance = 0.01
        
        bottom_faces = []
        for face in part.faces():
            try:
                face_bbox = face.bounding_box()
                normal = face.normal_at()
                # Bottom face: facing down (normal.Z < -0.5) and at or near minimum Z
                # Include faces within 1mm of minimum Z to catch warped bottoms
                if normal.Z < -0.5 and face_bbox.min.Z <= z_min + 1.0:
                    bottom_faces.append(face)
            except Exception:
                continue
        
        if not bottom_faces:
            return CheckResult(
                check_id="flatness",
                name="Bottom Face Flatness",
                status=CheckStatus.SKIPPED,
                details="No bottom face detected",
                affected_features=[],
            )
        
        # For each bottom face, sample points and check Z variation
        for face in bottom_faces:
            try:
                # Sample points on face: vertices + center
                vertices = list(face.vertices())
                z_values = [v.Z for v in vertices]
                face_center = face.center()
                z_values.append(face_center.Z)
                
                all_z_values.extend(z_values)
                affected = self._find_affected_features(spec, face)
            except Exception:
                continue
        
        if not all_z_values:
            return CheckResult(
                check_id="flatness",
                name="Bottom Face Flatness",
                status=CheckStatus.SKIPPED,
                details="Could not sample bottom face",
                affected_features=[],
            )
        
        # Overall deviation across all bottom faces
        z_min_all = min(all_z_values)
        z_max_all = max(all_z_values)
        max_deviation = z_max_all - z_min_all
        
        threshold = self.thresholds["max_flatness_deviation"]
        status = CheckStatus.PASS if max_deviation <= threshold else CheckStatus.WARNING
        
        return CheckResult(
            check_id="flatness",
            name="Bottom Face Flatness",
            status=status,
            value=round(max_deviation, 3),
            threshold=threshold,
            unit="mm",
            details=f"Maximum planarity deviation: {max_deviation:.3f} mm (limit: {threshold} mm)",
            affected_features=affected,
        )
    
    def _is_top_face_supported(self, part: Part, face: Face, face_bbox) -> bool:
        """
        Check if a horizontal face facing UP is the top of a solid (supported by walls).
        
        A top face is supported if there are vertical walls around its perimeter
        that extend downward. We check the four edges of the face's bounding box
        to see if there are vertical faces adjacent to them.
        """
        try:
            supported_edges = 0
            
            # X-min edge (left)
            has_vertical_wall = False
            for other_face in part.faces():
                if other_face == face:
                    continue
                try:
                    other_bbox = other_face.bounding_box()
                    other_normal = other_face.normal_at()
                    if abs(other_normal.Z) < 0.5:
                        if abs(other_bbox.min.X - face_bbox.min.X) < 0.1 or abs(other_bbox.max.X - face_bbox.min.X) < 0.1:
                            if (other_bbox.min.Y <= face_bbox.max.Y and other_bbox.max.Y >= face_bbox.min.Y):
                                if other_bbox.max.Z >= face_bbox.min.Z - 0.1:
                                    has_vertical_wall = True
                                    break
                except Exception:
                    continue
            if has_vertical_wall:
                supported_edges += 1
            
            # X-max edge (right)
            has_vertical_wall = False
            for other_face in part.faces():
                if other_face == face:
                    continue
                try:
                    other_bbox = other_face.bounding_box()
                    other_normal = other_face.normal_at()
                    if abs(other_normal.Z) < 0.5:
                        if abs(other_bbox.min.X - face_bbox.max.X) < 0.1 or abs(other_bbox.max.X - face_bbox.max.X) < 0.1:
                            if (other_bbox.min.Y <= face_bbox.max.Y and other_bbox.max.Y >= face_bbox.min.Y):
                                if other_bbox.max.Z >= face_bbox.min.Z - 0.1:
                                    has_vertical_wall = True
                                    break
                except Exception:
                    continue
            if has_vertical_wall:
                supported_edges += 1
            
            # Y-min edge (front)
            has_vertical_wall = False
            for other_face in part.faces():
                if other_face == face:
                    continue
                try:
                    other_bbox = other_face.bounding_box()
                    other_normal = other_face.normal_at()
                    if abs(other_normal.Z) < 0.5:
                        if abs(other_bbox.min.Y - face_bbox.min.Y) < 0.1 or abs(other_bbox.max.Y - face_bbox.min.Y) < 0.1:
                            if (other_bbox.min.X <= face_bbox.max.X and other_bbox.max.X >= face_bbox.min.X):
                                if other_bbox.max.Z >= face_bbox.min.Z - 0.1:
                                    has_vertical_wall = True
                                    break
                except Exception:
                    continue
            if has_vertical_wall:
                supported_edges += 1
            
            # Y-max edge (back)
            has_vertical_wall = False
            for other_face in part.faces():
                if other_face == face:
                    continue
                try:
                    other_bbox = other_face.bounding_box()
                    other_normal = other_face.normal_at()
                    if abs(other_normal.Z) < 0.5:
                        if abs(other_bbox.min.Y - face_bbox.max.Y) < 0.1 or abs(other_bbox.max.Y - face_bbox.max.Y) < 0.1:
                            if (other_bbox.min.X <= face_bbox.max.X and other_bbox.max.X >= face_bbox.min.X):
                                if other_bbox.max.Z >= face_bbox.min.Z - 0.1:
                                    has_vertical_wall = True
                                    break
                except Exception:
                    continue
            if has_vertical_wall:
                supported_edges += 1
            
            # Face is supported if it has vertical walls on at least 3 edges
            return supported_edges >= 3
        except Exception:
            pass
        return False
    
    def _is_bottom_face_supported(self, part: Part, face: Face, face_bbox) -> bool:
        """
        Determine whether a horizontal underside is backed by solid material.

        Side walls around a face do not make its underside printable: an isolated
        box has side walls too. Instead, sample points across the face and inspect
        the geometry a small distance below it. A face is treated as supported
        only when nearly all sampled interior points have material immediately
        below them. Partial support is conservatively treated as an unsupported
        bridge so an open span is not hidden by support at its edges.
        """
        try:
            size_x = float(face_bbox.size.X)
            size_y = float(face_bbox.size.Y)
            if size_x <= 0.0 or size_y <= 0.0:
                return False

            # Keep sampling bounded for large faces while using multiple interior
            # samples for ordinary print-sized geometry.
            samples_x = min(11, max(3, int(np.ceil(size_x / 5.0))))
            samples_y = min(11, max(3, int(np.ceil(size_y / 5.0))))
            z_sample = float(face.center().Z) - 0.1
            supported = 0
            tested = 0

            for ix in range(1, samples_x):
                x = float(face_bbox.min.X) + size_x * ix / samples_x
                for iy in range(1, samples_y):
                    y = float(face_bbox.min.Y) + size_y * iy / samples_y
                    point_on_face = (x, y, float(face.center().Z))
                    if not face.is_inside(point_on_face, tolerance=1e-5):
                        continue
                    tested += 1
                    if part.is_inside((x, y, z_sample), tolerance=1e-5):
                        supported += 1

            if tested == 0:
                return False

            return (supported / tested) >= 0.9
        except Exception:
            # A failed geometric probe must not silently mark a bridge as safe.
            return False

    def _find_affected_features(self, spec: PartSpec, *faces: Face) -> List[str]:
        """
        Find which features in the spec are affected by the given faces.
        Uses bounding box overlap as a heuristic.
        """
        affected = []
        
        for feature in spec.features:
            # Get feature's bounding box by creating a temporary part
            # This is a heuristic - in practice we'd track face-to-feature mapping
            try:
                # Create a temporary part with just this feature to get its bbox
                temp_spec = PartSpec(
                    name="temp",
                    description="",
                    unit_system=spec.unit_system,
                    features=[feature],
                )
                temp_part = create_part_from_spec(temp_spec)
                feat_bbox = temp_part.bounding_box()
                
                for face in faces:
                    face_bbox = face.bounding_box()
                    # Check if bounding boxes overlap significantly
                    overlap_x = max(0, min(feat_bbox.max.X, face_bbox.max.X) - max(feat_bbox.min.X, face_bbox.min.X))
                    overlap_y = max(0, min(feat_bbox.max.Y, face_bbox.max.Y) - max(feat_bbox.min.Y, face_bbox.min.Y))
                    overlap_z = max(0, min(feat_bbox.max.Z, face_bbox.max.Z) - max(feat_bbox.min.Z, face_bbox.min.Z))
                    
                    if overlap_x > 0.1 and overlap_y > 0.1 and overlap_z > 0.1:
                        affected.append(feature.id)
                        break
            except Exception:
                continue
        
        return affected


def run_all_checks(
    spec: PartSpec,
    thresholds: Optional[Dict[str, float]] = None,
    bed_size: Optional[Tuple[float, float, float]] = None,
) -> List[CheckResult]:
    """Convenience function to run all printability checks."""
    checker = PrintabilityChecker(thresholds=thresholds, bed_size=bed_size)
    return checker.check_all(spec)
