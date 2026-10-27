"""
Comprehensive tests for the printability module.
"""

import pytest
from math import isclose

from ai3d_designer.core.spec.models import (
    PartSpec, FeatureSpec, ParameterSpec,
    PrimitiveType, OperationType, UnitSystem
)
from ai3d_designer.printability.checks import (
    PrintabilityChecker,
    CheckResult,
    CheckStatus,
    run_all_checks,
)
from ai3d_designer.printability.explanations import (
    EXPLANATIONS,
    GLOSSARY,
    get_explanation,
    get_glossary_entry,
)
from ai3d_designer.printability.fixes import (
    FixAction,
    FixResult,
    apply_fix_and_reverify,
    get_available_fixes,
)
from ai3d_designer.core.geometry.engine import create_part_from_spec
from ai3d_designer.core.validation.validator import validate_geometry


def create_box_spec(width: float, depth: float, height: float, name: str = "Test Box") -> PartSpec:
    """Create a simple box PartSpec."""
    return PartSpec(
        name=name,
        description="Test box",
        unit_system=UnitSystem.MM,
        features=[
            FeatureSpec(
                id="base",
                type=PrimitiveType.BOX,
                name="Base Box",
                parameters={
                    "width": ParameterSpec(name="width", value=width, unit=UnitSystem.MM),
                    "depth": ParameterSpec(name="depth", value=depth, unit=UnitSystem.MM),
                    "height": ParameterSpec(name="height", value=height, unit=UnitSystem.MM),
                },
                position=[0.0, 0.0, 0.0],
                rotation=[0.0, 0.0, 0.0],
                operation=OperationType.UNION,
            )
        ],
    )


def create_box_with_hole_spec(
    width: float, depth: float, height: float,
    hole_diameter: float, hole_x: float = 0.0, hole_y: float = 0.0
) -> PartSpec:
    """Create a box with a through hole."""
    return PartSpec(
        name="Box with Hole",
        description="Box with center hole",
        unit_system=UnitSystem.MM,
        features=[
            FeatureSpec(
                id="base",
                type=PrimitiveType.BOX,
                name="Base Box",
                parameters={
                    "width": ParameterSpec(name="width", value=width, unit=UnitSystem.MM),
                    "depth": ParameterSpec(name="depth", value=depth, unit=UnitSystem.MM),
                    "height": ParameterSpec(name="height", value=height, unit=UnitSystem.MM),
                },
                position=[0.0, 0.0, 0.0],
                rotation=[0.0, 0.0, 0.0],
                operation=OperationType.UNION,
            ),
            FeatureSpec(
                id="hole",
                type=PrimitiveType.CYLINDER,
                name="Through Hole",
                parameters={
                    "radius": ParameterSpec(name="radius", value=hole_diameter / 2.0, unit=UnitSystem.MM),
                    "height": ParameterSpec(name="height", value=height + 2.0, unit=UnitSystem.MM),
                },
                position=[hole_x, hole_y, 0.0],
                rotation=[0.0, 0.0, 0.0],
                operation=OperationType.DIFFERENCE,
                parent_id="base",
            )
        ],
    )


def create_thin_wall_spec() -> PartSpec:
    """Create a spec with walls thinner than 0.8mm."""
    return PartSpec(
        name="Thin Wall Box",
        description="Box with thin walls",
        unit_system=UnitSystem.MM,
        features=[
            FeatureSpec(
                id="outer",
                type=PrimitiveType.BOX,
                name="Outer Box",
                parameters={
                    "width": ParameterSpec(name="width", value=50.0, unit=UnitSystem.MM),
                    "depth": ParameterSpec(name="depth", value=30.0, unit=UnitSystem.MM),
                    "height": ParameterSpec(name="height", value=10.0, unit=UnitSystem.MM),
                },
                position=[0.0, 0.0, 0.0],
                rotation=[0.0, 0.0, 0.0],
                operation=OperationType.UNION,
            ),
            FeatureSpec(
                id="inner",
                type=PrimitiveType.BOX,
                name="Inner Cavity",
                parameters={
                    "width": ParameterSpec(name="width", value=49.6, unit=UnitSystem.MM),  # 0.2mm wall
                    "depth": ParameterSpec(name="depth", value=29.6, unit=UnitSystem.MM),  # 0.2mm wall
                    "height": ParameterSpec(name="height", value=9.0, unit=UnitSystem.MM),
                },
                position=[0.0, 0.0, 0.5],
                rotation=[0.0, 0.0, 0.0],
                operation=OperationType.DIFFERENCE,
                parent_id="outer",
            )
        ],
    )


