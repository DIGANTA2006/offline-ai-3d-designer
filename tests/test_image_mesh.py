"""Tests for printable heightfield mesh topology."""

import numpy as np
import pytest

from ai3d_designer.image_to_3d.mesh import build_closed_heightfield


def test_heightfield_is_watertight_positive_volume_and_has_bottom():
    x, y = np.meshgrid(np.linspace(0, 10, 4), np.linspace(0, 5, 3))
    top = np.full_like(x, 2.0)
    mesh = build_closed_heightfield(x, y, top, bottom_z=0)

    assert mesh.is_watertight
    assert mesh.is_volume
    assert mesh.volume == pytest.approx(100.0, abs=1e-6)
    assert mesh.bounds[0, 2] == pytest.approx(0.0)
    assert mesh.bounds[1, 2] == pytest.approx(2.0)


def test_heightfield_rejects_non_finite_or_non_solid_data():
    x, y = np.meshgrid(np.linspace(0, 1, 2), np.linspace(0, 1, 2))
    bad = np.array([[1.0, float("nan")], [1.0, 1.0]])
    with pytest.raises(ValueError, match="finite"):
        build_closed_heightfield(x, y, bad)
    with pytest.raises(ValueError, match="above bottom_z"):
        build_closed_heightfield(x, y, np.zeros_like(x), bottom_z=0)


def test_heightfield_color_grid_shape_is_checked():
    x, y = np.meshgrid(np.linspace(0, 1, 2), np.linspace(0, 1, 2))
    z = np.ones_like(x)
    with pytest.raises(ValueError, match="vertex_colors"):
        build_closed_heightfield(x, y, z, vertex_colors=np.zeros((3, 3, 3), dtype=np.uint8))
