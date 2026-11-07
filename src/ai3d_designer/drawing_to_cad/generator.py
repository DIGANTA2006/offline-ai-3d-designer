"""Deterministic build123d generator for the supported drawing-blueprint v1 schema."""
from __future__ import annotations

import math
import tempfile
from pathlib import Path
from typing import Any

import trimesh
from build123d import (
    Align,
    Axis,
    Box,
    BuildPart,
    BuildSketch,
    Cylinder,
    Locations,
    Mode,
    Part,
    Plane,
    Polygon,
    export_step,
    export_stl,
    extrude,
    fillet,
    revolve,
    insert,
)

from ai3d_designer.drawing_to_cad.blueprint import Blueprint, apply_defaults, lint

EPS = 1e-3
BOTTOM = (Align.CENTER, Align.CENTER, Align.MIN)


class GeometryError(RuntimeError):
    """The reviewed blueprint could not be turned into a valid single solid."""


def _cut_cylinder(x: float, y: float, diameter: float, height: float, depth: float | None) -> None:
    z0 = -1.0 if depth is None else height - depth
    cut_height = height + 2.0 - z0 if depth is None else depth + 1.0
    with Locations((x, y, z0)):
        Cylinder(radius=diameter / 2, height=cut_height, align=BOTTOM, mode=Mode.SUBTRACT)


def _cut_box(x: float, y: float, length: float, width: float, height: float, depth: float | None) -> None:
    z0 = -1.0 if depth is None else height - depth
    cut_height = height + 2.0 - z0 if depth is None else depth + 1.0
    with Locations((x, y, z0)):
        Box(length, width, cut_height, align=BOTTOM, mode=Mode.SUBTRACT)


def _flange(sketch: Any) -> None:
    Cylinder(radius=sketch.outer_diameter / 2, height=sketch.thickness, align=BOTTOM)
    if sketch.inner_bore_diameter:
        _cut_cylinder(0.0, 0.0, sketch.inner_bore_diameter, sketch.thickness, None)


def _prismatic(sketch: Any, body_type: str) -> None:
    if sketch.profile == "rectangle":
        Box(sketch.length, sketch.width, sketch.thickness, align=BOTTOM)
    elif sketch.profile in {"polygon", "complex_path"} and sketch.points:
        with BuildSketch(Plane.XY):
            Polygon(*[tuple(point) for point in sketch.points], align=None)
        extrude(amount=sketch.thickness)
    else:
        raise GeometryError(f"Profile {sketch.profile!r} is not supported for {body_type}")

    if body_type == "sheet_enclosure":
        if sketch.profile != "rectangle" or not sketch.wall_thickness:
            raise GeometryError("Sheet enclosure v1 requires a rectangle profile and positive wall thickness")
        wall = sketch.wall_thickness
        inner_length = sketch.length - 2 * wall
        inner_width = sketch.width - 2 * wall
        if inner_length <= 0 or inner_width <= 0:
            raise GeometryError("Enclosure wall leaves no interior cavity")
        with Locations((0.0, 0.0, wall)):
            Box(
                inner_length,
                inner_width,
                sketch.thickness - wall + 1.0,
                align=BOTTOM,
                mode=Mode.SUBTRACT,
            )


def _revolve_profile(points: list[list[float]]) -> None:
    # Profile points are [radius, z] in millimetres in the world XZ plane.
    with BuildSketch(Plane.XZ):
        Polygon(*[tuple(point) for point in points], align=None)
    revolve(axis=Axis.Z)


def _select_edges(part: Any, scope: str, height: float) -> list[Any]:
    edges = list(part.edges())
    if scope == "all":
        return edges
    z = height if scope == "top" else 0.0
    return [edge for edge in edges if abs(edge.center().Z - z) < EPS]


