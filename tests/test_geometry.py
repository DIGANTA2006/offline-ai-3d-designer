"""
Tests for the geometry module.
"""

import pytest
from ai3d_designer.core.spec.models import (
    PartSpec, FeatureSpec, ParameterSpec,
    PrimitiveType, OperationType, UnitSystem
)
from ai3d_designer.core.geometry.engine import GeometryEngine, create_part_from_spec


def test_geometry_engine_creation():
    """Test GeometryEngine instantiation."""
    engine = GeometryEngine(UnitSystem.MM)
    assert engine.unit_system == UnitSystem.MM
    assert engine.unit_factor == 1.0
    
    engine_cm = GeometryEngine(UnitSystem.CM)
    assert engine_cm.unit_factor == 10.0
    
    engine_inch = GeometryEngine(UnitSystem.INCH)
    assert engine_inch.unit_factor == 25.4


def test_unit_conversion():
    """Test unit conversion."""
    engine = GeometryEngine(UnitSystem.MM)
    assert engine._convert(10) == 10.0
    
    engine_cm = GeometryEngine(UnitSystem.CM)
    assert engine_cm._convert(1) == 10.0
    
    engine_inch = GeometryEngine(UnitSystem.INCH)
    assert abs(engine_inch._convert(1) - 25.4) < 0.001


def test_create_box():
    """Test creating a simple box."""
    spec = PartSpec(
        name="test_box",
        unit_system=UnitSystem.MM,
    )
    feature = FeatureSpec(
        type=PrimitiveType.BOX,
        name="box",
        parameters={
            "width": ParameterSpec(name="width", value=10),
            "depth": ParameterSpec(name="depth", value=20),
            "height": ParameterSpec(name="height", value=30),
        },
        operation=OperationType.UNION,
    )
    spec.add_feature(feature)
    
    part = create_part_from_spec(spec)
    assert part is not None
    assert part.volume > 0
    # Volume should be 10 * 20 * 30 = 6000
    assert abs(part.volume - 6000.0) < 0.01


def test_create_cylinder():
    """Test creating a cylinder."""
    spec = PartSpec(
        name="test_cylinder",
        unit_system=UnitSystem.MM,
    )
    feature = FeatureSpec(
        type=PrimitiveType.CYLINDER,
        name="cylinder",
        parameters={
            "radius": ParameterSpec(name="radius", value=5),
            "height": ParameterSpec(name="height", value=10),
        },
        operation=OperationType.UNION,
    )
    spec.add_feature(feature)
    
    part = create_part_from_spec(spec)
    assert part is not None
    assert part.volume > 0
    # Volume = pi * r^2 * h = pi * 25 * 10 = 250 * pi ≈ 785.4
    import math
    expected = math.pi * 25 * 10
    assert abs(part.volume - expected) < 0.1


def test_create_sphere():
    """Test creating a sphere."""
    spec = PartSpec(
        name="test_sphere",
        unit_system=UnitSystem.MM,
    )
    feature = FeatureSpec(
        type=PrimitiveType.SPHERE,
        name="sphere",
        parameters={
            "radius": ParameterSpec(name="radius", value=10),
        },
        operation=OperationType.UNION,
    )
    spec.add_feature(feature)
    
    part = create_part_from_spec(spec)
    assert part is not None
    assert part.volume > 0
    # Volume = 4/3 * pi * r^3
    import math
    expected = 4/3 * math.pi * 1000
    assert abs(part.volume - expected) < 0.1


def test_boolean_difference():
    """Test boolean difference operation (box with hole)."""
    spec = PartSpec(
        name="box_with_hole",
        unit_system=UnitSystem.MM,
    )
    
    # Box
    box = FeatureSpec(
        id="box",
        type=PrimitiveType.BOX,
        name="box",
        parameters={
            "width": ParameterSpec(name="width", value=20),
            "depth": ParameterSpec(name="depth", value=20),
            "height": ParameterSpec(name="height", value=10),
        },
        operation=OperationType.UNION,
    )
    spec.add_feature(box)
    
    # Hole (cylinder)
    hole = FeatureSpec(
        id="hole",
        type=PrimitiveType.CYLINDER,
        name="hole",
        parameters={
            "radius": ParameterSpec(name="radius", value=3),
            "height": ParameterSpec(name="height", value=12),
        },
        position=[10, 10, -1],
        operation=OperationType.DIFFERENCE,
    )
    spec.add_feature(hole)
    
    part = create_part_from_spec(spec)
    assert part is not None
    assert part.volume > 0
    # Box volume = 4000, hole volume ≈ 339, result ≈ 3661
    assert part.volume < 4000
    assert part.volume > 3500


