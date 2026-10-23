"""Legacy geometry import path.

This module remains for backward compatibility. The core engine is the single
source of truth for units, feature history, validation, extrusion and revolution.
"""

from build123d import Part

from ..spec.models import PartSpec, UnitSystem
from ..core.spec.models import PartSpec as CorePartSpec
from ..core.geometry.engine import GeometryEngine as CoreGeometryEngine

class GeometryEngine:
    """Backward-compatible adapter around :class:`core.geometry.GeometryEngine`."""

    UNIT_FACTORS = {
        UnitSystem.MM: 1.0,
        UnitSystem.CM: 10.0,
        UnitSystem.INCH: 25.4,
        UnitSystem.M: 1000.0,
    }

    def __init__(self, unit_system: UnitSystem = UnitSystem.MM):
        self.unit_system = unit_system
        self.unit_factor = self.UNIT_FACTORS[unit_system]
        self._engine = CoreGeometryEngine()

    def create_part(self, spec: PartSpec) -> Part:
        """Convert a legacy PartSpec into the canonical core schema and build it."""
        try:
            core_spec = CorePartSpec.model_validate(spec.model_dump(mode="python"))
        except Exception as exc:
            raise ValueError(f"Could not convert legacy part specification: {exc}") from exc
        return self._engine.create_part(core_spec)


def create_part_from_spec(spec: PartSpec) -> Part:
    """Backward-compatible convenience function using the canonical core engine."""
    return GeometryEngine(spec.unit_system).create_part(spec)
