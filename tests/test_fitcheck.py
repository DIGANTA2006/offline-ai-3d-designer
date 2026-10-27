"""
Tests for the fit check module (WS5 - T40, T43) and hardware presets (Step E).
"""

import pytest
from ai3d_designer.fitcheck.engine import FitCheckEngine, check_fit
from ai3d_designer.fitcheck.models import ComponentSpec, EnclosureSpec, ComponentType, FitCheckResult, FitCheckReport
from ai3d_designer.fitcheck.presets import (
    STANDARD_COMPONENT_PRESETS,
    get_preset_component,
    list_hardware_presets,
    generate_enclosure_for_component,
    run_fit_check,
)
from ai3d_designer.core.spec.models import ParameterSource, PartSpec, FeatureSpec, PrimitiveType, OperationType, UnitSystem


def test_component_spec_creation():
    """Test creating a component specification."""
    component = ComponentSpec(
        name="Test PCB",
        type=ComponentType.PCB,
        width=50.0,
        depth=30.0,
        height=10.0,
        source=ParameterSource.USER,
        confirmed=True,
    )
    assert component.name == "Test PCB"
    assert component.width == 50.0
    assert component.confirmed is True


def test_component_spec_validation():
    """Test component spec validation."""
    # Valid component
    component = ComponentSpec(name="Test", width=10, depth=10, height=5)
    assert component.width == 10

    # Invalid dimensions
    with pytest.raises(ValueError, match="width must be finite and positive"):
        ComponentSpec(name="Test", width=-1, depth=10, height=5)

    with pytest.raises(ValueError, match="depth must be finite and positive"):
        ComponentSpec(name="Test", width=10, depth=0, height=5)

    with pytest.raises(ValueError, match="height must be finite and positive"):
        ComponentSpec(name="Test", width=10, depth=10, height=float("nan"))


def test_enclosure_spec_creation():
    """Test creating an enclosure specification."""
    enclosure = EnclosureSpec(
        name="Test Enclosure",
        interior_width=100.0,
        interior_depth=80.0,
        interior_height=40.0,
        wall_thickness=2.0,
    )
    assert enclosure.name == "Test Enclosure"
    assert enclosure.interior_width == 100.0
    assert enclosure.wall_thickness == 2.0


def test_enclosure_spec_validation():
    """Test enclosure spec validation."""
    # Valid enclosure
    enclosure = EnclosureSpec(name="Test", interior_width=100, interior_depth=80, interior_height=40)
    assert enclosure.interior_width == 100

    # Invalid dimensions
    with pytest.raises(ValueError, match="interior width must be finite and positive"):
        EnclosureSpec(name="Test", interior_width=-1, interior_depth=80, interior_height=40)

    with pytest.raises(ValueError, match="wall thickness must be finite and non-negative"):
        EnclosureSpec(name="Test", interior_width=100, interior_depth=80, interior_height=40, wall_thickness=-1)


def test_fit_check_component_fits():
    """Test fit check when component fits with clearance."""
    component = ComponentSpec(
        name="PCB",
        width=50.0,
        depth=30.0,
        height=10.0,
    )
    enclosure = EnclosureSpec(
        name="Enclosure",
        interior_width=100.0,
        interior_depth=80.0,
        interior_height=40.0,
    )

    engine = FitCheckEngine(default_clearance_mm=1.0)
    result = engine.check_component_fit(component, enclosure)

    assert result.fits is True
    assert result.clearance_mm["x"] == 48.0  # 100 - 2*1 - 50
    assert result.clearance_mm["y"] == 48.0  # 80 - 2*1 - 30
    assert result.clearance_mm["z"] == 28.0  # 40 - 2*1 - 10
    assert result.shortfall_mm["x"] == 0.0
    assert result.shortfall_mm["y"] == 0.0
    assert result.shortfall_mm["z"] == 0.0