def create_overhang_spec() -> PartSpec:
    """Create a spec with significant overhangs (sharp cone)."""
    return PartSpec(
        name="Overhang Test",
        description="Sharp cone with steep overhang",
        unit_system=UnitSystem.MM,
        features=[
            FeatureSpec(
                id="cone",
                type=PrimitiveType.CONE,
                name="Cone",
                parameters={
                    "radius_bottom": ParameterSpec(name="radius_bottom", value=20.0, unit=UnitSystem.MM),
                    "radius_top": ParameterSpec(name="radius_top", value=1.0, unit=UnitSystem.MM),
                    "height": ParameterSpec(name="height", value=30.0, unit=UnitSystem.MM),
                },
                position=[0.0, 0.0, 0.0],
                rotation=[0.0, 0.0, 0.0],
                operation=OperationType.UNION,
            )
        ],
    )


def create_tall_part_spec() -> PartSpec:
    """Create a part taller than bed Z but fits on side."""
    # Cylinder: radius 20mm (diameter 40mm), height 200mm (fits on side: 40x200 footprint, 40 height)
    return PartSpec(
        name="Tall Part",
        description="Tall vertical part",
        unit_system=UnitSystem.MM,
        features=[
            FeatureSpec(
                id="base",
                type=PrimitiveType.CYLINDER,
                name="Tall Cylinder",
                parameters={
                    "radius": ParameterSpec(name="radius", value=20.0, unit=UnitSystem.MM),
                    "height": ParameterSpec(name="height", value=200.0, unit=UnitSystem.MM),  # 200mm < 250mm bed Z when on side
                },
                position=[0.0, 0.0, 0.0],
                rotation=[0.0, 0.0, 0.0],
                operation=OperationType.UNION,
            )
        ],
    )


def create_bridge_spec() -> PartSpec:
    """Create a part with a long bridge (horizontal face between supports)."""
    return PartSpec(
        name="Bridge Test",
        description="Part with 10mm bridge",
        unit_system=UnitSystem.MM,
        features=[
            FeatureSpec(
                id="left",
                type=PrimitiveType.BOX,
                name="Left Support",
                parameters={
                    "width": ParameterSpec(name="width", value=20.0, unit=UnitSystem.MM),
                    "depth": ParameterSpec(name="depth", value=30.0, unit=UnitSystem.MM),
                    "height": ParameterSpec(name="height", value=20.0, unit=UnitSystem.MM),
                },
                position=[-25.0, 0.0, 0.0],
                rotation=[0.0, 0.0, 0.0],
                operation=OperationType.UNION,
            ),
            FeatureSpec(
                id="right",
                type=PrimitiveType.BOX,
                name="Right Support",
                parameters={
                    "width": ParameterSpec(name="width", value=20.0, unit=UnitSystem.MM),
                    "depth": ParameterSpec(name="depth", value=30.0, unit=UnitSystem.MM),
                    "height": ParameterSpec(name="height", value=20.0, unit=UnitSystem.MM),
                },
                position=[25.0, 0.0, 0.0],
                rotation=[0.0, 0.0, 0.0],
                operation=OperationType.UNION,
            ),
            FeatureSpec(
                id="bridge",
                type=PrimitiveType.BOX,
                name="Bridge",
                parameters={
                    "width": ParameterSpec(name="width", value=30.0, unit=UnitSystem.MM),  # 30mm span
                    "depth": ParameterSpec(name="depth", value=30.0, unit=UnitSystem.MM),
                    "height": ParameterSpec(name="height", value=5.0, unit=UnitSystem.MM),
                },
                position=[0.0, 0.0, 20.0],
                rotation=[0.0, 0.0, 0.0],
                operation=OperationType.UNION,
            )
        ],
    )


