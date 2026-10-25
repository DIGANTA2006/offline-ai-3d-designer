"""Regression tests for manufacturing export validation."""

import numpy as np
import trimesh

from ai3d_designer.core.export.exporter import _validate_stl


def test_valid_closed_box_stl_passes_manifold_validation(tmp_path):
    path = tmp_path / "box.stl"
    trimesh.creation.box(extents=(10, 10, 10)).export(path)

    errors, warnings = _validate_stl(str(path))

    assert errors == []
    assert warnings == []


def test_open_stl_is_rejected_instead_of_only_warned(tmp_path):
    path = tmp_path / "open-box.stl"
    mesh = trimesh.creation.box(extents=(10, 10, 10))
    mesh.update_faces(np.arange(len(mesh.faces) - 1))
    mesh.export(path)

    errors, _ = _validate_stl(str(path))

    assert any("not watertight" in error.lower() for error in errors)
