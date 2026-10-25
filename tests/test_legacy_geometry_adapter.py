"""The legacy public geometry import must delegate to the canonical engine."""

import math

from ai3d_designer.geometry.engine import create_part_from_spec
from ai3d_designer.spec.models import (
    FeatureSpec,
    OperationType,
    ParameterSpec,
    PartSpec,
    PrimitiveType,
    UnitSystem,
)


def test_legacy_geometry_entrypoint_uses_per_parameter_units_and_mm_positions():
    feature = FeatureSpec(
        id="legacy_box",
        type=PrimitiveType.BOX,
        name="Compatibility box",
        parameters={
            "width": ParameterSpec(name="width", value=1, unit=UnitSystem.CM),
            "depth": ParameterSpec(name="depth", value=2, unit=UnitSystem.CM),
            "height": ParameterSpec(name="height", value=3, unit=UnitSystem.CM),
        },
        position=[1, 0, 0],
        operation=OperationType.UNION,
    )
    spec = PartSpec(
        name="Legacy API box",
        unit_system=UnitSystem.M,
        features=[feature],
    )

    part = create_part_from_spec(spec)

    assert math.isclose(part.volume, 10 * 20 * 30, rel_tol=1e-7)
    assert math.isclose(part.bounding_box().min.X, -4, abs_tol=1e-6)
    assert math.isclose(part.bounding_box().max.X, 6, abs_tol=1e-6)