def create_small_base_spec() -> PartSpec:
    """Create a part with tiny base contact (cone on tip).
    
    Cone is rotated 180° around X-axis so tip points down (at Z=0).
    """
    return PartSpec(
        name="Small Base",
        description="Cone on tip",
        unit_system=UnitSystem.MM,
        features=[
            FeatureSpec(
                id="cone",
                type=PrimitiveType.CONE,
                name="Cone",
                parameters={
                    "radius_bottom": ParameterSpec(name="radius_bottom", value=20.0, unit=UnitSystem.MM),
                    "radius_top": ParameterSpec(name="radius_top", value=0.5, unit=UnitSystem.MM),
                    "height": ParameterSpec(name="height", value=30.0, unit=UnitSystem.MM),
                },
                position=[0.0, 0.0, 0.0],
                rotation=[180.0, 0.0, 0.0],  # Rotate so tip is at Z=0
                operation=OperationType.UNION,
            )
        ],
    )


def create_hole_near_edge_spec() -> PartSpec:
    """Create a box with hole very close to edge."""
    return PartSpec(
        name="Hole Near Edge",
        description="Box with hole near wall",
        unit_system=UnitSystem.MM,
        features=[
            FeatureSpec(
                id="base",
                type=PrimitiveType.BOX,
                name="Base Box",
                parameters={
                    "width": ParameterSpec(name="width", value=50.0, unit=UnitSystem.MM),
                    "depth": ParameterSpec(name="depth", value=30.0, unit=UnitSystem.MM),
                    "height": ParameterSpec(name="height", value=10.0, unit=UnitSystem.MM),
                },
                position=[0.0, 0.0, 0.0],
                rotation=[0.0, 0.0, 0.0],
                operation=OperationType.UNION,
            ),
            FeatureSpec(
                id="hole",
                type=PrimitiveType.CYLINDER,
                name="Edge Hole",
                parameters={
                    "radius": ParameterSpec(name="radius", value=5.0, unit=UnitSystem.MM),
                    "height": ParameterSpec(name="height", value=12.0, unit=UnitSystem.MM),
                },
                position=[24.0, 0.0, 0.0],  # Hole center at 24mm, radius 5 -> edge at 29mm, box edge at 25mm
                rotation=[0.0, 0.0, 0.0],
                operation=OperationType.DIFFERENCE,
                parent_id="base",
            )
        ],
    )


def create_warped_bottom_spec() -> PartSpec:
    """Create a part with non-flat bottom (multiple bottom faces at different Z)."""
    return PartSpec(
        name="Warped Bottom",
        description="Part with uneven bottom",
        unit_system=UnitSystem.MM,
        features=[
            FeatureSpec(
                id="base",
                type=PrimitiveType.BOX,
                name="Base",
                parameters={
                    "width": ParameterSpec(name="width", value=50.0, unit=UnitSystem.MM),
                    "depth": ParameterSpec(name="depth", value=30.0, unit=UnitSystem.MM),
                    "height": ParameterSpec(name="height", value=10.0, unit=UnitSystem.MM),
                },
                position=[0.0, 0.0, 0.0],
                rotation=[0.0, 0.0, 0.0],
                operation=OperationType.UNION,
            ),
            FeatureSpec(
                id="bump",
                type=PrimitiveType.BOX,
                name="Bottom Bump",
                parameters={
                    "width": ParameterSpec(name="width", value=10.0, unit=UnitSystem.MM),
                    "depth": ParameterSpec(name="depth", value=10.0, unit=UnitSystem.MM),
                    "height": ParameterSpec(name="height", value=0.5, unit=UnitSystem.MM),
                },
                position=[0.0, 0.0, -5.0],  # Below base bottom
                rotation=[0.0, 0.0, 0.0],
                operation=OperationType.UNION,
            )
        ],
    )


def create_very_tall_part_spec() -> PartSpec:
    """Create a part too tall for default bed in any orientation (300mm)."""
    return PartSpec(
        name="Very Tall Part",
        description="Very tall vertical part",
        unit_system=UnitSystem.MM,
        features=[
            FeatureSpec(
                id="base",
                type=PrimitiveType.CYLINDER,
                name="Tall Cylinder",
                parameters={
                    "radius": ParameterSpec(name="radius", value=20.0, unit=UnitSystem.MM),
                    "height": ParameterSpec(name="height", value=300.0, unit=UnitSystem.MM),
                },
                position=[0.0, 0.0, 0.0],
                rotation=[0.0, 0.0, 0.0],
                operation=OperationType.UNION,
            )
        ],
    )


