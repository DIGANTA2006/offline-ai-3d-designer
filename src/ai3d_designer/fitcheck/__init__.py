"""
Fit check module for verifying component clearances inside enclosures.
"""

from .engine import FitCheckEngine, check_fit, FitCheckResult, FitCheckReport
from .models import ComponentSpec, EnclosureSpec, ComponentType

__all__ = [
    "FitCheckEngine",
    "check_fit",
    "FitCheckResult",
    "FitCheckReport",
    "ComponentSpec",
    "EnclosureSpec",
    "ComponentType",
]
