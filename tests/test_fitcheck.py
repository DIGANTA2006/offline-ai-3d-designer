"""
Tests for the fit check module (WS5 - T40, T43).
"""

import pytest
from ai3d_designer.fitcheck.engine import FitCheckEngine, check_fit
from ai3d_designer.fitcheck.models import ComponentSpec, EnclosureSpec, ComponentType, FitCheckResult, FitCheckReport
from ai3d_designer.core.spec.models import ParameterSource


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
        mounting_bosses=[[10, 10, 0], [40, 10, 0], [10, 20, 0], [40, 20, 0]],
    )

    engine = FitCheckEngine()
    result = engine.check_component_fit(component, enclosure)

    assert result.fits is True


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