def test_fit_check_component_exact_fit():
    """Test fit check when component fits exactly (no clearance)."""
    component = ComponentSpec(
        name="Tight PCB",
        width=98.0,  # 100 - 2*1
        depth=78.0,  # 80 - 2*1
        height=38.0,  # 40 - 2*1
    )
    enclosure = EnclosureSpec(
        name="Enclosure",
        interior_width=100.0,
        interior_depth=80.0,
        interior_height=40.0,
    )

    engine = FitCheckEngine(default_clearance_mm=1.0)
    result = engine.check_component_fit(component, enclosure)

    assert result.fits is True
    assert result.clearance_mm["x"] == 0.0
    assert result.clearance_mm["y"] == 0.0
    assert result.clearance_mm["z"] == 0.0


def test_fit_check_component_too_wide():
    """Test fit check when component is too wide."""
    component = ComponentSpec(
        name="Wide PCB",
        width=105.0,  # Exceeds 100 - 2*1 = 98
        depth=30.0,
        height=10.0,
    )
    enclosure = EnclosureSpec(
        name="Enclosure",
        interior_width=100.0,
        interior_depth=80.0,
        interior_height=40.0,
    )

    engine = FitCheckEngine(default_clearance_mm=1.0)
    result = engine.check_component_fit(component, enclosure)

    assert result.fits is False
    assert result.shortfall_mm["x"] == 7.0  # 105 - 98
    assert result.shortfall_mm["y"] == 0.0
    assert result.shortfall_mm["z"] == 0.0
    assert len(result.issues) > 0
    assert "exceeds available width" in result.issues[0]


def test_fit_check_component_too_deep():
    """Test fit check when component is too deep."""
    component = ComponentSpec(
        name="Deep PCB",
        width=50.0,
        depth=85.0,  # Exceeds 80 - 2*1 = 78
        height=10.0,
    )
    enclosure = EnclosureSpec(
        name="Enclosure",
        interior_width=100.0,
        interior_depth=80.0,
        interior_height=40.0,
    )

    engine = FitCheckEngine(default_clearance_mm=1.0)
    result = engine.check_component_fit(component, enclosure)

    assert result.fits is False
    assert result.shortfall_mm["y"] == 7.0  # 85 - 78


def test_fit_check_component_too_tall():
    """Test fit check when component is too tall."""
    component = ComponentSpec(
        name="Tall PCB",
        width=50.0,
        depth=30.0,
        height=45.0,  # Exceeds 40 - 2*1 = 38
    )
    enclosure = EnclosureSpec(
        name="Enclosure",
        interior_width=100.0,
        interior_depth=80.0,
        interior_height=40.0,
    )

    engine = FitCheckEngine(default_clearance_mm=1.0)
    result = engine.check_component_fit(component, enclosure)

    assert result.fits is False
    assert result.shortfall_mm["z"] == 7.0  # 45 - 38


def test_fit_check_multiple_components():
    """Test fit check with multiple components."""
    components = [
        ComponentSpec(name="PCB", width=50.0, depth=30.0, height=10.0),
        ComponentSpec(name="Battery", width=40.0, depth=20.0, height=15.0),
    ]
    enclosure = EnclosureSpec(
        name="Enclosure",
        interior_width=100.0,
        interior_depth=80.0,
        interior_height=40.0,
    )

    engine = FitCheckEngine(default_clearance_mm=1.0)
    report = engine.check_all_components(components, enclosure)

    assert report.overall_fit is True
    assert len(report.results) == 2
    assert all(r.fits for r in report.results)
    assert "All 2 component(s) fit" in report.summary


