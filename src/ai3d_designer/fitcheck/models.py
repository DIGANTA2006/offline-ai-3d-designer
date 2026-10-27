"""
Models for component fit checking.
Re-exports from core.spec.models for convenience.
"""

from ai3d_designer.core.spec.models import (
    ComponentSpec,
    EnclosureSpec,
    ComponentType,
    FitCheckResult,
    FitCheckReport,
    ParameterSource,
)

__all__ = [
    "ComponentSpec",
    "EnclosureSpec",
    "ComponentType",
    "FitCheckResult",
    "FitCheckReport",
    "ParameterSource",
]
