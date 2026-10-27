"""
Fit check module for verifying component clearances inside enclosures.
"""

from .engine import FitCheckEngine, check_fit, FitCheckResult, FitCheckReport
from .models import ComponentSpec, EnclosureSpec, ComponentType
from .presets import (
    STANDARD_COMPONENT_PRESETS,
    get_preset_component,
    list_hardware_presets,
    generate_enclosure_for_component,
)

__all__ = [
    "FitCheckEngine",
    "check_fit",
    "FitCheckResult",
    "FitCheckReport",
    "ComponentSpec",
    "EnclosureSpec",
    "ComponentType",
    "STANDARD_COMPONENT_PRESETS",
    "get_preset_component",
    "list_hardware_presets",
    "generate_enclosure_for_component",
]