def test_fit_check_multiple_components_one_fails():
    """Test fit check with multiple components where one fails."""
    components = [
        ComponentSpec(name="PCB", width=50.0, depth=30.0, height=10.0),
        ComponentSpec(name="Large Battery", width=105.0, depth=20.0, height=15.0),  # Too wide
    ]
    enclosure = EnclosureSpec(
        name="Enclosure",
        interior_width=100.0,
        interior_depth=80.0,
        interior_height=40.0,
    )

    engine = FitCheckEngine(default_clearance_mm=1.0)
    report = engine.check_all_components(components, enclosure)

    assert report.overall_fit is False
    assert len(report.results) == 2
    assert report.results[0].fits is True
    assert report.results[1].fits is False
    assert "1 of 2 component(s) do not fit" in report.summary


def test_fit_check_custom_clearance():
    """Test fit check with custom clearance."""
    component = ComponentSpec(
        name="PCB",
        width=50.0,
        depth=30.0,
        height=10.0,
    )
    enclosure = EnclosureSpec(
        name="Enclosure",
        interior_width=100.0,
        interior_depth=80.0,
        interior_height=40.0,
    )

    # With 5mm clearance
    engine = FitCheckEngine(default_clearance_mm=5.0)
    result = engine.check_component_fit(component, enclosure)

    assert result.fits is True
    assert result.clearance_mm["x"] == 40.0  # 100 - 2*5 - 50
    assert result.suggested_clearance_mm == 5.0


def test_fit_check_tight_fit_warning():
    """Test that tight fits generate warnings."""
    component = ComponentSpec(
        name="Tight PCB",
        width=96.0,  # 100 - 2*1 = 98, so clearance = 2mm (less than 2*1=2mm... actually equal)
        depth=30.0,
        height=10.0,
    )
    enclosure = EnclosureSpec(
        name="Enclosure",
        interior_width=100.0,
        interior_depth=80.0,
        interior_height=40.0,
    )

    engine = FitCheckEngine(default_clearance_mm=1.0)
    result = engine.check_component_fit(component, enclosure)

    assert result.fits is True
    # Clearance is 2mm, which equals 2*default_clearance, so no warning
    # Let's test with even tighter
    component2 = ComponentSpec(
        name="Very Tight PCB",
        width=97.0,  # clearance = 1mm < 2mm
        depth=30.0,
        height=10.0,
    )
    result2 = engine.check_component_fit(component2, enclosure)
    assert result2.fits is True
    assert len(result2.warnings) > 0
    assert "Tight fit" in result2.warnings[0]


def test_convenience_function():
    """Test the convenience check_fit function."""
    components = [
        ComponentSpec(name="PCB", width=50.0, depth=30.0, height=10.0),
    ]
    enclosure = EnclosureSpec(
        name="Enclosure",
        interior_width=100.0,
        interior_depth=80.0,
        interior_height=40.0,
    )

    report = check_fit(components, enclosure, clearance_mm=1.0)

    assert isinstance(report, FitCheckReport)
    assert report.overall_fit is True
    assert len(report.results) == 1


def test_fit_check_report_bool():
    """Test FitCheckReport boolean evaluation."""
    components = [
        ComponentSpec(name="PCB", width=50.0, depth=30.0, height=10.0),
    ]
    enclosure = EnclosureSpec(
        name="Enclosure",
        interior_width=100.0,
        interior_depth=80.0,
        interior_height=40.0,
    )

    report = check_fit(components, enclosure)
    assert bool(report) is True

    # Failing case
    components_fail = [
        ComponentSpec(name="Big PCB", width=200.0, depth=30.0, height=10.0),
    ]
    report_fail = check_fit(components_fail, enclosure)
    assert bool(report_fail) is False


def test_component_with_mounting_holes():
    """Test component with mounting holes."""
    component = ComponentSpec(
        name="PCB with Mounts",
        width=50.0,
        depth=30.0,
        height=10.0,
        mounting_holes=[[10, 10, 0], [40, 10, 0], [10, 20, 0], [40, 20, 0]],
    )
    enclosure = EnclosureSpec(
        name="Enclosure",
        interior_width=100.0,
        interior_depth=80.0,
        interior_height=40.0,
        # Bosses are in enclosure coordinates; the component is centred in the interior.
        mounting_bosses=[[37, 37, 0], [67, 37, 0], [37, 47, 0], [67, 47, 0]],
    )

    engine = FitCheckEngine()
    result = engine.check_component_fit(component, enclosure)

    assert result.fits is True
    assert result.issues == []


