"""Regression tests for conservative natural-language CAD parsing."""

from ai3d_designer.core.nlp.parser import RuleBasedParser
from ai3d_designer.core.spec.models import OperationType, UnitSystem


def test_box_triplet_with_center_through_hole():
    result = RuleBasedParser().parse(
        "A 50x30x10mm box with a 5mm diameter hole through the center"
    )

    assert result.success, result.error
    assert result.spec is not None
    assert len(result.spec.features) == 2

    base, hole = result.spec.features
    assert base.parameters["width"].value == 50
    assert base.parameters["depth"].value == 30
    assert base.parameters["height"].value == 10
    assert hole.operation == OperationType.DIFFERENCE
    assert hole.parent_id == base.id
    assert hole.parameters["radius"].value == 2.5
    assert hole.parameters["height"].value > base.parameters["height"].value
    assert hole.position == [0.0, 0.0, 0.0]


def test_mixed_triplet_units_preserve_original_units():
    result = RuleBasedParser().parse("A 2 x 3 x 1 cm box")

    assert result.success, result.error
    assert result.spec is not None
    feature = result.spec.features[0]
    # Values preserved in original units (cm)
    assert feature.parameters["width"].value == 2
    assert feature.parameters["depth"].value == 3
    assert feature.parameters["height"].value == 1
    assert all(parameter.unit == UnitSystem.CM for parameter in feature.parameters.values())


def test_named_cylinder_dimensions_are_not_misread():
    result = RuleBasedParser().parse("A 20mm diameter cylinder, 50mm tall")

    assert result.success, result.error
    assert result.spec is not None
    feature = result.spec.features[0]
    assert feature.parameters["radius"].value == 10
    assert feature.parameters["height"].value == 50


def test_bare_triplet_uses_requested_default_units():
    result = RuleBasedParser().parse("4 x 2 x 1 box", unit_system=UnitSystem.CM)

    assert result.success, result.error
    assert result.spec is not None
    feature = result.spec.features[0]
    # Values preserved in requested default units (cm)
    assert feature.parameters["width"].value == 4
    assert feature.parameters["depth"].value == 2
    assert feature.parameters["height"].value == 1
    assert all(parameter.unit == UnitSystem.CM for parameter in feature.parameters.values())


def test_tube_generates_a_real_inner_bore():
    result = RuleBasedParser().parse(
        "A tube with 20mm outer diameter, 10mm inner diameter and 50mm length"
    )

    assert result.success, result.error
    assert result.spec is not None
    assert len(result.spec.features) == 2
    outer, bore = result.spec.features
    assert outer.parameters["radius"].value == 10
    assert outer.parameters["height"].value == 50
    assert bore.operation == OperationType.DIFFERENCE
    assert bore.parameters["radius"].value == 5
    assert bore.parameters["height"].value > outer.parameters["height"].value


def test_tube_wall_thickness_derives_inner_diameter():
    result = RuleBasedParser().parse(
        "A pipe with 20mm OD, 3mm wall thickness and 50mm length"
    )

    assert result.success, result.error
    assert result.spec is not None
    assert len(result.spec.features) == 2
    assert result.spec.features[0].parameters["radius"].value == 10
    assert result.spec.features[1].parameters["radius"].value == 7


def test_underspecified_shape_is_rejected_instead_of_guessing_dimensions():
    result = RuleBasedParser().parse("Make a cylinder")

    assert result.success is False
    assert "explicit" in (result.error or "").lower()


def test_tube_without_inner_diameter_or_wall_is_rejected():
    result = RuleBasedParser().parse("Make a tube with 20mm outer diameter and 50mm length")

    assert result.success is False
    assert "inner diameter or wall thickness" in (result.error or "").lower()


def test_unpositioned_multiple_holes_are_not_guessed():
    result = RuleBasedParser().parse("A 50x30x10mm box with four 5mm holes")

    assert result.success is False
    assert "explicit positions" in (result.error or "").lower()


def test_plate_with_explicit_thickness():
    result = RuleBasedParser().parse("A 100 x 50 mm plate, 5 mm thick")

    assert result.success, result.error
    assert result.spec is not None
    feature = result.spec.features[0]
    assert feature.parameters["width"].value == 100
    assert feature.parameters["depth"].value == 50
    assert feature.parameters["height"].value == 5


def test_parser_rejects_unbounded_numeric_tokens_instead_of_truncating():
    result = RuleBasedParser().parse("A 100000000 x 30 x 10 mm box")
    assert result.success is False
    assert "explicit" in (result.error or "").lower()


def test_parser_rejects_overlong_untrusted_descriptions():
    result = RuleBasedParser().parse("box " + ("0" * 5000))
    assert result.success is False
    assert "character parser limit" in (result.error or "").lower()


def test_bounded_number_grammar_keeps_normal_decimal_dimensions():
    result = RuleBasedParser().parse("A 12.5 x 8.25 x 3.75 mm box")
    assert result.success, result.error
    assert result.spec is not None
    feature = result.spec.features[0]
    assert feature.parameters["width"].value == 12.5
    assert feature.parameters["depth"].value == 8.25
    assert feature.parameters["height"].value == 3.75


def test_public_parser_entry_point_enforces_description_limit():
    from ai3d_designer.core.nlp.parser import parse_natural_language

    result = parse_natural_language("box " + ("x" * 5000), use_llm=False)
    assert result.success is False
    assert "character parser limit" in (result.error or "").lower()
