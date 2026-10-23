"""
Validation module for geometry and specification validation.
"""

from typing import List, Dict, Any, Optional
from math import isfinite
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
        issues = []
        
        # Check required parameters for each primitive type
        required_params = {
            PrimitiveType.BOX: ["width", "depth", "height"],
            PrimitiveType.CYLINDER: ["radius", "height"],
            PrimitiveType.SPHERE: ["radius"],
            PrimitiveType.CONE: ["radius_bottom", "radius_top", "height"],
            PrimitiveType.TORUS: ["major_radius", "minor_radius"],
            PrimitiveType.WEDGE: ["width", "depth", "height"],
        }
        
        if feature.type in required_params:
            for param_name in required_params[feature.type]:
                if param_name not in feature.parameters:
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        code=f"FEATURE_MISSING_PARAM_{param_name.upper()}",
                        message=f"Feature '{feature.name or feature.id}' ({feature.type.value}) missing required parameter: {param_name}",
                        feature_id=feature.id,
                        field=f"parameters.{param_name}",
                        suggestion=f"Add {param_name} parameter with a positive value"
                    ))
                else:
                    param = feature.parameters[param_name]
                    if not isfinite(float(param.value)):
                        issues.append(ValidationIssue(
                            severity=ValidationSeverity.ERROR,
                            code=f"FEATURE_NON_FINITE_PARAM_{param_name.upper()}",
                            message=f"Parameter '{param_name}' must be finite, got {param.value}",
                            feature_id=feature.id,
                            field=f"parameters.{param_name}",
                            suggestion="Use a finite numeric value."
                        ))
                    elif param.value < 0 or (param.value == 0 and not (
                        feature.type == PrimitiveType.CONE and param_name == "radius_top"
                    )):
                        issues.append(ValidationIssue(
                            severity=ValidationSeverity.ERROR,
                            code=f"FEATURE_INVALID_PARAM_{param_name.upper()}",
                            message=f"Parameter '{param_name}' must be positive, got {param.value}",
                            feature_id=feature.id,
                            field=f"parameters.{param_name}",
                            suggestion=f"Set {param_name} to a positive value"
                        ))
                    elif param.value > 0 and param.value < self.MIN_FEATURE_SIZE:
                        issues.append(ValidationIssue(
                            severity=ValidationSeverity.WARNING,
                            code=f"FEATURE_SMALL_PARAM_{param_name.upper()}",
                            message=f"Parameter '{param_name}' = {param.value}mm is very small (min recommended: {self.MIN_FEATURE_SIZE}mm)",
                            feature_id=feature.id,
                            field=f"parameters.{param_name}",
                            suggestion="Consider if this feature size is manufacturable"
                        ))
        
        # Validate position/rotation arrays
        if len(feature.position) != 3:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="FEATURE_INVALID_POSITION",
                message=f"Position must have 3 values, got {len(feature.position)}",
                feature_id=feature.id,
                field="position",
            ))
        
        if len(feature.rotation) != 3:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="FEATURE_INVALID_ROTATION",
                message=f"Rotation must have 3 values, got {len(feature.rotation)}",
                feature_id=feature.id,
                field="rotation",
            ))
        
        return issues
    
    def _validate_cross_features(self, spec: PartSpec) -> List[ValidationIssue]:
        issues = []
        
        # Check for features that reference non-existent parents
        feature_ids = {f.id for f in spec.features}
        for feature in spec.features:
            if feature.parent_id and feature.parent_id not in feature_ids:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="FEATURE_INVALID_PARENT",
                    message=f"Feature '{feature.id}' references non-existent parent '{feature.parent_id}'",
                    feature_id=feature.id,
                    field="parent_id",
                ))
        
        # Check for circular dependencies (simplified)
        # This would need a proper graph traversal for full detection
        
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
            
            # Ask OpenCascade whether the B-rep is topologically valid when supported.
            try:
                validity = getattr(part, "is_valid", None)
                if callable(validity):
                    validity = validity()
                if validity is False:
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        code="GEOM_INVALID_BREP",
                        message="CAD kernel reports an invalid boundary representation.",
                        suggestion="Review boolean operations, profile wires, and coincident faces."
                    ))
            except Exception as exc:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    code="GEOM_VALIDITY_CHECK_ERROR",
                    message=f"Could not query CAD-kernel validity: {exc}",
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