def test_fit_check_rejects_misaligned_mounting_bosses():
    component = ComponentSpec(
        name="PCB with Mounts",
        width=50.0,
        depth=30.0,
        height=10.0,
        mounting_holes=[[10, 10], [40, 10], [10, 20], [40, 20]],
    )
    enclosure = EnclosureSpec(
        name="Enclosure",
        interior_width=100.0,
        interior_depth=80.0,
        interior_height=40.0,
        wall_thickness=2.0,
        mounting_bosses=[[38, 37], [67, 37], [37, 47], [67, 47]],
    )

    result = FitCheckEngine().check_component_fit(component, enclosure)

    assert result.fits is False
    assert any("does not align" in issue for issue in result.issues)


def test_fit_check_rejects_invalid_clearances():
    with pytest.raises(ValueError, match="default_clearance_mm must be finite and non-negative"):
        FitCheckEngine(default_clearance_mm=-1.0)

    component = ComponentSpec(name="PCB", width=10, depth=10, height=5)
    enclosure = EnclosureSpec(name="Enclosure", interior_width=20, interior_depth=20, interior_height=20)
    with pytest.raises(ValueError, match="clearance_mm must be finite and non-negative"):
        FitCheckEngine().check_component_fit(component, enclosure, clearance_mm=float("nan"))


def test_fit_check_zero_clearance_is_reported_correctly():
    component = ComponentSpec(name="PCB", width=10, depth=10, height=5)
    enclosure = EnclosureSpec(name="Enclosure", interior_width=20, interior_depth=20, interior_height=20)

    report = FitCheckEngine().check_all_components([component], enclosure, clearance_mm=0.0)

    assert report.overall_fit is True
    assert "with 0.0 mm clearance" in report.summary


def test_fit_check_empty_component_list_is_not_reported_as_success():
    enclosure = EnclosureSpec(name="Empty", interior_width=20, interior_depth=20, interior_height=20)

    report = FitCheckEngine().check_all_components([], enclosure)

    assert report.overall_fit is False
    assert "No components were supplied" in report.summary


def test_run_fit_check_uses_available_engine_api_for_presets():
    component = get_preset_component("esp32_devkit")
    enclosure, _part_spec = generate_enclosure_for_component(component)

    report = run_fit_check(component, enclosure)

    assert report.overall_fit is True
    assert len(report.results) == 1
    assert report.results[0].component_id == component.id


def test_component_confirmed_flag():
    """Test component confirmed flag."""
    component = ComponentSpec(
        name="PCB",
        width=50.0,
        depth=30.0,
        height=10.0,
        confirmed=False,
    )
    assert component.confirmed is False

    component.confirmed = True
    assert component.confirmed is True


def test_enclosure_with_cutouts():
    """Test enclosure with cutouts."""
    enclosure = EnclosureSpec(
        name="Enclosure with USB cutout",
        interior_width=100.0,
        interior_depth=80.0,
        interior_height=40.0,
        cutouts=[{"type": "rectangle", "width": 12, "height": 5, "position": [50, 0, 5]}],
    )
    assert len(enclosure.cutouts) == 1
    assert enclosure.cutouts[0]["type"] == "rectangle"


# =============================================================================
# STEP E: Hardware Presets & Auto-Enclosure Tests
# =============================================================================

def test_standard_component_presets_exist():
    """Test that all 6 standard component presets are defined."""
    expected_presets = [
        "aries_v2_riscv",
        "aries_alpha_riscv",
        "iot_sensor_node",
        "esp32_devkit",
        "raspberry_pi_4",
        "arduino_uno_r3",
    ]
    assert set(STANDARD_COMPONENT_PRESETS.keys()) == set(expected_presets)
    assert len(STANDARD_COMPONENT_PRESETS) == 6