def _ring_step(feature: Any, height: float) -> None:
    """Build an annular tool so a ring recess does not fill the central bore."""
    depth = float(feature.depth or 0.0)
    z0 = height - depth if feature.ring_mode == "cut" else height
    with BuildPart() as annulus:
        with Locations((0.0, 0.0, z0)):
            Cylinder(radius=feature.diameter / 2, height=depth, align=BOTTOM)
            Cylinder(radius=feature.inner_diameter / 2, height=depth, align=BOTTOM, mode=Mode.SUBTRACT)
    insert(annulus.part, mode=Mode.SUBTRACT if feature.ring_mode == "cut" else Mode.ADD)


def _apply_features(part: Any, blueprint: Blueprint, height: float) -> None:
    outer_radius = blueprint.base_sketch.outer_diameter / 2 if blueprint.base_sketch.outer_diameter else None
    for index, feature in enumerate(blueprint.features, start=1):
        if feature.type == "through_hole":
            _cut_cylinder(feature.x, feature.y, feature.diameter, height, feature.depth)
        elif feature.type in {"circular_pattern_cut", "hole_pattern"}:
            step = 360.0 / feature.count
            for number in range(feature.count):
                angle = math.radians(feature.start_angle + number * step)
                x = feature.x + feature.pitch_radius * math.cos(angle)
                y = feature.y + feature.pitch_radius * math.sin(angle)
                _cut_cylinder(x, y, feature.diameter, height, feature.depth)
        elif feature.type == "radial_cutout_pattern":
            if outer_radius is None or feature.radius is None:
                raise GeometryError(f"Feature {index}: radial cutouts need a flange radius and cutout radius")
            centre_radius = (
                feature.root_radius + feature.radius
                if feature.root_radius is not None
                else feature.pitch_radius
            )
            if centre_radius is None or centre_radius <= 0:
                raise GeometryError(f"Feature {index}: radial cutout centre radius cannot be resolved")
            step = 360.0 / feature.count
            for number in range(feature.count):
                angle = math.radians(feature.start_angle + number * step)
                x = feature.x + centre_radius * math.cos(angle)
                y = feature.y + centre_radius * math.sin(angle)
                _cut_cylinder(x, y, 2 * feature.radius, height, None)
        elif feature.type == "ring_step":
            _ring_step(feature, height)
        elif feature.type == "pocket":
            if feature.diameter:
                _cut_cylinder(feature.x, feature.y, feature.diameter, height, feature.depth)
            else:
                _cut_box(feature.x, feature.y, feature.length, feature.width, height, feature.depth)
        elif feature.type == "fillet":
            edges = _select_edges(part, feature.edge_scope, height)
            if not edges:
                raise GeometryError(f"Feature {index}: no edges matched fillet scope {feature.edge_scope!r}")
            try:
                fillet(edges, radius=feature.radius)
            except Exception as exc:
                raise GeometryError(f"Feature {index}: fillet failed; reduce the radius or narrow the edge scope") from exc


def build_part(blueprint: Blueprint) -> tuple[Part, list[str]]:
    """Build and validate the blueprint using build123d/OpenCASCADE."""
    solid, warnings, _effective = build_part_with_effective_blueprint(blueprint)
    return solid, warnings


def build_part_with_effective_blueprint(blueprint: Blueprint) -> tuple[Part, list[str], Blueprint]:
    """Build the blueprint and return the effective copy with defaults applied.

    Stored provenance must come from the effective copy: it describes the geometry
    that was exported, including provisional defaults that were not in the drawing.
    """
    blueprint = Blueprint.model_validate(blueprint.model_dump(mode="python"))
    defaults = apply_defaults(blueprint)
    errors, warnings = lint(blueprint)
    if errors:
        raise GeometryError("; ".join(errors))

    sketch = blueprint.base_sketch
    body_type = blueprint.primary_body_type
    height = float(sketch.thickness or 0.0)

    try:
        with BuildPart() as part:
            if body_type == "rotational_flange":
                _flange(sketch)
            elif body_type in {"prismatic_box", "sheet_enclosure"}:
                _prismatic(sketch, body_type)
            elif body_type == "revolved_profile":
                _revolve_profile(sketch.points)
            else:
                raise GeometryError("Primary body type is unresolved")

            if body_type != "revolved_profile":
                _apply_features(part, blueprint, height)
    except GeometryError:
        raise
    except Exception as exc:
        raise GeometryError(f"OpenCASCADE could not construct the reviewed blueprint: {type(exc).__name__}") from exc

    solid = part.part
    if not solid.is_valid:
        raise GeometryError("OpenCASCADE reports an invalid solid")
    solids = list(solid.solids())
    if len(solids) != 1:
        raise GeometryError(f"Expected one contiguous solid; generated {len(solids)} solids")
    if not math.isfinite(solid.volume) or solid.volume <= 0:
        raise GeometryError("Generated solid has non-positive or non-finite volume")

    return solid, list(dict.fromkeys(defaults + warnings)), blueprint


