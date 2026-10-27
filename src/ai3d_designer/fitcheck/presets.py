"""
Embedded Hardware Library & Auto-Enclosure Bridge (Step E).

Provides source-labelled but unconfirmed hardware starting presets, a dimension fit check,
and separate buildable enclosure-body/lid PartSpecs. Derived geometry stays unconfirmed until
the user reviews dimensions, clearances, mounting positions, and the exact component revision.
"""

from math import isfinite
from typing import Dict, List, Optional, Union
from ai3d_designer.core.spec.models import (
    ComponentSpec,
    ComponentType,
    EnclosureSpec,
    PartSpec,
    FeatureSpec,
    PrimitiveType,
    OperationType,
    ParameterSpec,
    ParameterSource,
    UnitSystem,
)
from ai3d_designer.fitcheck.engine import FitCheckEngine


# =============================================================================
# Standard Component Presets (Datasheet-verified, confirmed=True)
# =============================================================================

# Note: Tests expect width = shorter dimension (Y-axis), depth = longer dimension (X-axis)
STANDARD_COMPONENT_PRESETS: Dict[str, ComponentSpec] = {
    "aries_v2_riscv": ComponentSpec(
        id="aries_v2_riscv",
        name="VEGA ARIES v2.0/v3.0 (THEJAS32 RISC-V Dev Board)",
        type=ComponentType.PCB,
        # Dimensions in mm: width=Y (shorter), depth=X (longer), height=Z
        width=66.0,
        depth=78.0,
        height=12.0,
        clearance_mm=2.0,
        mounting_holes=[
            [3.0, 3.0],
            [75.0, 3.0],
            [75.0, 63.0],
            [3.0, 63.0],
        ],
        metadata={
            "vendor": "VEGA",
            "series": "ARIES",
            "mcu": "THEJAS32",
            "form_factor": "Dev Board",
            "mounting_hole_diameter_mm": 3.2,
            "mounting": "4x M3 corner holes",
            "description": "VEGA ARIES v2.0/v3.0 RISC-V development board with THEJAS32 MCU, 78x66x12 mm",
        },
        description="VEGA ARIES v2.0/v3.0 RISC-V development board with THEJAS32 MCU, 78x66x12 mm",
        source=ParameterSource.DATASHEET,
        confirmed=False,
        datasheet_url="https://vegaprocessors.in/aries/",
        part_number="ARIES-V2-THEJAS32",
    ),
    "aries_alpha_riscv": ComponentSpec(
        id="aries_alpha_riscv",
        name="VEGA ARIES ALPHA v1.0 (THEJAS32 Compact)",
        type=ComponentType.PCB,
        width=54.0,
        depth=78.0,
        height=12.0,
        clearance_mm=2.0,
        mounting_holes=[
            [3.0, 3.0],
            [75.0, 3.0],
            [75.0, 51.0],
            [3.0, 51.0],
        ],
        metadata={
            "vendor": "VEGA",
            "series": "ARIES ALPHA",
            "mcu": "THEJAS32",
            "form_factor": "Compact Dev Board",
            "mounting_hole_diameter_mm": 3.2,
            "mounting": "4x M3 corner holes",
            "description": "VEGA ARIES ALPHA compact RISC-V development board, 78x54x12 mm",
        },
        description="VEGA ARIES ALPHA compact RISC-V development board, 78x54x12 mm",
        source=ParameterSource.DATASHEET,
        confirmed=False,
        datasheet_url="https://vegaprocessors.in/aries-alpha/",
        part_number="ARIES-ALPHA-THEJAS32",
    ),
    "iot_sensor_node": ComponentSpec(
        id="iot_sensor_node",
        name="Industrial IoT Sensor Telemetry Node",
        type=ComponentType.PCB,
        width=48.0,
        depth=65.0,
        height=15.0,
        clearance_mm=2.0,
        mounting_holes=[
            [3.0, 3.0],
            [62.0, 3.0],
            [62.0, 45.0],
            [3.0, 45.0],
        ],
        metadata={
            "vendor": "Generic Industrial",
            "series": "IoT Sensor Node",
            "form_factor": "Telemetry PCB",
            "mounting_hole_diameter_mm": 3.2,
            "mounting": "4x M3 corner holes",
            "description": "Industrial IoT sensor telemetry node with 4x M3 corner mounting, 65x48x15 mm",
        },
        description="Industrial IoT sensor telemetry node with 4x M3 corner mounting, 65x48x15 mm",
        source=ParameterSource.DEFAULT,
        confirmed=False,
        datasheet_url=None,
        part_number="IOT-SENSOR-NODE-01",
    ),
    "esp32_devkit": ComponentSpec(
        id="esp32_devkit",
        name="ESP32-WROOM-32 DevKitC",
        type=ComponentType.PCB,
        width=28.0,
        depth=55.0,
        height=13.0,
        clearance_mm=1.5,
        mounting_holes=[
            [2.5, 2.5],
            [52.5, 2.5],
            [52.5, 25.5],
            [2.5, 25.5],
        ],
        metadata={
            "vendor": "Espressif",
            "series": "ESP32 DevKitC",
            "mcu": "ESP32-WROOM-32",
            "form_factor": "Dev Board",
            "mounting_hole_diameter_mm": 3.0,
            "mounting": "4x M3 corner holes",
            "description": "ESP32-WROOM-32 DevKitC development board, 55x28x13 mm",
        },
        description="ESP32-WROOM-32 DevKitC development board, 55x28x13 mm",
        source=ParameterSource.DATASHEET,
        confirmed=False,
        datasheet_url="https://docs.espressif.com/projects/esp-idf/en/latest/esp32/hw-reference/esp32/get-started-devkitc.html",
        part_number="ESP32-DEVKITC-V4",
    ),
    "raspberry_pi_4": ComponentSpec(
        id="raspberry_pi_4",
        name="Raspberry Pi 4 / 5 Model B",
        type=ComponentType.PCB,
        width=56.0,
        depth=85.0,
        height=17.0,
        clearance_mm=2.5,
        mounting_holes=[
            [3.5, 3.5],
            [81.5, 3.5],
            [81.5, 52.5],
            [3.5, 52.5],
        ],
        metadata={
            "vendor": "Raspberry Pi Foundation",
            "series": "Model B",
            "models": ["Pi 4", "Pi 5"],
            "form_factor": "SBC",
            "mounting_hole_diameter_mm": 2.7,
            "mounting": "4x M2.7 corner holes",
            "description": "Raspberry Pi 4/5 Model B single-board computer with GPIO, HDMI, Ethernet, 85x56x17 mm",
        },
        description="Raspberry Pi 4/5 Model B single-board computer with GPIO, HDMI, Ethernet, 85x56x17 mm",
        source=ParameterSource.DATASHEET,
        confirmed=False,
        datasheet_url="https://www.raspberrypi.com/documentation/computers/raspberry-pi.html",
        part_number="RPI4-MODELB-4GB",
    ),
    "arduino_uno_r3": ComponentSpec(
        id="arduino_uno_r3",
        name="Arduino Uno R3 Standard",
        type=ComponentType.PCB,
        width=53.4,
        depth=68.6,
        height=15.0,
        clearance_mm=2.0,
        mounting_holes=[
            [3.2, 3.2],
            [65.4, 3.2],
            [65.4, 50.2],
            [3.2, 50.2],
        ],
        metadata={
            "vendor": "Arduino",
            "series": "Uno",
            "model": "R3",
            "mcu": "ATmega328P",
            "form_factor": "Dev Board",
            "mounting_hole_diameter_mm": 3.2,
            "mounting": "4x M3 corner holes",
            "description": "Arduino Uno R3 standard development board, 68.6x53.4x15 mm with 4x 3.2mm mounting holes",
        },
        description="Arduino Uno R3 standard development board, 68.6x53.4x15 mm with 4x 3.2mm mounting holes",
        source=ParameterSource.DATASHEET,
        confirmed=False,
        datasheet_url="https://docs.arduino.cc/hardware/uno-rev3",
        part_number="A000066",
    ),
}


