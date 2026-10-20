"""
Pydantic models for part specifications.
Defines the schema for describing mechanical parts and features.
"""

from enum import Enum
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator, model_validator
import uuid


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
        if self.min_value is not None and self.value < self.min_value:
            raise ValueError(f"Value {self.value} below minimum {self.min_value}")
        if self.max_value is not None and self.value > self.max_value:
            raise ValueError(f"Value {self.value} above maximum {self.max_value}")
        return self


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
    created_at: str = ""
    updated_at: str = ""
    spec_hash: str = ""

    def add_feature(self, feature: FeatureSpec) -> None:
        """Add a feature to the part."""
        self.features.append(feature)

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
        data = self.model_dump(mode="json", exclude={"spec_hash"})
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
        return errors