def validate_solid(solid: Part, blueprint: Blueprint) -> dict[str, Any]:
    if not solid.is_valid:
        raise GeometryError("OpenCASCADE reports an invalid solid")
    if len(solid.solids()) != 1:
        raise GeometryError(f"Expected one solid, generated {len(solid.solids())}")
    if not math.isfinite(solid.volume) or solid.volume <= 0:
        raise GeometryError("Solid volume is invalid")
    size = solid.bounding_box().size
    sketch = blueprint.base_sketch
    expected: tuple[float, float] | None = None
    if blueprint.primary_body_type == "rotational_flange" and sketch.outer_diameter:
        has_perimeter_cutouts = any(feature.type == "radial_cutout_pattern" for feature in blueprint.features)
        if has_perimeter_cutouts:
            expected = None
            target = float(sketch.outer_diameter)
            tolerance = max(0.02, 0.005 * target)
            for actual in (size.X, size.Y):
                if actual > target + tolerance:
                    raise GeometryError(f"Scalloped flange extent {actual:.3f} mm exceeds outer diameter {target:.3f} mm")
        else:
            expected = (sketch.outer_diameter, sketch.outer_diameter)
    elif blueprint.primary_body_type in {"prismatic_box", "sheet_enclosure"} and sketch.profile == "rectangle":
        expected = (sketch.length, sketch.width)
    if expected:
        for desired, actual in zip(expected, (size.X, size.Y)):
            if abs(actual - desired) > max(0.02, 0.005 * desired):
                raise GeometryError(f"Built size {actual:.3f} mm does not match blueprint {desired:.3f} mm")
    return {
        "volume_mm3": round(float(solid.volume), 3),
        "bbox_mm": [round(float(size.X), 3), round(float(size.Y), 3), round(float(size.Z), 3)],
        "solid_count": 1,
        "kernel_valid": True,
    }


def export_blueprint(blueprint: Blueprint) -> dict[str, Any]:
    """Return validated STEP/STL exports as Base64 for the authenticated web API."""
    solid, warnings, effective = build_part_with_effective_blueprint(blueprint)
    metrics = validate_solid(solid, effective)
    with tempfile.TemporaryDirectory(prefix="drawing-to-cad-") as temporary:
        root = Path(temporary)
        step_path = root / "model.step"
        stl_path = root / "model.stl"
        export_step(solid, str(step_path))
        export_stl(solid, str(stl_path))
        for output in (step_path, stl_path):
            if not output.is_file() or output.stat().st_size < 100:
                raise GeometryError(f"{output.suffix.upper()} exporter returned an empty file")
        mesh = trimesh.load(str(stl_path), force="mesh")
        watertight = bool(mesh.is_watertight)
        if not watertight:
            raise GeometryError("Exported STL is not watertight; check sketch closure, holes and fillets")
        import base64

        return {
            "stepBase64": base64.b64encode(step_path.read_bytes()).decode("ascii"),
            "stlBase64": base64.b64encode(stl_path.read_bytes()).decode("ascii"),
            "partSpec": effective.model_dump(mode="json"),
            "fitReport": (
                "The deterministic blueprint generator produced one kernel-valid solid and a watertight STL. "
                "This does not certify that the drawing was interpreted correctly, that hidden features were found, "
                "or that GD&T, tolerances, material, fit or manufacturing suitability are satisfied."
            ),
            "metrics": {**metrics, "stl_watertight": True},
            "warnings": warnings,
        }