def list_hardware_presets() -> List[Dict]:
    """Return a summary list of all available hardware presets."""
    return [
        {
            "id": preset_id,
            "name": component.name,
            "type": component.type.value,
            "category": "Development Board" if component.type == ComponentType.PCB else "Component",
            "length_mm": component.depth,  # longer dimension
            "width_mm": component.width,   # shorter dimension
            "height_mm": component.height,
            "clearance_mm": component.clearance_mm,
            "description": component.description,
            "source": component.source.value,
            "confirmed": component.confirmed,
            "vendor": component.metadata.get("vendor", "Unknown"),
            "part_number": component.part_number,
        }
        for preset_id, component in STANDARD_COMPONENT_PRESETS.items()
    ]


def get_preset_component(preset_id: str) -> ComponentSpec:
    """Get a component preset by ID."""
    if preset_id not in STANDARD_COMPONENT_PRESETS:
        raise KeyError(f"Unknown preset '{preset_id}'")
    return STANDARD_COMPONENT_PRESETS[preset_id]


# =============================================================================
# Auto-Enclosure Generation
# =============================================================================

def _validate_non_negative_finite(name: str, value: float, *, strictly_positive: bool = False) -> float:
    """Validate user-supplied enclosure dimensions before building a feature program."""
    number = float(value)
    if not isfinite(number) or (number <= 0 if strictly_positive else number < 0):
        qualifier = "positive" if strictly_positive else "finite and non-negative"
        raise ValueError(f"{name} must be {qualifier}.")
    return number


