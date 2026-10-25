"""Regression tests for CAD unit conventions and operation safety."""

import math

import pytest

from ai3d_designer.core.geometry.engine import create_part_from_spec
from ai3d_designer.core.spec.models import (
    FeatureSpec,
    OperationType,
    ParameterSpec,
    PartSpec,
    PrimitiveType,
    UnitSystem,
)


def _box_feature(operation: OperationType = OperationType.UNION) -> FeatureSpec:
    return FeatureSpec(
        id="base",
        type=PrimitiveType.BOX,
        name="Base",
        parameters={
            "width": ParameterSpec(name="width", value=1, unit=UnitSystem.CM),
            "depth": ParameterSpec(name="depth", value=2, unit=UnitSystem.CM),
            "height": ParameterSpec(name="height", value=3, unit=UnitSystem.CM),
        },
        position=[1, 0, 0],
        operation=operation,
    )


def test_geometry_dimensions_follow_each_parameter_unit_and_positions_are_mm():
    spec = PartSpec(name="mixed units", unit_system=UnitSystem.CM, features=[_box_feature()])
    part = create_part_from_spec(spec)

    assert math.isclose(part.volume, 10 * 20 * 30, rel_tol=1e-7)
    bounds = part.bounding_box()
    # Position is 1 mm, not 1 cm: the 10 mm-wide box is centred at x=1 mm.
    assert math.isclose(bounds.min.X, -4, abs_tol=1e-6)
    assert math.isclose(bounds.max.X, 6, abs_tol=1e-6)


def test_first_feature_cannot_start_with_difference():
    spec = PartSpec(
        name="invalid history",
        unit_system=UnitSystem.MM,
        features=[_box_feature(OperationType.DIFFERENCE)],
    )
    with pytest.raises(ValueError, match="first feature must use the union"):
        create_part_from_spec(spec)


def test_empty_boolean_result_is_rejected():
    base = FeatureSpec(
        id="base",
        type=PrimitiveType.BOX,
        name="Base",
        parameters={
            "width": ParameterSpec(name="width", value=10),
            "depth": ParameterSpec(name="depth", value=10),
            "height": ParameterSpec(name="height", value=10),
        },
        operation=OperationType.UNION,
    )
    disjoint = FeatureSpec(
        id="disjoint",
        type=PrimitiveType.BOX,
        name="Disjoint intersection",
        parameters={
            "width": ParameterSpec(name="width", value=2),
            "depth": ParameterSpec(name="depth", value=2),
            "height": ParameterSpec(name="height", value=2),
        },
        position=[100, 100, 100],
        operation=OperationType.INTERSECTION,
    )
    spec = PartSpec(name="empty intersection", features=[base, disjoint])
    with pytest.raises(ValueError, match="empty or invalid geometry"):
        create_part_from_spec(spec)


def test_profile_extrusion_generates_expected_volume():
    from ai3d_designer.core.spec.models import PrimitiveType

    feature = FeatureSpec(
        id="extruded_profile",
        type=PrimitiveType.EXTRUSION,
        name="Extruded rectangle",
        parameters={"height": ParameterSpec(name="height", value=5)},
        metadata={"profile": [[0, 0], [20, 0], [20, 10], [0, 10]]},
        operation=OperationType.UNION,
    )
    part = create_part_from_spec(PartSpec(name="Extrusion test", features=[feature]))
    assert math.isclose(part.volume, 1000.0, rel_tol=1e-6)
    assert part.is_valid


def test_profile_revolution_generates_expected_hollow_cylinder_volume():
    from ai3d_designer.core.spec.models import PrimitiveType

    feature = FeatureSpec(
        id="revolved_profile",
        type=PrimitiveType.REVOLUTION,
        name="Revolved rectangular annulus profile",
        metadata={"profile": [[10, 0], [20, 0], [20, 30], [10, 30]]},
        operation=OperationType.UNION,
    )
    part = create_part_from_spec(PartSpec(name="Revolution test", features=[feature]))
    expected = math.pi * (20**2 - 10**2) * 30
    assert math.isclose(part.volume, expected, rel_tol=1e-5)
    assert part.is_valid


def test_profile_features_reject_self_intersecting_polygons():
    from ai3d_designer.core.spec.models import PrimitiveType

    feature = FeatureSpec(
        id="bad_profile",
        type=PrimitiveType.EXTRUSION,
        name="Self crossing",
        parameters={"height": ParameterSpec(name="height", value=5)},
        metadata={"profile": [[0, 0], [10, 10], [0, 10], [10, 0]]},
        operation=OperationType.UNION,
    )
    with pytest.raises(ValueError, match="self-intersects"):
        create_part_from_spec(PartSpec(name="Invalid profile", features=[feature]))
