"""
Validation module for geometry and specification validation.
"""

from typing import List, Dict, Any, Optional
import math
from dataclasses import dataclass
from enum import Enum

from ..spec.models import PartSpec, FeatureSpec, PrimitiveType


class ValidationSeverity(str, Enum):
    """Severity levels for validation issues."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """A single validation issue."""
    severity: ValidationSeverity
    code: str
    message: str
    feature_id: Optional[str] = None
    field: Optional[str] = None
    suggestion: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of validation."""
    is_valid: bool
    issues: List[ValidationIssue]
    
    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.ERROR]
    
    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]
    
    @property
    def infos(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.INFO]


class SpecValidator:
    """Validates PartSpec for correctness and manufacturability."""
    
    # Minimum feature size in mm
    MIN_FEATURE_SIZE = 0.1
    # Maximum aspect ratio
    MAX_ASPECT_RATIO = 1000
    
    def validate(self, spec: PartSpec) -> ValidationResult:
        """Validate a complete part specification."""
        issues = []
        
        # Basic spec validation
        issues.extend(self._validate_spec_basic(spec))
        
        # Feature validation
        for feature in spec.features:
            issues.extend(self._validate_feature(feature, spec))
        
        # Cross-feature validation
        issues.extend(self._validate_cross_features(spec))
        
        is_valid = len([i for i in issues if i.severity == ValidationSeverity.ERROR]) == 0
        
        return ValidationResult(is_valid=is_valid, issues=issues)
    
    def _validate_spec_basic(self, spec: PartSpec) -> List[ValidationIssue]:
        issues = []
        
        if not spec.name or not spec.name.strip():
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="SPEC_EMPTY_NAME",
                message="Part name cannot be empty",
                field="name",
                suggestion="Provide a descriptive name for the part"
            ))
        
        if not spec.features:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="SPEC_NO_FEATURES",
                message="Part must have at least one feature",
                field="features",
                suggestion="Add at least one primitive feature"
            ))
        
        # Check for duplicate IDs
        ids = [f.id for f in spec.features]
        if len(ids) != len(set(ids)):
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="SPEC_DUPLICATE_IDS",
                message="Duplicate feature IDs found",
                field="features",
                suggestion="Ensure each feature has a unique ID"
            ))
        
        return issues
    
    def _validate_feature(self, feature: FeatureSpec, spec: PartSpec) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        required_params = {
            PrimitiveType.BOX: ["width", "depth", "height"],
            PrimitiveType.CYLINDER: ["radius", "height"],
            PrimitiveType.SPHERE: ["radius"],
            PrimitiveType.CONE: ["radius_bottom", "radius_top", "height"],
            PrimitiveType.TORUS: ["major_radius", "minor_radius"],
            PrimitiveType.WEDGE: ["width", "depth", "height"],
        }

        # Check every supplied value for finiteness, including optional parameters.
        # NaN/Infinity can bypass ordinary <= / >= checks and destabilize CAD kernels.
        for param_name, param in feature.parameters.items():
            if not math.isfinite(param.value):
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="FEATURE_NON_FINITE_PARAM",
                    message=f"Parameter '{param_name}' must be finite.",
                    feature_id=feature.id,
                    field=f"parameters.{param_name}",
                    suggestion="Replace NaN/Infinity with a concrete dimension.",
                ))

        for param_name in required_params.get(feature.type, []):
            if param_name not in feature.parameters:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code=f"FEATURE_MISSING_PARAM_{param_name.upper()}",
                    message=f"Feature '{feature.name or feature.id}' ({feature.type.value}) missing required parameter: {param_name}",
                    feature_id=feature.id,
                    field=f"parameters.{param_name}",
                    suggestion=f"Add {param_name} with a valid value.",
                ))
                continue

            param = feature.parameters[param_name]
            if not math.isfinite(param.value):
                # Already reported above, but don't issue a secondary range warning.
                continue

            # A cone may legitimately have a zero top radius. Every other required
            # dimension must be strictly positive.
            allow_zero = feature.type == PrimitiveType.CONE and param_name == "radius_top"
            invalid = param.value < 0 or (param.value == 0 and not allow_zero)
            if invalid:
                expectation = "non-negative" if allow_zero else "positive"
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code=f"FEATURE_INVALID_PARAM_{param_name.upper()}",
                    message=f"Parameter '{param_name}' must be {expectation}, got {param.value}.",
                    feature_id=feature.id,
                    field=f"parameters.{param_name}",
                    suggestion=f"Set {param_name} to a {expectation} value.",
                ))
            elif 0 < param.value < self.MIN_FEATURE_SIZE:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    code=f"FEATURE_SMALL_PARAM_{param_name.upper()}",
                    message=f"Parameter '{param_name}' = {param.value} {param.unit.value} is very small (recommended minimum: {self.MIN_FEATURE_SIZE} mm).",
                    feature_id=feature.id,
                    field=f"parameters.{param_name}",
                    suggestion="Confirm that this feature is manufacturable in the intended process.",
                ))

        for field_name, vector in (("position", feature.position), ("rotation", feature.rotation)):
            if len(vector) != 3:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code=f"FEATURE_INVALID_{field_name.upper()}",
                    message=f"{field_name.title()} must have 3 values, got {len(vector)}.",
                    feature_id=feature.id,
                    field=field_name,
                ))
            elif any(not math.isfinite(float(value)) for value in vector):
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code=f"FEATURE_NON_FINITE_{field_name.upper()}",
                    message=f"All {field_name} values must be finite.",
                    feature_id=feature.id,
                    field=field_name,
                ))

        if feature.type == PrimitiveType.TORUS:
            major = feature.parameters.get("major_radius")
            minor = feature.parameters.get("minor_radius")
            if major and minor and math.isfinite(major.value) and math.isfinite(minor.value):
                if major.to_mm() <= minor.to_mm():
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        code="TORUS_INVALID_RADII",
                        message="Torus major radius must be greater than its minor radius to avoid a self-intersecting/spindle torus.",
                        feature_id=feature.id,
                        field="parameters",
                        suggestion="Use an outer and inner diameter that define a ring-shaped torus.",
                    ))

        if feature.type == PrimitiveType.CONE:
            bottom = feature.parameters.get("radius_bottom")
            top = feature.parameters.get("radius_top")
            if bottom and top and math.isfinite(bottom.value) and math.isfinite(top.value):
                if top.to_mm() >= bottom.to_mm():
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        code="CONE_INVALID_RADII",
                        message="Cone top radius must be smaller than its base radius.",
                        feature_id=feature.id,
                        field="parameters",
                    ))

        if feature.type == PrimitiveType.WEDGE:
            for lower_name, upper_name in (("xmin", "xmax"), ("zmin", "zmax")):
                lower = feature.parameters.get(lower_name)
                upper = feature.parameters.get(upper_name)
                if lower and upper and math.isfinite(lower.value) and math.isfinite(upper.value):
                    if lower.to_mm() >= upper.to_mm():
                        issues.append(ValidationIssue(
                            severity=ValidationSeverity.ERROR,
                            code="WEDGE_INVALID_EXTENTS",
                            message=f"Wedge {lower_name} must be less than {upper_name}.",
                            feature_id=feature.id,
                            field="parameters",
                        ))

        return issues

    def _validate_cross_features(self, spec: PartSpec) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        feature_ids = {feature.id for feature in spec.features}

        if spec.features and spec.features[0].operation.value != "union":
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="FEATURE_BASE_OPERATION",
                message="The first feature must use union to establish the base solid.",
                feature_id=spec.features[0].id,
                field="features[0].operation",
                suggestion="Make the first feature a base solid, then apply cuts/intersections.",
            ))

        for feature in spec.features:
            if feature.parent_id and feature.parent_id not in feature_ids:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="FEATURE_INVALID_PARENT",
                    message=f"Feature '{feature.id}' references non-existent parent '{feature.parent_id}'.",
                    feature_id=feature.id,
                    field="parent_id",
                ))

        # Detect parent cycles. They cannot define a meaningful feature history and
        # are often a sign that a generated specification is malformed.
        parents = {feature.id: feature.parent_id for feature in spec.features}
        visited: set[str] = set()
        active: set[str] = set()

        def visit(feature_id: str) -> bool:
            if feature_id in active:
                return False
            if feature_id in visited:
                return True
            active.add(feature_id)
            parent_id = parents.get(feature_id)
            if parent_id in parents and not visit(parent_id):
                return False
            active.remove(feature_id)
            visited.add(feature_id)
            return True

        for feature in spec.features:
            if not visit(feature.id):
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="FEATURE_PARENT_CYCLE",
                    message="Feature parent references contain a cycle.",
                    feature_id=feature.id,
                    field="parent_id",
                    suggestion="Remove cyclic parent references.",
                ))
                break

        return issues