class TestPrintabilityChecks:
    """Tests for the 8 printability checks."""

    def test_min_wall_thickness_pass(self):
        """Thick walls should pass."""
        spec = create_box_spec(50, 30, 10)
        results = run_all_checks(spec)
        wall_check = next(r for r in results if r.check_id == "min_wall_thickness")
        assert wall_check.status == CheckStatus.PASS
        assert wall_check.value is not None
        assert wall_check.value >= 0.8

    def test_min_wall_thickness_fail(self):
        """Thin walls should fail."""
        spec = create_thin_wall_spec()
        results = run_all_checks(spec)
        wall_check = next(r for r in results if r.check_id == "min_wall_thickness")
        assert wall_check.status == CheckStatus.FAIL
        assert wall_check.value is not None
        assert wall_check.value < 0.8

    def test_hole_size_pass(self):
        """Large holes should pass."""
        spec = create_box_with_hole_spec(50, 30, 10, hole_diameter=5.0)
        results = run_all_checks(spec)
        hole_check = next(r for r in results if r.check_id == "hole_size")
        assert hole_check.status == CheckStatus.PASS
        assert hole_check.value is not None
        assert hole_check.value >= 2.0

    def test_hole_size_fail(self):
        """Small holes should fail."""
        spec = create_box_with_hole_spec(50, 30, 10, hole_diameter=1.0)
        results = run_all_checks(spec)
        hole_check = next(r for r in results if r.check_id == "hole_size")
        assert hole_check.status == CheckStatus.FAIL
        assert hole_check.value is not None
        assert hole_check.value < 2.0

    def test_overhang_angle_pass(self):
        """Shallow overhangs (vertical walls) should pass."""
        spec = create_box_spec(50, 30, 10)
        results = run_all_checks(spec)
        overhang_check = next(r for r in results if r.check_id == "overhang_angle")
        assert overhang_check.status == CheckStatus.PASS
        assert overhang_check.value is not None
        assert overhang_check.value <= 45.0

    def test_overhang_angle_warning(self):
        """Significant overhangs should warn."""
        spec = create_overhang_spec()
        results = run_all_checks(spec)
        overhang_check = next(r for r in results if r.check_id == "overhang_angle")
        assert overhang_check.status == CheckStatus.WARNING
        assert overhang_check.value is not None
        assert overhang_check.value > 45.0

    def test_bed_fit_all_orientations(self):
        """Test bed fit in 6 orientations."""
        spec = create_tall_part_spec()
        results = run_all_checks(spec)
        bed_checks = [r for r in results if r.check_id.startswith("bed_fit_")]
        assert len(bed_checks) == 6
        fit_results = [r for r in bed_checks if r.status == CheckStatus.PASS]
        assert len(fit_results) > 0, f"No orientation fits! Results: {[(r.orientation, r.status) for r in bed_checks]}"
        upright = next(r for r in bed_checks if "pos_z" in r.check_id.lower() or "upright" in r.orientation.lower())
        assert upright.status == CheckStatus.PASS

    def test_bridging_span_pass(self):
        """Short bridges (solid top on box) should pass - top is supported by walls."""
        spec = create_box_spec(50, 30, 10)
        results = run_all_checks(spec)
        bridge_check = next(r for r in results if r.check_id == "bridging_span")
        assert bridge_check.status == CheckStatus.PASS

    def test_bridging_span_warning(self):
        """Long bridges should warn."""
        spec = create_bridge_spec()
        results = run_all_checks(spec)
        bridge_check = next(r for r in results if r.check_id == "bridging_span")
        assert bridge_check.status == CheckStatus.WARNING
        assert bridge_check.value is not None
        assert bridge_check.value > 5.0

    def test_base_contact_pass(self):
        """Large base contact should pass."""
        spec = create_box_spec(50, 30, 10)
        results = run_all_checks(spec)
        base_check = next(r for r in results if r.check_id == "base_contact")
        assert base_check.status == CheckStatus.PASS
        assert base_check.value is not None
        assert base_check.value >= 20.0

    def test_base_contact_warning(self):
        """Small base contact should warn."""
        spec = create_small_base_spec()
        results = run_all_checks(spec)
        base_check = next(r for r in results if r.check_id == "base_contact")
        assert base_check.status == CheckStatus.WARNING
        assert base_check.value is not None
        assert base_check.value < 20.0

    def test_hole_edge_distance_pass(self):
        """Holes far from edges should pass."""
        spec = create_box_with_hole_spec(50, 30, 10, hole_diameter=5.0, hole_x=0.0, hole_y=0.0)
        results = run_all_checks(spec)
        edge_check = next(r for r in results if r.check_id == "hole_edge_distance")
        assert edge_check.status == CheckStatus.PASS
        assert edge_check.value is not None
        assert edge_check.value >= 1.0

    def test_hole_edge_distance_fail(self):
        """Holes too close to edges should fail."""
        spec = create_hole_near_edge_spec()
        results = run_all_checks(spec)
        edge_check = next(r for r in results if r.check_id == "hole_edge_distance")
        assert edge_check.status == CheckStatus.FAIL
        assert edge_check.value is not None
        assert edge_check.value < 1.0

    def test_flatness_pass(self):
        """Flat bottom should pass."""
        spec = create_box_spec(50, 30, 10)
        results = run_all_checks(spec)
        flat_check = next(r for r in results if r.check_id == "flatness")
        assert flat_check.status == CheckStatus.PASS
        assert flat_check.value is not None
        assert flat_check.value <= 0.2

    def test_flatness_warning(self):
        """Warped bottom should warn."""
        spec = create_warped_bottom_spec()
        results = run_all_checks(spec)
        flat_check = next(r for r in results if r.check_id == "flatness")
        assert flat_check.status == CheckStatus.WARNING
        assert flat_check.value is not None
        assert flat_check.value > 0.2

    def test_all_checks_return_results(self):
        """All 8 checks should return results."""
        spec = create_box_spec(50, 30, 10)
        results = run_all_checks(spec)
        check_ids = {r.check_id for r in results}
        expected = {
            "min_wall_thickness", "hole_size", "overhang_angle",
            "bed_fit_posZ_upright", "bed_fit_negZ_inverted",
            "bed_fit_posX_on_side", "bed_fit_negX_on_side",
            "bed_fit_posY_on_side", "bed_fit_negY_on_side",
            "bridging_span", "base_contact", "hole_edge_distance", "flatness"
        }
        for exp in expected:
            assert exp in check_ids, f"Missing check: {exp}"

    def test_check_result_structure(self):
        """CheckResult should have all required fields."""
        spec = create_box_spec(50, 30, 10)
        results = run_all_checks(spec)
        for r in results:
            assert r.check_id
            assert r.name
            assert r.status in CheckStatus
            assert r.unit
            assert r.details
            assert isinstance(r.affected_features, list)
            # to_dict should work
            d = r.to_dict()
            assert d["check_id"] == r.check_id
            assert d["status"] == r.status.value


