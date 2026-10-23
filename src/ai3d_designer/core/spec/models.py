"""
Pydantic models for part specifications.
Defines the schema for describing mechanical parts and features.
"""

from enum import Enum
from math import isfinite
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator, model_validator
import uuid
from datetime import datetime


class UnitSystem(str, Enum):
    """Supported unit systems."""
    MM = "mm"
    CM = "cm"
    INCH = "in"
    M = "m"


class PrimitiveType(str, Enum):
    """Supported primitive shapes."""
    BOX = "box"
    CYLINDER = "cylinder"
    SPHERE = "sphere"
    CONE = "cone"
    TORUS = "torus"
    WEDGE = "wedge"
    EXTRUSION = "extrusion"
    REVOLUTION = "revolution"
    LOFT = "loft"
    SWEEP = "sweep"


class OperationType(str, Enum):
    """Boolean operations."""
    UNION = "union"
    DIFFERENCE = "difference"
    INTERSECTION = "intersection"


class ExportFormat(str, Enum):
    """Supported export formats."""
    STEP = "step"
    STL = "stl"
    OBJ = "obj"
    GLTF = "gltf"
    THREE_MF = "3mf"


class ParameterSpec(BaseModel):
    """A single parameter with value, unit, and constraints."""
    name: str
    value: float
    unit: UnitSystem = UnitSystem.MM
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    description: str = ""

    @model_validator(mode="after")
    def validate_range(self):
        if not isfinite(self.value):
            raise ValueError("Parameter value must be finite.")
        if self.min_value is not None and not isfinite(self.min_value):
            raise ValueError("Parameter minimum must be finite.")
        if self.max_value is not None and not isfinite(self.max_value):
            raise ValueError("Parameter maximum must be finite.")
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError("Parameter minimum cannot exceed its maximum.")
        if self.min_value is not None and self.value < self.min_value:
            raise ValueError(f"Value {self.value} below minimum {self.min_value}")
        if self.max_value is not None and self.value > self.max_value:
            raise ValueError(f"Value {self.value} above maximum {self.max_value}")
        return self

    def to_mm(self) -> float:
        """Convert value to millimeters."""
        factors = {
            UnitSystem.MM: 1.0,
            UnitSystem.CM: 10.0,
            UnitSystem.INCH: 25.4,
            UnitSystem.M: 1000.0,
        }
        return self.value * factors.get(self.unit, 1.0)


class FeatureSpec(BaseModel):
    """A single feature (primitive or operation) in the part."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: PrimitiveType
    name: str = ""
    parameters: Dict[str, ParameterSpec] = Field(default_factory=dict)
    position: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    operation: OperationType = OperationType.UNION
    parent_id: Optional[str] = None
    children: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PartSpec(BaseModel):
    """Complete specification for a mechanical part."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    description: str = ""
    unit_system: UnitSystem = UnitSystem.MM
    features: List[FeatureSpec] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    spec_hash: str = ""

    def add_feature(self, feature: FeatureSpec) -> None:
        """Add a feature to the part."""
        self.features.append(feature)
        self.updated_at = datetime.utcnow().isoformat()

    def get_feature(self, feature_id: str) -> Optional[FeatureSpec]:
        """Get a feature by ID."""
        for f in self.features:
            if f.id == feature_id:
                return f
        return None

    def compute_hash(self) -> str:
        """Compute deterministic hash of the specification."""
        import hashlib
        import json
        # Create a canonical representation
        data = self.model_dump(mode="json", exclude={"spec_hash", "created_at", "updated_at"})
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def validate_spec(self) -> List[str]:
        """Validate the specification and return list of errors."""
        errors = []
        if not self.name:
            errors.append("Part name is required")
        if not self.features:
            errors.append("At least one feature is required")
        # Check for duplicate feature IDs
        ids = [f.id for f in self.features]
        if len(ids) != len(set(ids)):
            errors.append("Duplicate feature IDs found")
        # Validate each feature
        for feature in self.features:
            if feature.type in (PrimitiveType.EXTRUSION, PrimitiveType.REVOLUTION, 
                               PrimitiveType.LOFT, PrimitiveType.SWEEP):
                if not feature.metadata.get("profile"):
                    errors.append(f"Feature {feature.id} ({feature.type.value}) requires a profile")
        return errors
