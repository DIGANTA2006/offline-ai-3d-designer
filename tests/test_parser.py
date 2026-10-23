"""Regression tests for conservative natural-language CAD parsing."""

import math

from ai3d_designer.core.geometry.engine import create_part_from_spec
from ai3d_designer.core.nlp.parser import parse_natural_language
from ai3d_designer.core.spec.models import UnitSystem


def parse_ok(description: str, unit_system: UnitSystem = UnitSystem.MM):
    result = parse_natural_language(description, unit_system=unit_system)
    assert result.success, result.error
    assert result.spec is not None
    return result.spec


def test_dimension_tuple_with_trailing_unit_preserves_all_dimensions():
    spec = parse_ok("40 x 20 x 10 mm box")
    params = spec.features[0].parameters
    assert params["width"].value == 40
    assert params["depth"].value == 20
    assert params["height"].value == 10
    assert params["width"].unit == UnitSystem.MM
    assert params["depth"].unit == UnitSystem.MM
    assert params["height"].unit == UnitSystem.MM


def test_tuple_with_units_on_each_dimension():
    spec = parse_ok("40 mm x 2 cm x 10 mm plate")
    params = spec.features[0].parameters
    assert params["width"].unit == UnitSystem.MM
    assert params["width"].value == 40
    assert params["depth"].unit == UnitSystem.CM
    assert params["depth"].value == 2
    assert params["height"].unit == UnitSystem.MM
    assert params["height"].value == 10


def test_selected_unit_applies_when_tuple_has_no_units():
    spec = parse_ok("4 x 2 x 1 box", UnitSystem.CM)
    params = spec.features[0].parameters
    assert all(params[name].unit == UnitSystem.CM for name in ("width", "depth", "height"))
    part = create_part_from_spec(spec)
    assert math.isclose(part.volume, 40 * 20 * 10, rel_tol=1e-7)


def test_centered_through_hole_builds_cutter_feature():
    spec = parse_ok("40 x 20 x 10 mm box with a 5 mm hole through the center")
    assert len(spec.features) == 2
    base, cutter = spec.features
    assert base.operation.value == "union"
    assert cutter.operation.value == "difference"
    assert cutter.parameters["radius"].value == 2.5
    assert cutter.parameters["radius"].unit == UnitSystem.MM
    assert cutter.position == [0.0, 0.0, 0.0]
    assert cutter.parameters["height"].value == 12
    part = create_part_from_spec(spec)
    expected = 40 * 20 * 10 - math.pi * (2.5**2) * 10
    assert math.isclose(part.volume, expected, rel_tol=1e-5)


def test_cylinder_diameter_and_height_are_parsed():
    spec = parse_ok("cylinder with 20 mm diameter and 50 mm height")
    params = spec.features[0].parameters
    assert params["radius"].value == 10
    assert params["height"].value == 50


def test_tube_becomes_a_hollow_cylinder_not_a_solid_rod():
    spec = parse_ok("tube OD 20 mm ID 10 mm length 50 mm")
    assert len(spec.features) == 2
    assert spec.features[0].operation.value == "union"
    assert spec.features[1].operation.value == "difference"
    part = create_part_from_spec(spec)
    expected = math.pi * (10**2 - 5**2) * 50
    assert math.isclose(part.volume, expected, rel_tol=1e-5)


def test_torus_from_inner_and_outer_diameters():
    spec = parse_ok("ring with outer diameter 20 mm and inner diameter 10 mm")
    params = spec.features[0].parameters
    assert math.isclose(params["major_radius"].to_mm(), 7.5)
    assert math.isclose(params["minor_radius"].to_mm(), 2.5)


def test_ambiguous_box_without_dimensions_is_rejected_not_guessed():
    result = parse_natural_language("make a box")
    assert not result.success
    assert "box width" in (result.error or "")


def test_unsupported_precision_features_are_rejected_not_ignored():
    result = parse_natural_language("40 x 20 x 10 mm box with 2 mm filleted edges")
    assert not result.success
    assert "does not yet model fillets" in (result.error or "")


def test_multiple_holes_are_rejected_until_their_positions_are_specified():
    result = parse_natural_language("40 x 20 x 10 mm box with four 5 mm holes")
    assert not result.success
    assert "Multiple holes" in (result.error or "")


def test_pipe_rejects_invalid_inner_diameter():
    result = parse_natural_language("tube OD 10 mm ID 12 mm length 50 mm")
    assert not result.success
    assert "smaller than its outer diameter" in (result.error or "")


def test_sphere_requires_radius_or_diameter():
    result = parse_natural_language("sphere 20 mm")
    assert not result.success
    assert "sphere radius or diameter" in (result.error or "")


def test_unsupported_unit_system_returns_a_parse_error_not_an_exception():
    result = parse_natural_language("40 x 20 x 10 box", unit_system="furlong")
    assert not result.success
    assert "supported unit system" in (result.error or "")


def test_llm_entrypoint_consumes_unit_system_option_before_model_initialization(tmp_path):
    missing_model = tmp_path / "no-model.gguf"
    result = parse_natural_language(
        "A 20 mm cylinder",
        use_llm=True,
        unit_system=UnitSystem.CM,
        model_path=str(missing_model),
    )
    assert not result.success
    assert "Model not found" in (result.error or "")
