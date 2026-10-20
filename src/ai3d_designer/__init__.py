"""
Offline AI 3D Designer - Local LLM-driven CAD generation for mechanical parts.
"""

__version__ = "0.1.0"
__author__ = "Diganta Chakraborty"
__license__ = "Proprietary - All rights reserved"

# Core spec models
from .core.spec.models import (
    UnitSystem,
    PrimitiveType,
    OperationType,
    ExportFormat,
    ParameterSpec,
    FeatureSpec,
    PartSpec,
)

# Geometry engine
from .core.geometry.engine import (
    GeometryEngine,
    create_part_from_spec,
)

# Export
from .core.export.exporter import (
    ExportResult,
    export_step,
    export_stl,
    validate_export,
)

# Validation
from .core.validation.validator import (
    ValidationSeverity,
    ValidationIssue,
    ValidationResult,
    SpecValidator,
    GeometryValidator,
    validate_spec,
    validate_geometry,
)

# NLP
from .core.nlp.parser import (
    ParseResult,
    NLPEngine,
    RuleBasedParser,
    parse_natural_language,
    PromptTemplates,
)

# Storage
from .core.storage.storage import (
    SpecStorage,
    ProjectMetadata,
    get_storage,
)

# Licensing
from .core.licensing.manager import (
    LicenseInfo,
    LicenseManager,
    get_license_manager,
)

# Worker
from .core.worker.worker import (
    JobStatus,
    Job,
    WorkerPool,
    get_worker_pool,
    create_geometry_job,
    create_export_job,
    create_validate_job,
)

__all__ = [
    # Version info
    "__version__",
    "__author__",
    "__license__",
    # Spec models
    "UnitSystem",
    "PrimitiveType",
    "OperationType",
    "ExportFormat",
    "ParameterSpec",
    "FeatureSpec",
    "PartSpec",
    # Geometry
    "GeometryEngine",
    "create_part_from_spec",
    # Export
    "ExportResult",
    "export_step",
    "export_stl",
    "validate_export",
    # Validation
    "ValidationSeverity",
    "ValidationIssue",
    "ValidationResult",
    "SpecValidator",
    "GeometryValidator",
    "validate_spec",
    "validate_geometry",
    # NLP
    "ParseResult",
    "NLPEngine",
    "RuleBasedParser",
    "parse_natural_language",
    "PromptTemplates",
    # Storage
    "SpecStorage",
    "ProjectMetadata",
    "get_storage",
    # Licensing
    "LicenseInfo",
    "LicenseManager",
    "get_license_manager",
    # Worker
    "JobStatus",
    "Job",
    "WorkerPool",
    "get_worker_pool",
    "create_geometry_job",
    "create_export_job",
    "create_validate_job",
]
