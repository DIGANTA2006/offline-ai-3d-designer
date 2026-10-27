"""
Updated tests for the parser with Question Engine (T22) and source/confirmed fields.
"""

import pytest
from ai3d_designer.core.nlp.parser import RuleBasedParser, parse_natural_language
from ai3d_designer.core.spec.models import OperationType, UnitSystem, ParameterSource


def test_parser_returns_question_for_missing_width():
    """Test that parser returns a question when box width is missing."""
    result = RuleBasedParser().parse("A 30x10mm box")  # Missing width

    assert result.success is False
    assert result.current_question is not None
    assert result.current_question["parameter"] == "width"
    assert result.current_question["primitive_type"] == "box"
    assert "width" in result.current_question["question"].lower()
    assert result.current_question["hint"] is not None
    assert "caliper" in result.current_question["hint"].lower()


def test_parser_returns_question_for_missing_height():
    """Test that parser returns a question when box height is missing."""
    result = RuleBasedParser().parse("A 50x30mm box")  # Missing height

    assert result.success is False
    assert result.current_question is not None
    assert result.current_question["parameter"] == "height"
    assert "height" in result.current_question["question"].lower() or "thickness" in result.current_question["question"].lower()


def test_parser_returns_question_for_missing_cylinder_radius():
    """Test that parser returns a question when cylinder radius is missing."""
    result = RuleBasedParser().parse("A 50mm tall cylinder")  # Missing radius/diameter

    assert result.success is False
    assert result.current_question is not None
    assert result.current_question["parameter"] in ("radius", "diameter")
    assert "radius" in result.current_question["question"].lower() or "diameter" in result.current_question["question"].lower()


def test_parser_returns_question_for_missing_sphere_radius():
    """Test that parser returns a question when sphere radius is missing."""
    result = RuleBasedParser().parse("Make a sphere")  # Missing radius/diameter

    assert result.success is False
    assert result.current_question is not None
    assert result.current_question["parameter"] in ("radius", "diameter")


def test_parser_returns_question_for_missing_cone_radius():
    """Test that parser returns a question when cone base radius is missing."""
    result = RuleBasedParser().parse("A 50mm tall cone")  # Missing base radius

    assert result.success is False
    assert result.current_question is not None
    assert result.current_question["parameter"] in ("radius", "diameter", "radius_bottom")


def test_parser_returns_question_for_missing_torus_radius():
    """Test that parser returns a question when torus radii are missing."""
    result = RuleBasedParser().parse("Make a torus")  # Missing radii

    assert result.success is False
    assert result.current_question is not None
    assert result.current_question["parameter"] in ("major_radius", "minor_radius", "radius")


def test_parser_returns_question_for_missing_hole_diameter():
    """Test that parser returns a question when hole diameter is missing."""
    result = RuleBasedParser().parse("A 50x30x10mm box with a hole")  # Missing hole diameter

    assert result.success is False
    assert result.current_question is not None
    assert result.current_question["parameter"] == "hole_diameter"
    assert "hole" in result.current_question["question"].lower()


def test_parser_returns_question_for_missing_tube_inner_diameter():
    """Test that parser returns a question when tube inner diameter is missing."""
    result = RuleBasedParser().parse("A tube with 20mm outer diameter and 50mm length")  # Missing inner diameter

    assert result.success is False
    assert result.current_question is not None
    assert result.current_question["parameter"] == "inner_diameter"
    assert "inner diameter" in result.current_question["question"].lower() or "wall thickness" in result.current_question["question"].lower()


def test_parser_succeeds_when_all_dimensions_provided():
    """Test that parser succeeds when all required dimensions are provided."""
    result = RuleBasedParser().parse("A 50x30x10mm box with a 5mm hole")

    assert result.success is True
    assert result.spec is not None
    assert len(result.spec.features) == 2
    assert result.current_question is None


