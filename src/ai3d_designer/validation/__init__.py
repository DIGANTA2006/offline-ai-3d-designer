"""Compatibility exports for canonical validation types and functions."""
from ..core.validation import (
    ValidationSeverity,
    ValidationIssue,
    ValidationResult,
    SpecValidator,
    GeometryValidator,
    validate_spec,
    validate_geometry,
)

__all__ = [
    "ValidationSeverity",
    "ValidationIssue",
    "ValidationResult",
    "SpecValidator",
    "GeometryValidator",
    "validate_spec",
    "validate_geometry",
]
