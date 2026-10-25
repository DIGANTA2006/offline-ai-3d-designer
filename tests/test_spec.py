"""
Tests for the spec module.
"""

import pytest
from ai3d_designer.core.spec.models import (
    PartSpec, FeatureSpec, ParameterSpec,
    PrimitiveType, OperationType, UnitSystem
)


def test_parameter_spec():
    """Test ParameterSpec creation and validation."""
    param = ParameterSpec(name="width", value=10.0, unit=UnitSystem.MM)
    assert param.name == "width"
    assert param.value == 10.0
    assert param.unit == UnitSystem.MM


def test_parameter_spec_validation():
    """Test ParameterSpec validation."""
    param = ParameterSpec(name="width", value=10.0, min_value=0, max_value=100)
    assert param.value == 10.0
    
    # Test min validation
    with pytest.raises(ValueError):
        ParameterSpec(name="width", value=-1.0, min_value=0)
    
    # Test max validation
    with pytest.raises(ValueError):
        ParameterSpec(name="width", value=101.0, max_value=100)


def test_feature_spec():
    """Test FeatureSpec creation."""
    feature = FeatureSpec(
        id="test_1",
        type=PrimitiveType.BOX,
        name="test_box",
        parameters={
            "width": ParameterSpec(name="width", value=10),
            "height": ParameterSpec(name="height", value=20),
        },
        operation=OperationType.UNION,
    )
    assert feature.id == "test_1"
    assert feature.type == PrimitiveType.BOX
    assert feature.operation == OperationType.UNION


def test_part_spec():
    """Test PartSpec creation."""
    spec = PartSpec(
        name="test_part",
        description="A test part",
        unit_system=UnitSystem.MM,
    )
    assert spec.name == "test_part"
    assert spec.unit_system == UnitSystem.MM
    assert len(spec.features) == 0


def test_part_spec_add_feature():
    """Test adding features to PartSpec."""
    spec = PartSpec(name="test", unit_system=UnitSystem.MM)
    feature = FeatureSpec(
        type=PrimitiveType.BOX,
        name="box",
        parameters={"width": ParameterSpec(name="width", value=10)},
    )
    spec.add_feature(feature)
    assert len(spec.features) == 1
    assert spec.get_feature(feature.id) == feature


def test_part_spec_validation():
    """Test PartSpec validation."""
    # Empty name should fail
    spec = PartSpec(name="", unit_system=UnitSystem.MM)
    errors = spec.validate_spec()
    assert "Part name is required" in errors
    
    # No features should fail
    spec = PartSpec(name="test", unit_system=UnitSystem.MM)
    errors = spec.validate_spec()
    assert "At least one feature is required" in errors


def test_part_spec_hash():
    """Test deterministic hash computation."""
    spec = PartSpec(
        name="test",
        unit_system=UnitSystem.MM,
    )
    feature = FeatureSpec(
        type=PrimitiveType.BOX,
        name="box",
        parameters={"width": ParameterSpec(name="width", value=10)},
    )
    spec.add_feature(feature)
    
    hash1 = spec.compute_hash()
    hash2 = spec.compute_hash()
    assert hash1 == hash2
    assert len(hash1) == 16  # SHA256 truncated to 16 chars


def test_unit_system_enum():
    """Test UnitSystem enum values."""
    assert UnitSystem.MM.value == "mm"
    assert UnitSystem.CM.value == "cm"
    assert UnitSystem.INCH.value == "in"
    assert UnitSystem.M.value == "m"


def test_primitive_type_enum():
    """Test PrimitiveType enum values."""
    assert PrimitiveType.BOX.value == "box"
    assert PrimitiveType.CYLINDER.value == "cylinder"
    assert PrimitiveType.SPHERE.value == "sphere"


def test_operation_type_enum():
    """Test OperationType enum values."""
    assert OperationType.UNION.value == "union"
    assert OperationType.DIFFERENCE.value == "difference"
    assert OperationType.INTERSECTION.value == "intersection"


def test_parameter_spec_rejects_non_finite_values_and_bounds():
    with pytest.raises(ValueError, match="finite"):
        ParameterSpec(name="width", value=float("nan"))
    with pytest.raises(ValueError, match="finite"):
        ParameterSpec(name="width", value=1.0, max_value=float("inf"))
    with pytest.raises(ValueError, match="cannot exceed"):
        ParameterSpec(name="width", value=5.0, min_value=10.0, max_value=2.0)


def test_legacy_spec_path_reexports_canonical_models():
    from ai3d_designer.spec.models import PartSpec as LegacyPartSpec
    from ai3d_designer.core.spec.models import PartSpec as CorePartSpec

    assert LegacyPartSpec is CorePartSpec