def test_boolean_intersection():
    """Test boolean intersection operation."""
    spec = PartSpec(
        name="intersection_test",
        unit_system=UnitSystem.MM,
    )
    
    # Box 1
    box1 = FeatureSpec(
        id="box1",
        type=PrimitiveType.BOX,
        name="box1",
        parameters={
            "width": ParameterSpec(name="width", value=20),
            "depth": ParameterSpec(name="depth", value=20),
            "height": ParameterSpec(name="height", value=20),
        },
        operation=OperationType.UNION,
    )
    spec.add_feature(box1)
    
    # Box 2 (overlapping)
    box2 = FeatureSpec(
        id="box2",
        type=PrimitiveType.BOX,
        name="box2",
        parameters={
            "width": ParameterSpec(name="width", value=20),
            "depth": ParameterSpec(name="depth", value=20),
            "height": ParameterSpec(name="height", value=20),
        },
        position=[10, 0, 0],
        operation=OperationType.INTERSECTION,
    )
    spec.add_feature(box2)
    
    part = create_part_from_spec(spec)
    assert part is not None
    assert part.volume > 0
    # Intersection should be 10*20*20 = 4000
    assert abs(part.volume - 4000.0) < 1.0


def test_position_and_rotation():
    """Test position and rotation transforms."""
    spec = PartSpec(
        name="transform_test",
        unit_system=UnitSystem.MM,
    )
    
    feature = FeatureSpec(
        type=PrimitiveType.BOX,
        name="box",
        parameters={
            "width": ParameterSpec(name="width", value=10),
            "depth": ParameterSpec(name="depth", value=10),
            "height": ParameterSpec(name="height", value=10),
        },
        position=[5, 5, 5],
        rotation=[0, 0, 45],
        operation=OperationType.UNION,
    )
    spec.add_feature(feature)
    
    part = create_part_from_spec(spec)
    assert part is not None
    assert part.volume > 0
    # Volume unchanged by transform
    assert abs(part.volume - 1000.0) < 0.01


def test_empty_spec_fails():
    """Test that empty spec raises error."""
    spec = PartSpec(name="empty", unit_system=UnitSystem.MM)
    with pytest.raises(ValueError):
        create_part_from_spec(spec)


def test_unit_system_conversion():
    """Test that unit system affects geometry size."""
    # Create same spec in mm and cm
    spec_mm = PartSpec(name="test", unit_system=UnitSystem.MM)
    spec_mm.add_feature(FeatureSpec(
        type=PrimitiveType.BOX,
        name="box",
        parameters={
            "width": ParameterSpec(name="width", value=10, unit=UnitSystem.MM),
            "depth": ParameterSpec(name="depth", value=10, unit=UnitSystem.MM),
            "height": ParameterSpec(name="height", value=10, unit=UnitSystem.MM),
        },
    ))
    
    spec_cm = PartSpec(name="test", unit_system=UnitSystem.CM)
    spec_cm.add_feature(FeatureSpec(
        type=PrimitiveType.BOX,
        name="box",
        parameters={
            "width": ParameterSpec(name="width", value=1, unit=UnitSystem.CM),
            "depth": ParameterSpec(name="depth", value=1, unit=UnitSystem.CM),
            "height": ParameterSpec(name="height", value=1, unit=UnitSystem.CM),
        },
    ))
    
    part_mm = create_part_from_spec(spec_mm)
    part_cm = create_part_from_spec(spec_cm)
    
    # Both should produce same volume (10mm = 1cm)
    assert abs(part_mm.volume - part_cm.volume) < 0.01
    assert abs(part_mm.volume - 1000.0) < 0.01

def test_explicit_parameter_units_override_part_default_units():
    spec = PartSpec(name="explicit_units", unit_system=UnitSystem.CM)
    spec.add_feature(FeatureSpec(
        id="box_mm",
        type=PrimitiveType.BOX,
        name="box",
        parameters={
            "width": ParameterSpec(name="width", value=10, unit=UnitSystem.MM),
            "depth": ParameterSpec(name="depth", value=10, unit=UnitSystem.MM),
            "height": ParameterSpec(name="height", value=10, unit=UnitSystem.MM),
        },
        operation=OperationType.UNION,
    ))

    part = create_part_from_spec(spec)
    assert abs(part.volume - 1000.0) < 0.01


def test_omitted_parameter_units_inherit_part_default_units():
    spec = PartSpec(name="inherited_units", unit_system=UnitSystem.CM)
    spec.add_feature(FeatureSpec(
        id="box_cm",
        type=PrimitiveType.BOX,
        name="box",
        parameters={
            "width": ParameterSpec(name="width", value=1),
            "depth": ParameterSpec(name="depth", value=1),
            "height": ParameterSpec(name="height", value=1),
        },
        operation=OperationType.UNION,
    ))

    part = create_part_from_spec(spec)
    assert abs(part.volume - 1000.0) < 0.01