def test_get_preset_component_aries_v2_riscv():
    """Test retrieving the VEGA ARIES v2.0/v3.0 preset."""
    component = get_preset_component("aries_v2_riscv")

    assert component.id == "aries_v2_riscv"
    assert component.name == "VEGA ARIES v2.0/v3.0 (THEJAS32 RISC-V Dev Board)"
    assert component.length == 78.0
    assert component.width == 66.0
    assert component.height == 12.0
    assert component.clearance_mm == 2.0
    assert component.source == ParameterSource.DATASHEET
    assert component.confirmed is True
    assert component.type == ComponentType.PCB


def test_get_preset_component_aries_alpha_riscv():
    """Test retrieving the VEGA ARIES ALPHA preset."""
    component = get_preset_component("aries_alpha_riscv")

    assert component.id == "aries_alpha_riscv"
    assert component.name == "VEGA ARIES ALPHA v1.0 (THEJAS32 Compact)"
    assert component.length == 78.0
    assert component.width == 54.0
    assert component.height == 12.0
    assert component.clearance_mm == 2.0
    assert component.source == ParameterSource.DATASHEET
    assert component.confirmed is True


def test_get_preset_component_iot_sensor_node():
    """Test retrieving the Industrial IoT Sensor Node preset."""
    component = get_preset_component("iot_sensor_node")

    assert component.id == "iot_sensor_node"
    assert component.name == "Industrial IoT Sensor Telemetry Node"
    assert component.length == 65.0
    assert component.width == 48.0
    assert component.height == 15.0
    assert component.clearance_mm == 2.0
    assert component.source == ParameterSource.DATASHEET
    assert component.confirmed is True


def test_get_preset_component_esp32_devkit():
    """Test retrieving the ESP32 DevKitC preset."""
    component = get_preset_component("esp32_devkit")

    assert component.id == "esp32_devkit"
    assert component.name == "ESP32-WROOM-32 DevKitC"
    assert component.length == 55.0
    assert component.width == 28.0
    assert component.height == 13.0
    assert component.clearance_mm == 1.5
    assert component.source == ParameterSource.DATASHEET
    assert component.confirmed is True


def test_get_preset_component_raspberry_pi_4():
    """Test retrieving the Raspberry Pi 4/5 preset."""
    component = get_preset_component("raspberry_pi_4")

    assert component.id == "raspberry_pi_4"
    assert component.name == "Raspberry Pi 4 / 5 Model B"
    assert component.length == 85.0
    assert component.width == 56.0
    assert component.height == 17.0
    assert component.clearance_mm == 2.0
    assert component.source == ParameterSource.DATASHEET
    assert component.confirmed is True


def test_get_preset_component_arduino_uno_r3():
    """Test retrieving the Arduino Uno R3 preset."""
    component = get_preset_component("arduino_uno_r3")

    assert component.id == "arduino_uno_r3"
    assert component.name == "Arduino Uno R3 Standard"
    assert component.length == 68.6
    assert component.width == 53.4
    assert component.height == 15.0
    assert component.clearance_mm == 2.0
    assert component.source == ParameterSource.DATASHEET
    assert component.confirmed is True


def test_get_preset_component_invalid_raises():
    """Test that invalid preset ID raises KeyError with helpful message."""
    with pytest.raises(KeyError, match="Unknown preset 'invalid_id'"):
        get_preset_component("invalid_id")


