"""Slicer safety tests; a placeholder preview must never be reported as printable G-code."""

import trimesh

from ai3d_designer.slicing.slicer import SliceSettings, Slicer


def test_default_slice_settings_are_valid():
    assert SliceSettings().validation_errors() == []


def test_invalid_layer_and_infill_settings_are_rejected():
    settings = SliceSettings(layer_height=0, infill_density=101)
    errors = settings.validation_errors()
    assert any("layer_height" in error for error in errors)
    assert any("infill_density" in error for error in errors)


def test_missing_cura_engine_does_not_write_fake_gcode(tmp_path, monkeypatch):
    stl_path = tmp_path / "cube.stl"
    output_path = tmp_path / "cube.gcode"
    mesh = trimesh.creation.box(extents=(20, 20, 20))
    mesh.export(stl_path)

    monkeypatch.setattr(Slicer, "_find_cura_engine", lambda self: None)
    slicer = Slicer()

    result = slicer.slice(str(stl_path), str(output_path))

    assert not result.success
    assert any("CuraEngine was not found" in error for error in result.errors)
    assert not output_path.exists()


def test_slicer_rejects_output_path_equal_to_input(tmp_path, monkeypatch):
    stl_path = tmp_path / "cube.stl"
    mesh = trimesh.creation.box(extents=(20, 20, 20))
    mesh.export(stl_path)
    monkeypatch.setattr(Slicer, "_find_cura_engine", lambda self: None)
    slicer = Slicer()

    result = slicer.slice(str(stl_path), str(stl_path))

    assert not result.success
    assert any("different from the source STL" in error for error in result.errors)