def test_positions_are_always_millimeters():
    spec = PartSpec(name="position_mm", unit_system=UnitSystem.CM)
    spec.add_feature(FeatureSpec(
        id="box",
        type=PrimitiveType.BOX,
        name="box",
        parameters={
            "width": ParameterSpec(name="width", value=10, unit=UnitSystem.MM),
            "depth": ParameterSpec(name="depth", value=10, unit=UnitSystem.MM),
            "height": ParameterSpec(name="height", value=10, unit=UnitSystem.MM),
        },
        position=[10, 0, 0],
        operation=OperationType.UNION,
    ))

    part = create_part_from_spec(spec)
    assert abs(part.bounding_box().min.X - 5.0) < 0.01


def test_extrusion_from_polygon_profile():
    spec = PartSpec(name="profile_extrusion", unit_system=UnitSystem.MM)
    spec.add_feature(FeatureSpec(
        id="extruded_profile",
        type=PrimitiveType.EXTRUSION,
        name="rectangular extrusion",
        parameters={
            "height": ParameterSpec(name="height", value=10, unit=UnitSystem.MM),
        },
        metadata={
            "profile": {
                "unit": "mm",
                "points": [[0, 0], [20, 0], [20, 10], [0, 10]],
            }
        },
        operation=OperationType.UNION,
    ))

    part = create_part_from_spec(spec)
    assert part.volume > 0
    assert abs(part.volume - 2000.0) < 0.1


def test_missing_boolean_parent_and_cycles_fail_clearly():
    spec = PartSpec(name="missing_parent", unit_system=UnitSystem.MM)
    spec.add_feature(FeatureSpec(
        id="child",
        type=PrimitiveType.BOX,
        name="child",
        parameters={
            "width": ParameterSpec(name="width", value=10),
            "depth": ParameterSpec(name="depth", value=10),
            "height": ParameterSpec(name="height", value=10),
        },
        parent_id="not-present",
    ))
    with pytest.raises(ValueError, match="missing parent"):
        create_part_from_spec(spec)

    cyclic = PartSpec(name="cycle", unit_system=UnitSystem.MM)
    cyclic.add_feature(FeatureSpec(
        id="a", type=PrimitiveType.BOX, name="a",
        parameters={
            "width": ParameterSpec(name="width", value=10),
            "depth": ParameterSpec(name="depth", value=10),
            "height": ParameterSpec(name="height", value=10),
        },
        parent_id="b",
    ))
    cyclic.add_feature(FeatureSpec(
        id="b", type=PrimitiveType.BOX, name="b",
        parameters={
            "width": ParameterSpec(name="width", value=10),
            "depth": ParameterSpec(name="depth", value=10),
            "height": ParameterSpec(name="height", value=10),
        },
        parent_id="a",
    ))
    with pytest.raises(ValueError, match="cycle"):
        create_part_from_spec(cyclic)


def test_zero_top_radius_is_valid_for_a_pointed_cone():
    spec = PartSpec(name="pointed_cone", unit_system=UnitSystem.MM)
    spec.add_feature(FeatureSpec(
        id="cone",
        type=PrimitiveType.CONE,
        name="cone",
        parameters={
            "radius_bottom": ParameterSpec(name="radius_bottom", value=10),
            "radius_top": ParameterSpec(name="radius_top", value=0),
            "height": ParameterSpec(name="height", value=20),
        },
        operation=OperationType.UNION,
    ))
    result = create_part_from_spec(spec)
    assert result.volume > 0


def test_revolution_profile_uses_radius_height_plane():
    spec = PartSpec(name="turned_sleeve", unit_system=UnitSystem.MM)
    spec.add_feature(FeatureSpec(
        id="revolve_sleeve",
        type=PrimitiveType.REVOLUTION,
        name="sleeve",
        parameters={},
        metadata={
            "profile": {
                "unit": "mm",
                "points": [[5, 0], [10, 0], [10, 20], [5, 20]],
            }
        },
        operation=OperationType.UNION,
    ))
    part = create_part_from_spec(spec)
    assert part.volume > 0
    assert part.bounding_box().size.Z == pytest.approx(20.0, abs=0.1)


def test_loft_accepts_offset_polygon_sections():
    spec = PartSpec(name="tapered_loft", unit_system=UnitSystem.MM)
    spec.add_feature(FeatureSpec(
        id="loft",
        type=PrimitiveType.LOFT,
        name="loft",
        parameters={},
        metadata={
            "profiles": [
                {"unit": "mm", "z": 0, "points": [[0, 0], [20, 0], [20, 20], [0, 20]]},
                {"unit": "mm", "z": 10, "points": [[5, 5], [15, 5], [15, 15], [5, 15]]},
            ]
        },
        operation=OperationType.UNION,
    ))
    part = create_part_from_spec(spec)
    assert part.volume > 0
    assert part.bounding_box().size.Z == pytest.approx(10.0, abs=0.1)