def test_list_hardware_presets():
    """Test listing all hardware presets as JSON-serializable metadata."""
    presets = list_hardware_presets()

    assert len(presets) == 6
    for preset in presets:
        assert "id" in preset
        assert "name" in preset
        assert "category" in preset
        assert "length_mm" in preset
        assert "width_mm" in preset
        assert "height_mm" in preset
        assert "clearance_mm" in preset
        assert "description" in preset
        assert isinstance(preset["length_mm"], (int, float))
        assert isinstance(preset["width_mm"], (int, float))
        assert isinstance(preset["height_mm"], (int, float))
        assert isinstance(preset["clearance_mm"], (int, float))


def test_fit_check_preset_aries_v2_passes():
    """Test that VEGA ARIES v2 fits in its auto-generated enclosure."""
    component = get_preset_component("aries_v2_riscv")
    enclosure, part_spec = generate_enclosure_for_component("aries_v2_riscv")

    engine = FitCheckEngine(default_clearance_mm=component.clearance_mm)
    result = engine.check_component_fit(component, enclosure)

    assert result.fits is True
    # Clearance should match component's specified clearance
    assert result.clearance_mm["x"] == pytest.approx(component.clearance_mm * 2, rel=1e-6)
    assert result.clearance_mm["y"] == pytest.approx(component.clearance_mm * 2, rel=1e-6)
    assert result.clearance_mm["z"] >= component.clearance_mm  # Z has extra lid clearance


def test_fit_check_preset_all_pass():
    """Test that all presets fit in their auto-generated enclosures."""
    for preset_id in STANDARD_COMPONENT_PRESETS:
        component = get_preset_component(preset_id)
        enclosure, _ = generate_enclosure_for_component(preset_id)

        engine = FitCheckEngine(default_clearance_mm=component.clearance_mm)
        result = engine.check_component_fit(component, enclosure)

        assert result.fits is True, f"Preset {preset_id} should fit in its enclosure"


def test_generate_enclosure_for_component_aries_v2():
    """Test auto-enclosure generation for VEGA ARIES v2."""
    enclosure, part_spec = generate_enclosure_for_component("aries_v2_riscv")

    # Check EnclosureSpec
    assert isinstance(enclosure, EnclosureSpec)
    assert enclosure.name == "Enclosure for VEGA ARIES v2.0/v3.0 (THEJAS32 RISC-V Dev Board)"
    assert enclosure.confirmed is True
    assert enclosure.source == ParameterSource.DATASHEET
    assert enclosure.wall_thickness == 2.5  # default
    assert enclosure.lid_clearance == 4.0  # default

    # Interior = component + 2*clearance (2mm each side)
    # length: 78 + 2*2 = 82
    # width: 66 + 2*2 = 70
    # height: 12 + 2*2 + 4 (lid) = 20
    assert enclosure.interior_length == pytest.approx(82.0)
    assert enclosure.interior_width == pytest.approx(70.0)
    assert enclosure.interior_height == pytest.approx(20.0)

    # Exterior = interior + 2*wall_thickness (2.5mm each side)
    # length: 82 + 2*2.5 = 87
    # width: 70 + 2*2.5 = 75
    # height: 20 + 2*2.5 = 25
    assert enclosure.exterior_length == pytest.approx(87.0)
    assert enclosure.exterior_width == pytest.approx(75.0)
    assert enclosure.exterior_height == pytest.approx(25.0)

    # Check PartSpec
    assert isinstance(part_spec, PartSpec)
    assert part_spec.name == "Enclosure for VEGA ARIES v2.0/v3.0 (THEJAS32 RISC-V Dev Board)"
    assert part_spec.unit_system == UnitSystem.MM
    assert len(part_spec.features) == 4  # base, cavity, lid, lid_cavity

    # Verify features have confirmed parameters
    for feature in part_spec.features:
        for param in feature.parameters.values():
            assert param.confirmed is True
            assert param.source == ParameterSource.DATASHEET