class TestExplanations:
    """Tests for explanation texts and glossary."""

    def test_all_checks_have_explanations(self):
        """Every check ID should have an explanation."""
        spec = create_box_spec(50, 30, 10)
        results = run_all_checks(spec)
        for r in results:
            exp = get_explanation(r.check_id)
            assert exp is not None, f"No explanation for {r.check_id}"
            assert "what" in exp
            assert "why" in exp
            assert "fix" in exp
            assert "learn_more" in exp

    def test_glossary_has_entries(self):
        """Glossary should have entries for key terms."""
        key_terms = ["overhang", "bridging", "wall thickness", "hole diameter", "bed adhesion", "flatness"]
        for term in key_terms:
            entry = get_glossary_entry(term)
            assert entry is not None, f"No glossary entry for {term}"
            assert len(entry) > 10

    def test_explanation_content_quality(self):
        """Explanations should be non-trivial and helpful."""
        exp = get_explanation("overhang_angle")
        assert len(exp["what"]) > 20
        assert len(exp["why"]) > 20
        assert len(exp["fix"]) > 20
        assert len(exp["learn_more"]) > 10


class TestFixes:
    """Tests for 1-click fix actions."""

    def test_rotate_fix_for_bed_fit(self):
        """Rotate should fix bed fit for tall part."""
        # Use a part that's too tall for upright but fits on side with larger bed
        # 300mm tall cylinder with 40mm diameter - needs bed with X>=300 when on side
        tall_spec = PartSpec(
            name="Very Tall Part",
            description="Very tall vertical part",
            unit_system=UnitSystem.MM,
            features=[
                FeatureSpec(
                    id="base",
                    type=PrimitiveType.CYLINDER,
                    name="Tall Cylinder",
                    parameters={
                        "radius": ParameterSpec(name="radius", value=20.0, unit=UnitSystem.MM),
                        "height": ParameterSpec(name="height", value=300.0, unit=UnitSystem.MM),
                    },
                    position=[0.0, 0.0, 0.0],
                    rotation=[0.0, 0.0, 0.0],
                    operation=OperationType.UNION,
                )
            ],
        )
        # Use larger bed for this test (400x400x250)
        bed_size = (400.0, 400.0, 250.0)
        results = run_all_checks(tall_spec, bed_size=bed_size)
        
        # Find failing upright bed fit
        upright_fail = next(r for r in results if r.check_id.startswith("bed_fit_") and r.status == CheckStatus.FAIL)
        
        # Apply rotate fix with same bed size
        fix_result = apply_fix_and_reverify(
            tall_spec, FixAction.ROTATE, upright_fail.check_id,
            {"orientation": "+X (on side)"},
            bed_size=bed_size
        )
        
        assert fix_result.success
        assert fix_result.modified_spec is not None
        assert len(fix_result.new_checks) > 0
        
        # Check that the new orientation passes
        new_bed_checks = [r for r in fix_result.new_checks if r.check_id.startswith("bed_fit_")]
        side_pass = any(r.status == CheckStatus.PASS and r.orientation == "+X (on side)" for r in new_bed_checks)
        assert side_pass, f"No side orientation passes: {[(r.check_id, r.status) for r in new_bed_checks]}"

    def test_thicken_fix_for_wall(self):
        """Thicken should fix thin walls."""
        spec = create_thin_wall_spec()
        results = run_all_checks(spec)
        wall_check = next(r for r in results if r.check_id == "min_wall_thickness")
        assert wall_check.status == CheckStatus.FAIL
        
        fix_result = apply_fix_and_reverify(
            spec, FixAction.THICKEN, "min_wall_thickness",
            {"min_thickness": 1.0}
        )
        
        assert fix_result.success
        new_wall_check = next(r for r in fix_result.new_checks if r.check_id == "min_wall_thickness")
        assert new_wall_check.status == CheckStatus.PASS
        assert new_wall_check.value >= 1.0

    def test_enlarge_fix_for_hole_size(self):
        """Enlarge should fix small holes."""
        spec = create_box_with_hole_spec(50, 30, 10, hole_diameter=1.0)
        results = run_all_checks(spec)
        hole_check = next(r for r in results if r.check_id == "hole_size")
        assert hole_check.status == CheckStatus.FAIL
        
        fix_result = apply_fix_and_reverify(
            spec, FixAction.ENLARGE, "hole_size",
            {"min_diameter": 2.0}
        )
        
        assert fix_result.success
        new_hole_check = next(r for r in fix_result.new_checks if r.check_id == "hole_size")
        assert new_hole_check.status == CheckStatus.PASS
        assert new_hole_check.value >= 2.0

    def test_enlarge_fix_for_hole_edge(self):
        """Enlarge should fix hole-to-edge distance by expanding parent."""
        spec = create_hole_near_edge_spec()
        results = run_all_checks(spec)
        edge_check = next(r for r in results if r.check_id == "hole_edge_distance")
        assert edge_check.status == CheckStatus.FAIL
        
        # Need min_distance=5 to expand box from 50 to 60 (half-width 25->30, hole edge at 29, distance=1)
        fix_result = apply_fix_and_reverify(
            spec, FixAction.ENLARGE, "hole_edge_distance",
            {"min_distance": 5.0}
        )
        
        assert fix_result.success
        new_edge_check = next(r for r in fix_result.new_checks if r.check_id == "hole_edge_distance")
        assert new_edge_check.status == CheckStatus.PASS
        assert new_edge_check.value >= 1.0

    def test_add_support_fix_for_overhang(self):
        """Add support should mark overhangs for support."""
        spec = create_overhang_spec()
        results = run_all_checks(spec)
        
        overhang_check = next(r for r in results if r.check_id == "overhang_angle")
        assert overhang_check.status == CheckStatus.WARNING
        
        fix_result = apply_fix_and_reverify(
            spec, FixAction.ADD_SUPPORT, "overhang_angle",
            {"support_angle": 45.0}
        )
        
        assert fix_result.success
        # Support doesn't change geometry, but marks for slicer
        # The check still warns (geometry unchanged) but metadata is added
        for feat in fix_result.modified_spec.features:
            assert feat.metadata.get("needs_support") is True

    def test_split_fix_for_bed_fit(self):
        """Split should mark part for splitting."""
        spec = create_very_tall_part_spec()
        bed_size = (400.0, 400.0, 250.0)
        results = run_all_checks(spec, bed_size=bed_size)
        bed_check = next(r for r in results if r.check_id.startswith("bed_fit_") and r.status == CheckStatus.FAIL)
        
        fix_result = apply_fix_and_reverify(
            spec, FixAction.SPLIT, bed_check.check_id,
            {"axis": "Z", "position": 0.5},
            bed_size=bed_size
        )
        
        assert fix_result.success
        for feat in fix_result.modified_spec.features:
            assert feat.metadata.get("split") is not None
            assert feat.metadata["split"]["axis"] == "Z"

    def test_invalid_fix_action_rejected(self):
        """Invalid fix action should return error."""
        spec = create_box_spec(50, 30, 10)
        result = apply_fix_and_reverify(spec, "invalid_action", "min_wall_thickness")
        assert not result.success
        assert result.error is not None

    def test_fix_preserves_spec_validity(self):
        """Fixed spec should still be valid."""
        spec = create_thin_wall_spec()
        fix_result = apply_fix_and_reverify(spec, FixAction.THICKEN, "min_wall_thickness", {"min_thickness": 1.0})
        assert fix_result.success
        errors = fix_result.modified_spec.validate_spec()
        assert len(errors) == 0

    def test_fix_rebuilds_geometry(self):
        """Fixed spec should produce valid geometry."""
        spec = create_thin_wall_spec()
        fix_result = apply_fix_and_reverify(spec, FixAction.THICKEN, "min_wall_thickness", {"min_thickness": 1.0})
        assert fix_result.success
        part = create_part_from_spec(fix_result.modified_spec)
        assert part is not None
        assert part.volume > 0


