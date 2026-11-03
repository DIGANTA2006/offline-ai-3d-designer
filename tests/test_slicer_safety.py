"""Slicer safety tests; a placeholder preview must never be reported as printable G-code."""

import trimesh

from ai3d_designer.slicing.slicer import SliceSettings, Slicer


def test_default_slice_settings_are_valid():
    assert SliceSettings().validation_errors() == []


def test_invalid_layer_and_infill_settings_are_rejected():
    settings = SliceSettings(layer_height=0, infill_density=101)
    errors = settings.validate()
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


def test_gcode_validator_does_not_trust_commands_inside_comments(tmp_path, monkeypatch):
    gcode_path = tmp_path / "comment_only.gcode"
    gcode_path.write_text("; G28 M104 S200 G1 X100 E5\n; generated preview", encoding="utf-8")
    monkeypatch.setattr(Slicer, "_find_cura_engine", lambda self: None)
    result = Slicer().validate_gcode(str(gcode_path))
    assert not result["valid"]
    assert "missing required commands" in result["error"]


def test_gcode_validator_accepts_minimal_structural_sanity_fixture(tmp_path, monkeypatch):
    gcode_path = tmp_path / "minimal.gcode"
    gcode_path.write_text(
        "G21\nG90\nM104 S200\nG28\nG1 X0 Y0 Z0.2 F1200\nG1 X10 Y10 E1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(Slicer, "_find_cura_engine", lambda self: None)
    result = Slicer().validate_gcode(str(gcode_path))
    assert result["valid"]
    assert result["stats"]["has_home"]
    assert result["stats"]["has_temp"]
    assert result["stats"]["has_extrusion"]
    assert result["stats"]["max_x"] == 10
    assert result["stats"]["max_y"] == 10


def test_gcode_validator_does_not_count_retractions_as_printing(tmp_path, monkeypatch):
    gcode_path = tmp_path / "retraction_only.gcode"
    gcode_path.write_text(
        "G21\nG90\nM82\nM104 S200\nG28\nG1 X0 Y0 Z0.2 F1200\nG1 E-1 F1800\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(Slicer, "_find_cura_engine", lambda self: None)
    result = Slicer().validate_gcode(str(gcode_path))
    assert not result["valid"]
    assert "extrusion move" in result["error"]


def test_gcode_validator_tracks_relative_extrusion_and_e_resets(tmp_path, monkeypatch):
    gcode_path = tmp_path / "relative_extrusion.gcode"
    gcode_path.write_text(
        "G21\nG90\nM104 S200\nG28\nM83\nG1 X0 Y0 Z0.2 F1200\nG1 X10 E1\nG92 E0\nG1 X20 E0.5\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(Slicer, "_find_cura_engine", lambda self: None)
    result = Slicer().validate_gcode(str(gcode_path))
    assert result["valid"]
    assert result["stats"]["has_extrusion"]


def test_gcode_validator_uses_absolute_e_deltas_not_positive_coordinates(tmp_path):
    gcode_path = tmp_path / "absolute_retraction_then_extrusion.gcode"
    gcode_path.write_text(
        "G21\nG90\nM82\nM104 S200\nG28\n;LAYER_COUNT:1\n"
        "G1 X0 Y0 Z0.2 F1200\nG92 E10\n"
        "G1 E9 F1800\n"
        "G1 X10 Y0 E9.5 F1200\n",
        encoding="utf-8",
    )
    result = Slicer(cura_engine_path="unused-test-path").validate_gcode(str(gcode_path))
    assert result["valid"] is True
    assert result["stats"]["extrusion_length_mm"] == 0.5
    assert result["stats"]["deposition_extrusion_mm"] == 0.5
    assert result["stats"]["deposition_moves"] == 1


def test_gcode_validator_rejects_positive_absolute_e_coordinate_that_only_retracts(tmp_path):
    gcode_path = tmp_path / "absolute_retraction_only.gcode"
    gcode_path.write_text(
        "G21\nG90\nM82\nM104 S200\nG28\n;LAYER_COUNT:1\n"
        "G1 X0 Y0 Z0.2 F1200\nG92 E10\nG1 X10 Y0 E9 F1200\n",
        encoding="utf-8",
    )
    result = Slicer(cura_engine_path="unused-test-path").validate_gcode(str(gcode_path))
    assert result["valid"] is False
    assert "positive extrusion" in result["error"].lower()


def test_gcode_validator_measures_relative_extrusion_after_e_reset(tmp_path):
    gcode_path = tmp_path / "relative_extrusion.gcode"
    gcode_path.write_text(
        "G21\nG90\nM83\nM104 S200\nG28\n;LAYER_COUNT:1\n"
        "G1 X0 Y0 Z0.2 F1200\nG1 X10 Y0 E1 F1200\n"
        "G92 E0\nG1 X20 Y0 E0.5 F1200\n",
        encoding="utf-8",
    )
    result = Slicer(cura_engine_path="unused-test-path").validate_gcode(str(gcode_path))
    assert result["valid"] is True
    assert result["stats"]["extrusion_length_mm"] == 1.5
    assert result["stats"]["deposition_moves"] == 2


def test_gcode_validator_converts_volumetric_extrusion_to_filament_length(tmp_path):
    import math

    diameter_mm = 1.75
    area_mm2 = math.pi * (diameter_mm / 2) ** 2
    gcode_path = tmp_path / "volumetric_extrusion.gcode"
    gcode_path.write_text(
        "G21\nG90\nM83\nM200 D1.75\nM104 S200\nG28\n;LAYER_COUNT:1\n"
        "G1 X0 Y0 Z0.2 F1200\nG1 X10 Y0 E" + str(area_mm2) + " F1200\n",
        encoding="utf-8",
    )
    result = Slicer(cura_engine_path="unused-test-path").validate_gcode(str(gcode_path))
    assert result["valid"] is True
    assert abs(result["stats"]["extrusion_length_mm"] - 1.0) < 1e-6