class GeometryValidator:
    """Validates generated geometry for manufacturability."""
    
    def __init__(self):
        self.min_wall_thickness = 0.4  # mm for FDM
        self.max_overhang_angle = 45  # degrees
    
    def validate_part(self, part) -> ValidationResult:
        """Validate a build123d Part."""
        issues = []
        
        try:
            # Check if part is valid
            if part is None:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="GEOM_NULL_PART",
                    message="Part is None",
                ))
                return ValidationResult(is_valid=False, issues=issues)
            
            # Check the kernel's own topological validity when exposed by the shape.
            validity = getattr(part, "is_valid", None)
            try:
                is_valid = validity() if callable(validity) else validity
                if is_valid is False:
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        code="GEOM_TOPOLOGY_INVALID",
                        message="The CAD kernel reports that this shape is topologically invalid.",
                        suggestion="Revise feature dimensions/placements and regenerate the model.",
                    ))
            except Exception as e:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    code="GEOM_TOPOLOGY_CHECK_FAILED",
                    message=f"Could not query kernel topology validity: {e}",
                ))

            # Check volume
            try:
                volume = part.volume
                if volume <= 0:
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        code="GEOM_ZERO_VOLUME",
                        message="Part has zero or negative volume",
                    ))
                elif volume < 1.0:  # mm^3
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        code="GEOM_SMALL_VOLUME",
                        message=f"Part volume is very small: {volume:.3f} mm³",
                    ))
            except Exception as e:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    code="GEOM_VOLUME_ERROR",
                    message=f"Could not compute volume: {str(e)}",
                ))
            
            # Check bounding box
            try:
                bbox = part.bounding_box()
                size = bbox.size
                min_dim = min(size.X, size.Y, size.Z)
                max_dim = max(size.X, size.Y, size.Z)
                
                if min_dim < self.min_wall_thickness:
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        code="GEOM_THIN_FEATURE",
                        message=f"Part has very thin dimension: {min_dim:.3f}mm (min recommended: {self.min_wall_thickness}mm)",
                        suggestion="Consider increasing wall thickness for manufacturability"
                    ))
                
                aspect_ratio = max_dim / min_dim if min_dim > 0 else float('inf')
                if aspect_ratio > 1000:
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        code="GEOM_HIGH_ASPECT_RATIO",
                        message=f"Part has high aspect ratio: {aspect_ratio:.1f}:1",
                        suggestion="Consider if this geometry is suitable for manufacturing"
                    ))
            except Exception as e:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.INFO,
                    code="GEOM_BBOX_ERROR",
                    message=f"Could not compute bounding box: {str(e)}",
                ))
            
        except Exception as e:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="GEOM_VALIDATION_ERROR",
                message=f"Geometry validation failed: {str(e)}",
            ))
        
        is_valid = len([i for i in issues if i.severity == ValidationSeverity.ERROR]) == 0
        return ValidationResult(is_valid=is_valid, issues=issues)


def validate_spec(spec: PartSpec) -> ValidationResult:
    """Convenience function to validate a spec."""
    return SpecValidator().validate(spec)


def validate_geometry(part) -> ValidationResult:
    """Convenience function to validate geometry."""
    return GeometryValidator().validate_part(part)