def test_parser_parameters_have_source_and_confirmed():
    """Test that parsed parameters have source and confirmed fields."""
    result = RuleBasedParser().parse("A 50x30x10mm box")

    assert result.success is True
    feature = result.spec.features[0]
    for param in feature.parameters.values():
        assert param.source == ParameterSource.USER
        assert param.confirmed is True


def test_parser_hole_parameters_have_source_and_confirmed():
    """Test that hole parameters have source and confirmed fields."""
    result = RuleBasedParser().parse("A 50x30x10mm box with a 5mm hole")

    assert result.success is True
    hole = result.spec.features[1]
    for param in hole.parameters.values():
        assert param.source == ParameterSource.USER
        assert param.confirmed is True


def test_parser_missing_parameters_list():
    """Test that missing_parameters list is populated."""
    result = RuleBasedParser().parse("A box")  # Missing all dimensions

    assert result.success is False
    assert result.missing_parameters is not None
    assert len(result.missing_parameters) > 0
    # Should have width, depth, height
    param_names = [p["parameter"] for p in result.missing_parameters]
    assert "width" in param_names
    assert "depth" in param_names
    assert "height" in param_names


def test_parser_question_engine_one_at_a_time():
    """Test that question engine returns one question at a time."""
    result = RuleBasedParser().parse("A box")  # Missing width, depth, height

    assert result.success is False
    assert result.current_question is not None
    # Should only return the first missing parameter
    assert result.current_question["parameter"] == "width"
    # But missing_parameters should list all
    assert len(result.missing_parameters) == 3


def test_parse_natural_language_entry_point():
    """Test the main parse_natural_language entry point."""
    result = parse_natural_language("A 50x30x10mm box", use_llm=False)

    assert result.success is True
    assert result.spec is not None


def test_parse_natural_language_with_question():
    """Test parse_natural_language returns question for missing dims."""
    result = parse_natural_language("A box", use_llm=False)

    assert result.success is False
    assert result.current_question is not None


def test_unsupported_features_still_rejected():
    """Test that unsupported features are still rejected (T23)."""
    result = parse_natural_language("A 50x30x10mm box with filleted edges", use_llm=False)

    assert result.success is False
    assert "fillet" in (result.error or "").lower()


def test_multiple_holes_still_rejected():
    """Test that multiple holes without positions are rejected."""
    result = parse_natural_language("A 50x30x10mm box with four 5mm holes", use_llm=False)

    assert result.success is False
    assert "multiple holes" in (result.error or "").lower()


def test_tube_without_inner_diameter_rejected():
    """Test that tube without inner diameter is rejected."""
    result = parse_natural_language("A tube with 20mm outer diameter and 50mm length", use_llm=False)

    assert result.success is False
    assert "inner diameter or wall thickness" in (result.error or "").lower()


def test_measuring_hints_are_present():
    """Test that measuring hints are present for all parameters."""
    parser = RuleBasedParser()
    
    # Check all required params have hints
    for prim_type, params in parser.REQUIRED_PARAMS.items():
        for param in params:
            assert param in parser.MEASURING_HINTS, f"Missing hint for {param}"
            hint = parser.MEASURING_HINTS[param]
            assert len(hint) > 10, f"Hint too short for {param}"
            assert "measure" in hint.lower() or "caliper" in hint.lower(), f"Hint not actionable for {param}"


def test_parser_rejects_unknown_primitive():
    """Test that unknown primitives are rejected."""
    result = parse_natural_language("Make a gear with 20 teeth", use_llm=False)

    assert result.success is False
    assert "supported primitive" in (result.error or "").lower()


def test_parser_rejects_sweep_loft():
    """Test that sweep and loft are rejected as unsupported."""
    result = parse_natural_language("A sweep along a path", use_llm=False)
    assert result.success is False
    assert "sweep" in (result.error or "").lower()

    result = parse_natural_language("A loft between profiles", use_llm=False)
    assert result.success is False
    assert "loft" in (result.error or "").lower()
