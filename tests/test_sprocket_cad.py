import tempfile
import unittest
from pathlib import Path

try:
    from ai3d_designer.drawing_to_cad.sprocket_cad import ExportBlocked, export_sprocket, verify, build_sprocket
    from ai3d_designer.drawing_to_cad.sprocket_spec import SprocketSpec, has_errors
    HAVE_CAD = True
except ImportError:
    HAVE_CAD = False


@unittest.skipUnless(HAVE_CAD, "build123d is not installed")
class SprocketCadTests(unittest.TestCase):
    def spec(self):
        return SprocketSpec(chain="16B", teeth=20, thickness_mm=12, bore_mm=30, bolt_count=6, bolt_hole_dia_mm=12, bolt_pcd_mm=88)

    def test_build_passes_verify(self):
        spec = self.spec()
        self.assertFalse(has_errors(verify(build_sprocket(spec), spec)))

    def test_export_writes_step_stl(self):
        with tempfile.TemporaryDirectory() as directory:
            export_sprocket(self.spec(), directory, "test_part")
            self.assertGreater((Path(directory) / "test_part.step").stat().st_size, 100)
            self.assertGreater((Path(directory) / "test_part.stl").stat().st_size, 100)

    def test_invalid_spec_is_refused_before_export(self):
        bad = SprocketSpec(chain="12A", teeth=20, thickness_mm=12, bore_mm=30)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ExportBlocked):
                export_sprocket(bad, directory, "bad")
            self.assertFalse((Path(directory) / "bad.stl").exists())
