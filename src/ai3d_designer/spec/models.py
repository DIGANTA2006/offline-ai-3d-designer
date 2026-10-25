"""Compatibility imports for the canonical part-specification models.

The old package path must share the exact model classes used by the geometry
engine; a second independent schema can lead to incompatible PartSpec objects.
"""
from ..core.spec.models import (
    UnitSystem,
    PrimitiveType,
    OperationType,
    ExportFormat,
    ParameterSpec,
    FeatureSpec,
    PartSpec,
)

__all__ = [
    "UnitSystem",
    "PrimitiveType",
    "OperationType",
    "ExportFormat",
    "ParameterSpec",
    "FeatureSpec",
    "PartSpec",
]