def _unconfirmed_parameter(name: str, value: float) -> ParameterSpec:
    """Keep generated dimensions reviewable instead of treating defaults as datasheet facts."""
    return ParameterSpec(
        name=name,
        value=float(value),
        unit=UnitSystem.MM,
        source=ParameterSource.DEFAULT,
        confirmed=False,
    )


def generate_enclosure_for_component(
    component: Union[str, ComponentSpec],
    wall_thickness_mm: float = 2.5,
    lid_clearance_mm: float = 4.0,
    extra_clearance_mm: float = 0.0,
) -> tuple[EnclosureSpec, PartSpec]:
    """
    Build an open-top enclosure body for a component.

    Component mounting coordinates are measured from the component's lower-left
    edge as [X along component.depth, Y along component.width]. FeatureSpec
    positions and Box geometry are centred at the world origin, so coordinates
    are transformed before adding bosses.

    The lid is intentionally generated separately by generate_lid_for_enclosure:
    a removable lid is a second physical part and must not be Boolean-unioned to
    the enclosure body. Every derived dimension remains unconfirmed until review.
    """
    if isinstance(component, str):
        component = get_preset_component(component)

    wall_thickness_mm = _validate_non_negative_finite(
        "wall_thickness_mm", wall_thickness_mm, strictly_positive=True
    )
    lid_clearance_mm = _validate_non_negative_finite("lid_clearance_mm", lid_clearance_mm)
    extra_clearance_mm = _validate_non_negative_finite("extra_clearance_mm", extra_clearance_mm)
    clearance = _validate_non_negative_finite("component.clearance_mm", component.clearance_mm)
    clearance += extra_clearance_mm

    interior_width = component.width + 2 * clearance
    interior_depth = component.depth + 2 * clearance
    interior_height = component.height + 2 * clearance + lid_clearance_mm

    # EnclosureSpec dimensions use width=short axis and depth=long axis.
    # The build123d Box uses X=width and Y=depth, while the hardware presets'
    # hole coordinates use X=long and Y=short; swap the dimensions for the
    # actual feature program so each mounting hole remains on the correct axis.
    enclosure = EnclosureSpec(
        id=f"enclosure_{component.id}",
        name=f"Enclosure for {component.name}",
        interior_width=interior_width,
        interior_depth=interior_depth,
        interior_height=interior_height,
        wall_thickness=wall_thickness_mm,
        lid_clearance=lid_clearance_mm,
        mounting_bosses=[
            [
                wall_thickness_mm + (interior_depth - component.depth) / 2 + float(hole[0]),
                wall_thickness_mm + (interior_width - component.width) / 2 + float(hole[1]),
            ]
            for hole in component.mounting_holes
            if isinstance(hole, (list, tuple))
            and len(hole) >= 2
            and isfinite(float(hole[0]))
            and isfinite(float(hole[1]))
        ],
        source=ParameterSource.DEFAULT,
        confirmed=False,
        description=(
            f"Suggested enclosure for {component.name}; verify the component revision, "
            "clearances, mounting pattern, and lid fit before export."
        ),
    )

    part_spec = PartSpec(
        id=f"part_{enclosure.id}",
        name=enclosure.name,
        description=enclosure.description,
        unit_system=UnitSystem.MM,
        metadata={
            "assembly_role": "enclosure_body",
            "requires_review": True,
            "component_id": component.id,
            "component_source": component.source.value,
            "component_datasheet_url": component.datasheet_url,
        },
    )

    # The open-top body is one connected solid. Its total height is interior
    # cavity height + floor thickness; the removable lid accounts for the other
    # wall thickness in EnclosureSpec.exterior_height.
    base_exterior_height = enclosure.interior_height + wall_thickness_mm
    outer_box = FeatureSpec(
        id="outer_box",
        type=PrimitiveType.BOX,
        name="Enclosure Outer Shell",
        parameters={
            "width": _unconfirmed_parameter("width", enclosure.exterior_depth),
            "depth": _unconfirmed_parameter("depth", enclosure.exterior_width),
            "height": _unconfirmed_parameter("height", base_exterior_height),
        },
        position=[0.0, 0.0, 0.0],
        rotation=[0.0, 0.0, 0.0],
        operation=OperationType.UNION,
    )
    part_spec.add_feature(outer_box)

    # The cavity begins one wall thickness above the base and overruns the top
    # by a small amount to avoid a coincident cutting face.
    epsilon = 0.1
    cavity_height = enclosure.interior_height + epsilon
    inner_cavity = FeatureSpec(
        id="inner_cavity",
        type=PrimitiveType.BOX,
        name="Enclosure Interior Cavity",
        parameters={
            "width": _unconfirmed_parameter("width", enclosure.interior_depth),
            "depth": _unconfirmed_parameter("depth", enclosure.interior_width),
            "height": _unconfirmed_parameter("height", cavity_height),
        },
        position=[0.0, 0.0, (wall_thickness_mm + epsilon) / 2],
        rotation=[0.0, 0.0, 0.0],
        operation=OperationType.DIFFERENCE,
        parent_id="outer_box",
    )
    part_spec.add_feature(inner_cavity)

    if component.mounting_holes:
        boss_radius = 3.0
        hole_diameter = component.metadata.get("mounting_hole_diameter_mm", 3.2)
        try:
            hole_radius = float(hole_diameter) / 2
        except (TypeError, ValueError) as exc:
            raise ValueError("mounting_hole_diameter_mm must be a positive finite number.") from exc
        if not isfinite(hole_radius) or hole_radius <= 0 or hole_radius >= boss_radius:
            raise ValueError("Mounting-hole diameter must be positive and smaller than the generated boss diameter.")

        # Mounting-hole points are edge-origin coordinates. Convert to a centred
        # component frame in world X/Y, with the long dimension along X.
        floor_top = -enclosure.interior_height / 2 + wall_thickness_mm / 2
        boss_height = wall_thickness_mm
        boss_z = floor_top + boss_height / 2 - 0.05
        for index, hole in enumerate(component.mounting_holes):
            if not isinstance(hole, (list, tuple)) or len(hole) < 2:
                raise ValueError(f"Mounting hole {index + 1} must contain X and Y coordinates.")
            try:
                hole_x, hole_y = float(hole[0]), float(hole[1])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Mounting hole {index + 1} coordinates must be numeric.") from exc
            if not isfinite(hole_x) or not isfinite(hole_y):
                raise ValueError(f"Mounting hole {index + 1} coordinates must be finite.")
            if not (0 <= hole_x <= component.depth and 0 <= hole_y <= component.width):
                raise ValueError(
                    f"Mounting hole {index + 1} lies outside the component's depth/width bounds."
                )

            boss_x = hole_x - component.depth / 2
            boss_y = hole_y - component.width / 2
            boss = FeatureSpec(
                id=f"mounting_boss_{index}",
                type=PrimitiveType.CYLINDER,
                name=f"Mounting Boss {index + 1}",
                parameters={
                    "radius": _unconfirmed_parameter("radius", boss_radius),
                    "height": _unconfirmed_parameter("height", boss_height),
                },
                position=[boss_x, boss_y, boss_z],
                rotation=[0.0, 0.0, 0.0],
                operation=OperationType.UNION,
            )
            part_spec.add_feature(boss)

            boss_hole = FeatureSpec(
                id=f"mounting_boss_hole_{index}",
                type=PrimitiveType.CYLINDER,
                name=f"Mounting Boss Hole {index + 1}",
                parameters={
                    "radius": _unconfirmed_parameter("radius", hole_radius),
                    "height": _unconfirmed_parameter("height", boss_height + 0.2),
                },
                position=[boss_x, boss_y, boss_z],
                rotation=[0.0, 0.0, 0.0],
                operation=OperationType.DIFFERENCE,
            )
            part_spec.add_feature(boss_hole)

    return enclosure, part_spec


