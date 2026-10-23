"""Tests for dependency-safe image reliefs and watertight export."""

import numpy as np
import pytest
import trimesh
from PIL import Image

from ai3d_designer.image_to_3d.converter import (
    ImageTo3DConverter,
    MIDAS_AVAILABLE,
    _build_watertight_heightfield,
    create_lithophane,
)


def test_heightfield_builder_returns_a_closed_positive_volume_solid():
    heights = np.array([[1.0, 2.0, 1.0], [2.0, 3.0, 2.0], [1.0, 2.0, 1.0]])
    mesh = _build_watertight_heightfield(heights, scale_x=20, scale_y=10)
    assert mesh.is_watertight
    assert mesh.is_volume
    assert mesh.volume > 0
    assert mesh.extents[0] == pytest.approx(20)
    assert mesh.extents[1] == pytest.approx(10)
    assert mesh.bounds[0][2] == pytest.approx(0)


def test_heightfield_builder_rejects_nonfinite_and_degenerate_inputs():
    with pytest.raises(ValueError, match="finite"):
        _build_watertight_heightfield(np.array([[1.0, float("nan")], [1.0, 2.0]]), 10, 10)
    with pytest.raises(ValueError, match="2 × 2"):
        _build_watertight_heightfield(np.array([[1.0]]), 10, 10)


def test_depth_to_mesh_builds_watertight_aspect_preserving_relief():
    converter = ImageTo3DConverter.__new__(ImageTo3DConverter)
    depth = np.array([[0.0, 1.0, 0.5], [0.2, 0.8, 0.3]], dtype=np.float64)
    mesh = converter.depth_to_mesh(depth, scale=30, height_scale=4, base_thickness=1)
    assert mesh.is_watertight
    assert mesh.is_volume
    assert mesh.volume > 0
    assert mesh.extents[0] == pytest.approx(30)
    assert mesh.extents[1] == pytest.approx(20)
    assert mesh.bounds[0][2] == pytest.approx(0)
    assert mesh.bounds[1][2] == pytest.approx(5)


def test_lithophane_exports_valid_stl(tmp_path):
    image_path = tmp_path / "photo.png"
    output_path = tmp_path / "photo_lithophane.stl"
    pixels = np.array(
        [[0, 64, 128, 192, 255], [255, 192, 128, 64, 0], [32, 96, 160, 224, 255]],
        dtype=np.uint8,
    )
    Image.fromarray(pixels, mode="L").save(image_path)

    mesh = create_lithophane(
        str(image_path), str(output_path), max_size=40, thickness=3, thinnest=0.8, border=2
    )
    reloaded = trimesh.load(output_path, force="mesh")
    assert mesh.is_watertight and mesh.is_volume and mesh.volume > 0
    assert reloaded.is_watertight and reloaded.is_volume and reloaded.volume > 0
    assert output_path.exists() and output_path.stat().st_size > 0


def test_midas_dependency_is_reported_cleanly_when_unavailable():
    if MIDAS_AVAILABLE:
        pytest.skip("This runner has optional PyTorch installed.")
    with pytest.raises(RuntimeError, match="MiDaS depth estimation is unavailable"):
        ImageTo3DConverter()