class TestCheckerConfiguration:
    """Tests for checker configuration options."""

    def test_custom_thresholds(self):
        """Custom thresholds should be respected."""
        spec = create_box_spec(50, 30, 10)
        # Default min wall is 0.8, box has 50mm walls - passes
        results = run_all_checks(spec, thresholds={"min_wall_thickness": 100.0})
        wall_check = next(r for r in results if r.check_id == "min_wall_thickness")
        assert wall_check.status == CheckStatus.FAIL
        assert wall_check.threshold == 100.0

    def test_custom_bed_size(self):
        """Custom bed size should be respected."""
        spec = create_tall_part_spec()  # 200mm tall cylinder
        # Default bed Z is 250, so upright fits
        results = run_all_checks(spec)
        upright = next(r for r in results if "posz" in r.check_id.lower() or "upright" in r.orientation.lower())
        assert upright.status == CheckStatus.PASS
        
        # With smaller bed Z
        results = run_all_checks(spec, bed_size=(220.0, 220.0, 150.0))
        upright = next(r for r in results if "posz" in r.check_id.lower() or "upright" in r.orientation.lower())
        assert upright.status == CheckStatus.FAIL


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_spec(self):
        """Empty spec should be handled gracefully."""
        spec = PartSpec(name="Empty", description="", unit_system=UnitSystem.MM, features=[])
        results = run_all_checks(spec)
        assert len(results) == 1
        assert results[0].check_id == "build_error"
        assert results[0].status == CheckStatus.FAIL

    def test_invalid_spec_handling(self):
        """Invalid spec should return build error."""
        spec = PartSpec(
            name="Invalid",
            description="",
            unit_system=UnitSystem.MM,
            features=[
                FeatureSpec(
                    id="bad",
                    type=PrimitiveType.BOX,
                    name="Bad Box",
                    parameters={
                        "width": ParameterSpec(name="width", value=-10.0, unit=UnitSystem.MM),
                        "depth": ParameterSpec(name="depth", value=30.0, unit=UnitSystem.MM),
                        "height": ParameterSpec(name="height", value=10.0, unit=UnitSystem.MM),
                    },
                    position=[0.0, 0.0, 0.0],
                    rotation=[0.0, 0.0, 0.0],
                    operation=OperationType.UNION,
                )
            ],
        )
        results = run_all_checks(spec)
        assert len(results) == 1
        assert results[0].check_id == "build_error"
        assert results[0].status == CheckStatus.FAIL

    def test_check_result_serialization(self):
        """CheckResult should serialize to dict."""
        spec = create_box_spec(50, 30, 10)
        results = run_all_checks(spec)
        for r in results:
            d = r.to_dict()
            assert isinstance(d, dict)
            assert "check_id" in d
            assert "status" in d
            assert "details" in d