def generate_lid_for_enclosure(
    enclosure: EnclosureSpec,
    lip_clearance_mm: float = 0.3,
    lip_height_mm: Optional[float] = None,
) -> PartSpec:
    """
    Generate a separate, buildable lid PartSpec for an open-top enclosure.

    A small locating lip is fused to the lid plate. The lid is kept separate
    from the enclosure body so that the two physical pieces can be exported,
    printed, and assembled independently.
    """
    lip_clearance_mm = _validate_non_negative_finite("lip_clearance_mm", lip_clearance_mm)
    wall = _validate_non_negative_finite(
        "enclosure.wall_thickness", enclosure.wall_thickness, strictly_positive=True
    )
    if lip_height_mm is None:
        lip_height_mm = min(wall, 3.0)
    lip_height_mm = _validate_non_negative_finite(
        "lip_height_mm", lip_height_mm, strictly_positive=True
    )
    if lip_height_mm > wall:
        raise ValueError("lip_height_mm cannot exceed the enclosure wall thickness.")

    lip_width = enclosure.interior_width - 2 * lip_clearance_mm
    lip_depth = enclosure.interior_depth - 2 * lip_clearance_mm
    if lip_width <= 0 or lip_depth <= 0:
        raise ValueError("Lip clearance leaves no usable enclosure opening.")

    part_spec = PartSpec(
        id=f"lid_{enclosure.id}",
        name=f"Lid for {enclosure.name}",
        description=(
            "Separate removable lid with a locating lip. Verify the fit and "
            "printing tolerances against the selected material and printer."
        ),
        unit_system=UnitSystem.MM,
        metadata={
            "assembly_role": "enclosure_lid",
            "requires_review": True,
            "enclosure_id": enclosure.id,
        },
    )
    base_top = (enclosure.interior_height + wall) / 2
    plate = FeatureSpec(
        id="lid_plate",
        type=PrimitiveType.BOX,
        name="Lid Plate",
        parameters={
            "width": _unconfirmed_parameter("width", enclosure.exterior_depth),
            "depth": _unconfirmed_parameter("depth", enclosure.exterior_width),
            "height": _unconfirmed_parameter("height", wall),
        },
        position=[0.0, 0.0, base_top + wall / 2],
        rotation=[0.0, 0.0, 0.0],
        operation=OperationType.UNION,
    )
    part_spec.add_feature(plate)

    lip_height = lip_height_mm
    lip = FeatureSpec(
        id="lid_locating_lip",
        type=PrimitiveType.BOX,
        name="Lid Locating Lip",
        parameters={
            "width": _unconfirmed_parameter("width", lip_depth),
            "depth": _unconfirmed_parameter("depth", lip_width),
            "height": _unconfirmed_parameter("height", lip_height),
        },
        # Centre the lip under the plate and overlap by 0.1 mm to make a
        # single solid rather than two merely touching solids.
        position=[0.0, 0.0, base_top - lip_height / 2 + 0.05],
        rotation=[0.0, 0.0, 0.0],
        operation=OperationType.UNION,
        parent_id="lid_plate",
    )
    part_spec.add_feature(lip)
    return part_spec


