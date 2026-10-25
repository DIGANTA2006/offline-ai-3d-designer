"""CLI helper regression tests."""

import math

import pytest

from ai3d_designer.cli.main import create_box_spec
from ai3d_designer.core.geometry.engine import create_part_from_spec


def test_cli_box_with_hole_places_cutter_at_center():
    spec = create_box_spec("test_box", width=40, depth=20, height=10, hole_diameter=5)
    part = create_part_from_spec(spec)

    expected_volume = 40 * 20 * 10 - math.pi * (5 / 2) ** 2 * 10
    assert part.volume == pytest.approx(expected_volume, rel=1e-3)
    assert spec.features[1].position == [0.0, 0.0, 0.0]


@pytest.mark.parametrize("diameter", [0, -1, 20, 30])
def test_cli_box_helper_rejects_invalid_hole_diameter(diameter):
    with pytest.raises(ValueError, match="through-hole"):
        create_box_spec("test_box", width=40, depth=20, height=10, hole_diameter=diameter)
