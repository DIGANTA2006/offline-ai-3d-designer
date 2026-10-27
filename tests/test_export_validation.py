"""Regression tests for manufacturing export validation."""

import numpy as np
import trimesh
import tempfile
import os

from ai3d_designer.core.export.exporter import (
    _validate_stl,
    _validate_step,
    _validate_3mf,
    export_step,
    export_stl,
    export_3mf,
    export_zip_bundle,
    generate_dimension_report,
    generate_print_guide,
    check_export_blockers,
    validate_export,
)
from ai3d_designer.core.geometry.engine import create_part_from_spec
from ai3d_designer.core.spec.models import PartSpec, FeatureSpec, ParameterSpec, PrimitiveType, OperationType, UnitSystem


def create_test_box_spec() -> PartSpec:
    """Create a simple box PartSpec for testing."""
    spec = PartSpec(
        name="TestBox",
        description="Test box 10x10x10mm",
        unit_system=UnitSystem.MM,
    )
    box_feature = FeatureSpec(
        id="box1",
        type=PrimitiveType.BOX,
        name="Test Box",
        parameters={
            "width": ParameterSpec(name="width", value=10.0, unit=UnitSystem.MM),
            "depth": ParameterSpec(name="depth", value=10.0, unit=UnitSystem.MM),
            "height": ParameterSpec(name="height", value=10.0, unit=UnitSystem.MM),
        },
        operation=OperationType.UNION,
    )
    spec.add_feature(box_feature)
    return spec


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


def test_non_manifold_stl_rejected(tmp_path):
    """Test that non-manifold STL is rejected."""
    path = tmp_path / "nonmanifold.stl"
    # Create two boxes sharing an edge (non-manifold)
    mesh1 = trimesh.creation.box(extents=(10, 10, 10))
    mesh2 = trimesh.creation.box(extents=(10, 10, 10))
    mesh2.apply_translation([10, 0, 0])  # Touching at edge
    combined = trimesh.util.concatenate([mesh1, mesh2])
    combined.export(path)

    errors, _ = _validate_stl(str(path))
    # Should be rejected by manifold3d
    assert len(errors) > 0


def test_zero_volume_stl_rejected(tmp_path):
    """Test that zero-volume STL is rejected."""
    path = tmp_path / "flat.stl"
    # Create a flat 2D mesh (no volume)
    mesh = trimesh.Trimesh(
        vertices=[[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]],
        faces=[[0, 1, 2], [0, 2, 3]],
    )
    mesh.export(path)

    errors, _ = _validate_stl(str(path))
    assert any("volume" in error.lower() for error in errors)


def test_step_export_and_validation(tmp_path):
    """Test STEP export and validation."""
    spec = create_test_box_spec()
    part = create_part_from_spec(spec)
    
    step_path = tmp_path / "test.step"
    result = export_step(part, str(step_path), validate=True)
    
    assert result.success is True
    assert result.file_size > 0
    assert result.format == "STEP"
    assert os.path.exists(step_path)


def test_stl_export_and_validation(tmp_path):
    """Test STL export and validation."""
    spec = create_test_box_spec()
    part = create_part_from_spec(spec)
    
    stl_path = tmp_path / "test.stl"
    result = export_stl(part, str(stl_path), validate=True)
    
    assert result.success is True
    assert result.file_size > 0
    assert result.format == "STL"
    assert os.path.exists(stl_path)


def test_3mf_export_and_validation(tmp_path):
    """Test 3MF export and validation."""
    spec = create_test_box_spec()
    part = create_part_from_spec(spec)
    
    mf_path = tmp_path / "test.3mf"
    result = export_3mf(part, str(mf_path), validate=True)
    
    assert result.success is True
    assert result.file_size > 0
    assert result.format == "3MF"
    assert os.path.exists(mf_path)