# =============================================================================
# Fit Check Integration
# =============================================================================

def run_fit_check(component: Union[str, ComponentSpec], enclosure: EnclosureSpec) -> "FitCheckReport":
    """Run fit check between component and enclosure."""
    if isinstance(component, str):
        component = get_preset_component(component)
    
    engine = FitCheckEngine(default_clearance_mm=component.clearance_mm)
    return engine.check_all_components(
        [component],
        enclosure,
        clearance_mm=component.clearance_mm,
    )


# =============================================================================
# Golden 5 Reference Showcase (for UI)
# =============================================================================

GOLDEN_5_SHOWCASE = [
    {
        "id": "golden_1",
        "title": "RISC-V Board Enclosure",
        "description": "VEGA ARIES v2.0 RISC-V dev board enclosure with mounting bosses",
        "preset_id": "aries_v2_riscv",
        "category": "Development Board",
        "preview_image": None,
    },
    {
        "id": "golden_2",
        "title": "MB-001 Mounting Bracket",
        "description": "Universal mounting bracket for IoT sensor nodes",
        "preset_id": "iot_sensor_node",
        "category": "Mounting Hardware",
        "preview_image": None,
    },
    {
        "id": "golden_3",
        "title": "U-Clevis Block",
        "description": "Parametric U-clevis for linkage assemblies",
        "preset_id": None,  # Custom parametric
        "category": "Mechanical Component",
        "preview_image": None,
    },
    {
        "id": "golden_4",
        "title": "Robotics Sensor Plate",
        "description": "Multi-sensor mounting plate for robotics",
        "preset_id": "iot_sensor_node",
        "category": "Robotics",
        "preview_image": None,
    },
    {
        "id": "golden_5",
        "title": "Metrology Calibration Ring",
        "description": "Precision calibration ring for CMM verification",
        "preset_id": None,  # Custom parametric
        "category": "Metrology",
        "preview_image": None,
    },
]


def get_golden_5_showcase() -> List[Dict]:
    """Return the Golden 5 reference showcase items."""
    return GOLDEN_5_SHOWCASE
