import unittest

from ai3d_designer.drawing_to_cad.sprocket_spec import (
    CHAIN_TABLE, Severity, SprocketSpec, axis_extent_bounds_mm, derive,
    has_errors, implied_pitch_mm, outside_diameter_mm, pitch_diameter_mm, validate,
)


class SprocketFormulaTests(unittest.TestCase):
    def test_10t_08b_pitch_diameter(self):
        self.assertAlmostEqual(pitch_diameter_mm(12.70, 10), 41.098, places=2)

    def test_10t_08b_outside_diameter(self):
        self.assertAlmostEqual(outside_diameter_mm(12.70, 10), 46.706, places=2)

    def test_implied_pitch_round_trip(self):
        for pitch, _roller in CHAIN_TABLE.values():
            for teeth in (9, 17, 40):
                self.assertAlmostEqual(implied_pitch_mm(outside_diameter_mm(pitch, teeth), teeth), pitch, places=6)

    def test_16b_20t_axis_extent_bounds(self):
        spec = SprocketSpec(chain="16B", teeth=20, thickness_mm=12, bore_mm=30)
        d = derive(spec)
        lo, hi = axis_extent_bounds_mm(d)
        self.assertAlmostEqual(lo, 87.667, places=2)
        self.assertAlmostEqual(hi, d.outside_dia_mm / 2, places=6)

    def test_invalid_drawing_od_is_classified_as_custom_radial_part(self):
        spec = SprocketSpec(chain="08B", teeth=10, thickness_mm=10, bore_mm=12, drawing_od_mm=134)
        issues = validate(spec)
        mismatch = next(issue for issue in issues if issue.code == "OD_MISMATCH")
        self.assertIn("custom rotational_flange", mismatch.message)

    def test_unknown_chain_blocks(self):
        self.assertTrue(has_errors(validate(SprocketSpec(chain="12A", teeth=20, thickness_mm=12, bore_mm=30))))

    def test_estimated_chain_is_warning(self):
        issues = validate(SprocketSpec(
            chain="16B", teeth=20, thickness_mm=12, bore_mm=30,
            sources={"chain": __import__("ai3d_designer.drawing_to_cad.sprocket_spec", fromlist=["Source"]).Source.ESTIMATED},
        ))
        self.assertFalse(has_errors(issues))
        self.assertTrue(any(issue.severity is Severity.WARNING and issue.code=="ESTIMATED_VALUE" for issue in issues))