def test_zip_bundle_export(tmp_path):
    """Test ZIP bundle export with all components."""
    spec = create_test_box_spec()
    part = create_part_from_spec(spec)
    
    zip_path = tmp_path / "bundle.zip"
    result = export_zip_bundle(
        part, 
        str(zip_path), 
        part_spec=spec.model_dump(mode="json"),
        settings={"layer_height": 0.2, "infill_density": 20},
        include_step=True,
        include_stl=True,
        include_3mf=True,
        validate=True,
    )
    
    assert result.success is True
    assert result.file_size > 0
    assert result.format == "ZIP"
    assert os.path.exists(zip_path)
    
    # Verify ZIP contents
    import zipfile
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        assert "test.step" in names or "TestBox.step" in names
        assert "test.stl" in names or "TestBox.stl" in names
        assert "test.3mf" in names or "TestBox.3mf" in names
        assert "dimension_report.json" in names
        assert "print_guide.md" in names


def test_generate_dimension_report():
    """Test dimension report generation."""
    spec = create_test_box_spec()
    part = create_part_from_spec(spec)
    
    report = generate_dimension_report(part, spec.model_dump(mode="json"))
    
    assert "generated_at" in report
    assert "bounding_box" in report
    assert "volume_mm3" in report
    assert "volume_cm3" in report
    assert "center_of_mass" in report
    assert "spec" in report
    assert report["volume_mm3"] == 1000.0  # 10x10x10 = 1000
    assert report["volume_cm3"] == 1.0


def test_generate_print_guide():
    """Test print guide generation."""
    spec = create_test_box_spec()
    part = create_part_from_spec(spec)
    
    guide = generate_print_guide(part, {"layer_height": 0.2, "infill_density": 20})
    
    assert "Print Guide" in guide
    assert "1000.00 mm" in guide  # volume
    assert "10.0 × 10.0 × 10.0 mm" in guide  # dimensions
    assert "Layer Height" in guide
    assert "0.2 mm" in guide
    assert "Infill Density" in guide
    assert "20%" in guide


def test_validate_export_all_formats(tmp_path):
    """Test validate_export function."""
    spec = create_test_box_spec()
    part = create_part_from_spec(spec)
    
    results = validate_export(part, formats=["step", "stl", "3mf"])
    
    assert "step" in results
    assert "stl" in results
    assert "3mf" in results
    assert results["step"]["success"] is True
    assert results["stl"]["success"] is True
    assert results["3mf"]["success"] is True


def test_check_export_blockers_unconfirmed_defaults():
    """Test L-05: Export blocked on unconfirmed defaults."""
    part_spec = {
        "name": "Test",
        "features": [
            {
                "id": "feat1",
                "name": "Box",
                "type": "box",
                "parameters": {
                    "width": {"name": "width", "value": 10, "unit": "mm", "source": "default", "confirmed": False},
                    "depth": {"name": "depth", "value": 10, "unit": "mm", "source": "user", "confirmed": True},
                    "height": {"name": "height", "value": 10, "unit": "mm", "source": "default", "confirmed": False},
                },
            }
        ]
    }
    
    blockers = check_export_blockers(part_spec)
    assert len(blockers) == 2
    assert any("width" in b and "unconfirmed default" in b for b in blockers)
    assert any("height" in b and "unconfirmed default" in b for b in blockers)


def test_check_export_blockers_confirmed_defaults_allowed():
    """Test that confirmed defaults don't block export."""
    part_spec = {
        "name": "Test",
        "features": [
            {
                "id": "feat1",
                "name": "Box",
                "type": "box",
                "parameters": {
                    "width": {"name": "width", "value": 10, "unit": "mm", "source": "default", "confirmed": True},
                    "depth": {"name": "depth", "value": 10, "unit": "mm", "source": "default", "confirmed": True},
                    "height": {"name": "height", "value": 10, "unit": "mm", "source": "default", "confirmed": True},
                },
            }
        ]
    }
    
    blockers = check_export_blockers(part_spec)
    assert len(blockers) == 0


def test_check_export_blockers_sprocket_preview():
    """Test L-06: Export blocked on sprocket previews."""
    part_spec = {
        "name": "TestSprocket",
        "features": [
            {
                "id": "sprocket1",
                "name": "Sprocket",
                "type": "sprocket",
                "parameters": {},
            }
        ]
    }
    
    blockers = check_export_blockers(part_spec)
    assert len(blockers) == 1
    assert "sprocket" in blockers[0].lower()
    assert "preview" in blockers[0].lower()
    assert "ISO 606" in blockers[0]


