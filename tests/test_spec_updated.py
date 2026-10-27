"""
Updated tests for the spec module with ParameterSource and confirmed fields.
"""

import pytest
from ai3d_designer.core.spec.models import (
    PartSpec, FeatureSpec, ParameterSpec,
    PrimitiveType, OperationType, UnitSystem, ParameterSource
)


def test_parameter_spec_with_source_and_confirmed():
    """Test ParameterSpec with source and confirmed fields."""
    param = ParameterSpec(
        name="width",
        value=10.0,
        unit=UnitSystem.MM,
        source=ParameterSource.USER,
        confirmed=True,
    )
    assert param.name == "width"
    assert param.value == 10.0
    assert param.unit == UnitSystem.MM
    assert param.source == ParameterSource.USER
    assert param.confirmed is True


def test_parameter_spec_default_source_and_confirmed():
    """Test ParameterSpec defaults for source and confirmed."""
    param = ParameterSpec(name="width", value=10.0)
    assert param.source == ParameterSource.USER
    assert param.confirmed is False


def test_parameter_spec_all_sources():
    """Test all parameter source values."""
    for source in ParameterSource:
        param = ParameterSpec(name="test", value=1.0, source=source)
        assert param.source == source


def test_parameter_spec_confirmed_false_by_default():
    """Test that confirmed defaults to False."""
    param = ParameterSpec(name="test", value=1.0)
    assert param.confirmed is False

    param_confirmed = ParameterSpec(name="test", value=1.0, confirmed=True)
    assert param_confirmed.confirmed is True


def test_feature_spec_with_parameter_source():
    """Test FeatureSpec with parameters that have source and confirmed."""
    feature = FeatureSpec(
        id="test_1",
        type=PrimitiveType.BOX,
        name="test_box",
        parameters={
            "width": ParameterSpec(name="width", value=10, source=ParameterSource.USER, confirmed=True),
            "depth": ParameterSpec(name="depth", value=20, source=ParameterSource.DRAWING, confirmed=False),
            "height": ParameterSpec(name="height", value=5, source=ParameterSource.DEFAULT, confirmed=False),
        },
        operation=OperationType.UNION,
    )
    assert feature.parameters["width"].source == ParameterSource.USER
    assert feature.parameters["width"].confirmed is True
    assert feature.parameters["depth"].source == ParameterSource.DRAWING
    assert feature.parameters["depth"].confirmed is False
    assert feature.parameters["height"].source == ParameterSource.DEFAULT
    assert feature.parameters["height"].confirmed is False


def test_part_spec_with_mixed_sources():
    """Test PartSpec with features having mixed parameter sources."""
    spec = PartSpec(
        name="test_part",
        description="A test part",
        unit_system=UnitSystem.MM,
    )
    feature = FeatureSpec(
        type=PrimitiveType.BOX,
        name="box",
        parameters={
            "width": ParameterSpec(name="width", value=10, source=ParameterSource.USER, confirmed=True),
            "depth": ParameterSpec(name="depth", value=20, source=ParameterSource.DRAWING, confirmed=True),
            "height": ParameterSpec(name="height", value=5, source=ParameterSource.DEFAULT, confirmed=False),
        },
    )
    spec.add_feature(feature)

    errors = spec.validate_spec()
    assert len(errors) == 0  # Should be valid


def test_parameter_source_enum_values():
    """Test ParameterSource enum values."""
    assert ParameterSource.USER.value == "user"
    assert ParameterSource.DRAWING.value == "drawing"
    assert ParameterSource.DATASHEET.value == "datasheet"
    assert ParameterSource.DEFAULT.value == "default"


def test_parameter_spec_to_mm_with_different_units():
    """Test to_mm conversion with different units."""
    param_mm = ParameterSpec(name="test", value=10, unit=UnitSystem.MM)
    assert param_mm.to_mm() == 10.0

    param_cm = ParameterSpec(name="test", value=1, unit=UnitSystem.CM)
    assert param_cm.to_mm() == 10.0

    param_inch = ParameterSpec(name="test", value=1, unit=UnitSystem.INCH)
    assert param_inch.to_mm() == 25.4

    param_m = ParameterSpec(name="test", value=0.001, unit=UnitSystem.M)
    assert param_m.to_mm() == 1.0


def test_parameter_spec_validation_still_works():
    """Test that existing validation still works with new fields."""
    # Min/max validation
    with pytest.raises(ValueError, match="below minimum"):
        ParameterSpec(name="width", value=5, min_value=10)

    with pytest.raises(ValueError, match="above maximum"):
        ParameterSpec(name="width", value=15, max_value=10)

    # Finite validation
    with pytest.raises(ValueError, match="finite"):
        ParameterSpec(name="width", value=float("nan"))

    with pytest.raises(ValueError, match="finite"):
        ParameterSpec(name="width", value=1.0, max_value=float("inf"))


def test_part_spec_hash_with_new_fields():
    """Test that hash computation works with new fields."""
    spec = PartSpec(
        name="test",
        unit_system=UnitSystem.MM,
    )
    feature = FeatureSpec(
        type=PrimitiveType.BOX,
        name="box",
        parameters={
            "width": ParameterSpec(name="width", value=10, source=ParameterSource.USER, confirmed=True),
            "depth": ParameterSpec(name="depth", value=20, source=ParameterSource.USER, confirmed=True),
            "height": ParameterSpec(name="height", value=5, source=ParameterSource.USER, confirmed=True),
        },
    )
    spec.add_feature(feature)

    hash1 = spec.compute_hash()
    hash2 = spec.compute_hash()
    assert hash1 == hash2
    assert len(hash1) == 16


def test_legacy_spec_path_reexports_canonical_models():
    from ai3d_designer.spec.models import PartSpec as LegacyPartSpec
    from ai3d_designer.core.spec.models import PartSpec as CorePartSpec

    assert LegacyPartSpec is CorePartSpec
