"""
Printability module for Offline AI 3D Designer.

Provides 8 deterministic printability checks with 4-part explanations,
beginner glossary, and 1-click fix actions that mutate the spec,
rebuild in the kernel, and re-verify.
"""

from .checks import (
    PrintabilityChecker,
    CheckResult,
    CheckStatus,
    run_all_checks,
)
from .explanations import (
    EXPLANATIONS,
    GLOSSARY,
    get_explanation,
    get_glossary_entry,
)
from .fixes import (
    FixAction,
    FixResult,
    apply_fix,
    apply_fix_and_reverify,
)
from .api import router as printability_router

__all__ = [
    "PrintabilityChecker",
    "CheckResult",
    "CheckStatus",
    "run_all_checks",
    "EXPLANATIONS",
    "GLOSSARY",
    "get_explanation",
    "get_glossary_entry",
    "FixAction",
    "FixResult",
    "apply_fix",
    "apply_fix_and_reverify",
    "printability_router",
]