def test_generate_enclosure_for_component_custom_wall_thickness():
    """Test auto-enclosure generation with custom wall thickness."""
    enclosure, part_spec = generate_enclosure_for_component(
        "aries_v2_riscv",
        wall_thickness_mm=3.0,
        lid_clearance_mm=5.0,
    )

    assert enclosure.wall_thickness == 3.0
    assert enclosure.lid_clearance == 5.0

    # Interior unchanged (based on component + clearance)
    assert enclosure.interior_length == pytest.approx(82.0)
    assert enclosure.interior_width == pytest.approx(70.0)
    assert enclosure.interior_height == pytest.approx(21.0)  # 12 + 4 + 5

    # Exterior with custom wall thickness
    assert enclosure.exterior_length == pytest.approx(88.0)  # 82 + 2*3
    assert enclosure.exterior_width == pytest.approx(76.0)   # 70 + 2*3
    assert enclosure.exterior_height == pytest.approx(27.0)  # 21 + 2*3


def test_generate_enclosure_for_component_accepts_component_spec():
    """Test that generate_enclosure_for_component accepts a ComponentSpec directly."""
    component = get_preset_component("esp32_devkit")
    enclosure, part_spec = generate_enclosure_for_component(component)

    assert enclosure.name == "Enclosure for ESP32-WROOM-32 DevKitC"
    assert enclosure.interior_length == pytest.approx(55.0 + 2 * 1.5)  # 58.0
    assert enclosure.interior_width == pytest.approx(28.0 + 2 * 1.5)   # 31.0
    assert enclosure.interior_height == pytest.approx(13.0 + 2 * 1.5 + 4.0)  # 22.0


def test_generated_part_spec_is_buildable():
    """Test that the generated PartSpec can be used to create geometry."""
    from ai3d_designer.core.geometry.engine import create_part_from_spec
    from ai3d_designer.core.validation.validator import validate_spec, validate_geometry

    enclosure, part_spec = generate_enclosure_for_component("aries_v2_riscv")

    # Validate spec
    spec_validation = validate_spec(part_spec)
    assert spec_validation.is_valid, f"Spec validation failed: {spec_validation.errors}"

    # Create geometry
    part = create_part_from_spec(part_spec)
    assert part is not None
    assert part.volume > 0

    # Validate geometry
    geom_validation = validate_geometry(part)
    assert geom_validation.is_valid, f"Geometry validation failed: {geom_validation.errors}"


def test_all_presets_generate_buildable_enclosures():
    """Test that all presets generate valid, buildable PartSpecs."""
    from ai3d_designer.core.geometry.engine import create_part_from_spec
    from ai3d_designer.core.validation.validator import validate_spec, validate_geometry

    for preset_id in STANDARD_COMPONENT_PRESETS:
        enclosure, part_spec = generate_enclosure_for_component(preset_id)

        # Validate spec
        spec_validation = validate_spec(part_spec)
        assert spec_validation.is_valid, f"Preset {preset_id} spec invalid: {spec_validation.errors}"

        # Create geometry
        part = create_part_from_spec(part_spec)
        assert part is not None, f"Preset {preset_id} geometry creation failed"
        assert part.volume > 0, f"Preset {preset_id} has zero volume"

        # Validate geometry
        geom_validation = validate_geometry(part)
        assert geom_validation.is_valid, f"Preset {preset_id} geometry invalid: {geom_validation.errors}"


def test_preset_metadata_includes_vendor_info():
    """Test that presets include vendor metadata."""
    aries = get_preset_component("aries_v2_riscv")
    assert "vendor" in aries.metadata
    assert aries.metadata["vendor"] == "VEGA"
    assert "mcu" in aries.metadata
    assert aries.metadata["mcu"] == "THEJAS32"

    pi = get_preset_component("raspberry_pi_4")
    assert "vendor" in pi.metadata
    assert pi.metadata["vendor"] == "Raspberry Pi Foundation"
    assert "models" in pi.metadata

    uno = get_preset_component("arduino_uno_r3")
    assert "vendor" in uno.metadata
    assert uno.metadata["vendor"] == "Arduino"
    assert "mounting" in uno.metadata