def test_check_export_blockers_sprocket_in_name():
    """Test L-06: Export blocked when sprocket in feature name."""
    part_spec = {
        "name": "Test",
        "features": [
            {
                "id": "feat1",
                "name": "My Sprocket Gear",
                "type": "cylinder",
                "parameters": {
                    "radius": {"name": "radius", "value": 10, "unit": "mm"},
                    "height": {"name": "height", "value": 5, "unit": "mm"},
                },
            }
        ]
    }
    
    blockers = check_export_blockers(part_spec)
    assert len(blockers) == 1
    assert "sprocket" in blockers[0].lower()


def test_check_export_blockers_sprocket_in_id():
    """Test L-06: Export blocked when sprocket in feature ID."""
    part_spec = {
        "name": "Test",
        "features": [
            {
                "id": "sprocket_main",
                "name": "Gear",
                "type": "cylinder",
                "parameters": {
                    "radius": {"name": "radius", "value": 10, "unit": "mm"},
                    "height": {"name": "height", "value": 5, "unit": "mm"},
                },
            }
        ]
    }
    
    blockers = check_export_blockers(part_spec)
    assert len(blockers) == 1
    assert "sprocket" in blockers[0].lower()


def test_export_zip_includes_dimension_report_and_print_guide(tmp_path):
    """Test that ZIP bundle includes dimension_report.json and print_guide.md."""
    spec = create_test_box_spec()
    part = create_part_from_spec(spec)
    
    zip_path = tmp_path / "bundle.zip"
    result = export_zip_bundle(
        part, 
        str(zip_path), 
        part_spec=spec.model_dump(mode="json"),
        settings={"layer_height": 0.2},
        validate=True,
    )
    
    assert result.success is True
    
    import zipfile
    with zipfile.ZipFile(zip_path, "r") as zf:
        # Check dimension_report.json exists and is valid JSON
        assert "dimension_report.json" in zf.namelist()
        with zf.open("dimension_report.json") as f:
            import json
            report = json.load(f)
            assert "bounding_box" in report
            assert "volume_mm3" in report
        
        # Check print_guide.md exists and has content
        assert "print_guide.md" in zf.namelist()
        with zf.open("print_guide.md") as f:
            guide = f.read().decode("utf-8")
            assert "Print Guide" in guide
            assert "1000.00 mm" in guide


def test_export_zip_without_3mf(tmp_path):
    """Test ZIP bundle export without 3MF."""
    spec = create_test_box_spec()
    part = create_part_from_spec(spec)
    
    zip_path = tmp_path / "bundle_no_3mf.zip"
    result = export_zip_bundle(
        part, 
        str(zip_path), 
        part_spec=spec.model_dump(mode="json"),
        include_step=True,
        include_stl=True,
        include_3mf=False,
        validate=True,
    )
    
    assert result.success is True
    
    import zipfile
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        assert any(n.endswith(".step") for n in names)
        assert any(n.endswith(".stl") for n in names)
        assert not any(n.endswith(".3mf") for n in names)
        assert "dimension_report.json" in names
        assert "print_guide.md" in names


def test_export_zip_without_step(tmp_path):
    """Test ZIP bundle export without STEP."""
    spec = create_test_box_spec()
    part = create_part_from_spec(spec)
    
    zip_path = tmp_path / "bundle_no_step.zip"
    result = export_zip_bundle(
        part, 
        str(zip_path), 
        part_spec=spec.model_dump(mode="json"),
        include_step=False,
        include_stl=True,
        include_3mf=True,
        validate=True,
    )
    
    assert result.success is True
    
    import zipfile
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        assert not any(n.endswith(".step") for n in names)
        assert any(n.endswith(".stl") for n in names)
        assert any(n.endswith(".3mf") for n in names)


def test_export_blockers_empty_spec():
    """Test check_export_blockers with None/empty spec."""
    assert check_export_blockers(None) == []
    assert check_export_blockers({}) == []
    assert check_export_blockers({"features": []}) == []
