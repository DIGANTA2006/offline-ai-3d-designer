"""Typed, unit-normalized drawing blueprint with explicit defaults and linting."""
from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BodyType = Literal["rotational_flange", "prismatic_box", "sheet_enclosure", "revolved_profile"]
Profile = Literal["circle", "rectangle", "polygon", "complex_path"]
FeatureType = Literal["circular_pattern_cut", "hole_pattern", "radial_cutout_pattern", "ring_step", "through_hole", "pocket", "fillet"]

DEFAULT_HEIGHT_MM = 10.0
DEFAULT_SHEET_WALL_MM = 2.5
MAX_DIMENSION_MM = 1_000_000.0


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BaseSketch(StrictModel):
    profile: Profile = "circle"
    outer_diameter: float | None = Field(default=None, gt=0, le=MAX_DIMENSION_MM)
    inner_bore_diameter: float | None = Field(default=None, gt=0, le=MAX_DIMENSION_MM)
    width: float | None = Field(default=None, gt=0, le=MAX_DIMENSION_MM, description="Y extent, mm")
    length: float | None = Field(default=None, gt=0, le=MAX_DIMENSION_MM, description="X extent, mm")
    thickness: float | None = Field(default=None, gt=0, le=MAX_DIMENSION_MM, description="Solid height, mm")
    wall_thickness: float | None = Field(default=None, gt=0, le=MAX_DIMENSION_MM)
    thickness_is_default: bool = False
    wall_thickness_is_default: bool = False
    # Polygon points are [x, y] in mm. Revolved profiles use [radius, z] in mm.
    points: list[list[float]] | None = Field(default=None, max_length=1000)


class Feature(StrictModel):
    type: FeatureType
    count: int = Field(default=1, ge=1, le=360)
    # Radius of the bolt/pitch circle (PCD / 2), in mm.
    pitch_radius: float | None = Field(default=None, gt=0, le=MAX_DIMENSION_MM)
    start_angle: float = Field(default=0.0, ge=-360, le=360)
    angular_pitch: float | None = Field(default=None, gt=0, le=360)
    diameter: float | None = Field(default=None, gt=0, le=MAX_DIMENSION_MM, description="Hole diameter or outer diameter of a ring step, mm")
    inner_diameter: float | None = Field(default=None, gt=0, le=MAX_DIMENSION_MM, description="Inner diameter of an annular ring step, mm")
    root_radius: float | None = Field(default=None, gt=0, le=MAX_DIMENSION_MM, description="Radial distance from the part centre to the bottom of a perimeter gullet, mm; used to derive cutter-centre radius")
    ring_mode: Literal["cut", "boss"] = "cut"
    length: float | None = Field(default=None, gt=0, le=MAX_DIMENSION_MM)
    width: float | None = Field(default=None, gt=0, le=MAX_DIMENSION_MM)
    # None denotes a through cut. Positive values denote a blind depth from the top.
    depth: float | None = Field(default=None, gt=0, le=MAX_DIMENSION_MM)
    radius: float | None = Field(default=None, gt=0, le=MAX_DIMENSION_MM)
    edge_scope: Literal["all", "top", "bottom"] = "all"
    x: float = Field(default=0.0, ge=-MAX_DIMENSION_MM, le=MAX_DIMENSION_MM)
    y: float = Field(default=0.0, ge=-MAX_DIMENSION_MM, le=MAX_DIMENSION_MM)


class Blueprint(StrictModel):
    part_name: str = Field(default="part", min_length=1, max_length=120)
    primary_body_type: BodyType | None = None
    base_sketch: BaseSketch = Field(default_factory=BaseSketch)
    features: list[Feature] = Field(default_factory=list, max_length=100)
    warnings: list[str] = Field(default_factory=list, max_length=100)
    unsupported_geometry: list[str] = Field(default_factory=list, max_length=100)
    source_pages: list[int] = Field(default_factory=list, max_length=8)
    needs_review: bool = True


def apply_defaults(bp: Blueprint) -> list[str]:
    """Apply conspicuous, review-required defaults. Repeated calls are idempotent."""
    notes: list[str] = []
    sk = bp.base_sketch
    if bp.primary_body_type in {"rotational_flange", "prismatic_box", "sheet_enclosure"} and sk.thickness is None:
        sk.thickness = DEFAULT_HEIGHT_MM
        sk.thickness_is_default = True
        notes.append(f"Solid height was not grounded to the drawing; using {DEFAULT_HEIGHT_MM:g} mm as a provisional default.")
    if bp.primary_body_type == "sheet_enclosure" and sk.wall_thickness is None:
        sk.wall_thickness = DEFAULT_SHEET_WALL_MM
        sk.wall_thickness_is_default = True
        notes.append(f"Enclosure wall thickness was not grounded to the drawing; using {DEFAULT_SHEET_WALL_MM:g} mm as a provisional default.")
    if notes:
        bp.needs_review = True
    return notes


def _positive(value: float | None) -> bool:
    return value is not None and value > 0


def lint(bp: Blueprint) -> tuple[list[str], list[str]]:
    """Return (blocking errors, non-blocking warnings) for a blueprint in mm."""
    errors: list[str] = []
    warnings = list(bp.warnings)
    sk, body = bp.base_sketch, bp.primary_body_type

    if body is None:
        errors.append("Primary body type is unresolved. Configure a vision model or select a supported body type after inspecting the drawing.")
    if bp.unsupported_geometry:
        errors.extend(f"Unsupported geometry must be modelled explicitly before export: {item}" for item in bp.unsupported_geometry)

    if body == "rotational_flange":
        if sk.profile != "circle":
            errors.append("rotational_flange requires a circular base profile")
        if not _positive(sk.outer_diameter):
            errors.append("Flange needs a grounded, positive outer_diameter")
    elif body in {"prismatic_box", "sheet_enclosure"}:
        if sk.profile not in {"rectangle", "polygon", "complex_path"}:
            errors.append(f"{body} requires a rectangular or explicitly supplied polygon profile")
        if sk.profile == "rectangle" and not (_positive(sk.length) and _positive(sk.width)):
            errors.append(f"{body} needs positive length and width")
        if sk.profile in {"polygon", "complex_path"}:
            if not sk.points or len(sk.points) < 3 or any(len(point) != 2 for point in sk.points):
                errors.append("Polygon profile needs at least three [x, y] points")
    elif body == "revolved_profile":
        if not sk.points or len(sk.points) < 3 or any(len(point) != 2 for point in sk.points):
            errors.append("Revolved profiles need at least three [radius, z] points")
        elif any(point[0] <= 0 for point in sk.points):
            errors.append("Revolved profile radii must be positive and cannot cross the rotation axis")

    if body == "revolved_profile" and bp.features:
        errors.append("Features on revolved_profile bodies are not supported in v1; model those cuts/fillets directly in the revolved profile before export")
    if body != "revolved_profile" and not _positive(sk.thickness):
        errors.append("Thickness must be positive")
    if _positive(sk.inner_bore_diameter):
        if body != "rotational_flange":
            errors.append("The v1 central-bore generator is supported only for rotational_flange bodies")
        if not _positive(sk.outer_diameter):
            errors.append("Central bore cannot be validated without a positive outer diameter")
        elif sk.inner_bore_diameter >= sk.outer_diameter:
            errors.append("Bore must be smaller than the outer diameter")
    if body == "sheet_enclosure" and _positive(sk.wall_thickness) and _positive(sk.width) and _positive(sk.length):
        if 2 * sk.wall_thickness >= min(sk.width, sk.length):
            errors.append("Wall thickness is too large for the enclosure footprint")
    if body in {"rotational_flange", "prismatic_box", "sheet_enclosure"} and _positive(sk.thickness):
        h = sk.thickness
        outer_r = sk.outer_diameter / 2 if body == "rotational_flange" and _positive(sk.outer_diameter) else None
        bore_r = sk.inner_bore_diameter / 2 if _positive(sk.inner_bore_diameter) else 0.0
        for i, feature in enumerate(bp.features, start=1):
            tag = f"Feature {i} ({feature.type})"
            if feature.type != "ring_step" and feature.depth is not None and feature.depth > h:
                errors.append(f"{tag}: blind-cut depth cannot exceed body thickness")

            if feature.type in {"circular_pattern_cut", "hole_pattern"}:
                if feature.type == "hole_pattern" and body != "rotational_flange":
                    errors.append(f"{tag}: hole_pattern is supported only on rotational_flange bodies in v1")
                if feature.count < 2 or not (_positive(feature.pitch_radius) and _positive(feature.diameter)):
                    errors.append(f"{tag}: needs count >= 2, pitch_radius and diameter")
                    continue
                if outer_r is not None and feature.pitch_radius + feature.diameter / 2 >= outer_r:
                    errors.append(f"{tag}: holes break through the outer edge")
                if feature.pitch_radius - feature.diameter / 2 <= bore_r:
                    errors.append(f"{tag}: holes cut into the bore")
                if feature.angular_pitch is not None and abs(feature.angular_pitch - 360 / feature.count) > 0.5:
                    errors.append(f"{tag}: partial/uneven angular patterns are not supported in v1; no model will be generated using a full-circle substitute")

            elif feature.type == "radial_cutout_pattern":
                if body != "rotational_flange":
                    errors.append(f"{tag}: radial perimeter cutouts require a rotational_flange body")
                if feature.count < 3 or not _positive(feature.radius):
                    errors.append(f"{tag}: needs count >= 3 and a positive cutout radius")
                    continue
                if not (_positive(feature.pitch_radius) or _positive(feature.root_radius)):
                    errors.append(f"{tag}: needs a cutter-centre pitch_radius or a drawing-grounded root_radius")
                    continue
                if outer_r is None:
                    errors.append(f"{tag}: a positive flange outer_diameter is required")
                    continue
                if feature.root_radius is not None:
                    if feature.root_radius >= outer_r:
                        errors.append(f"{tag}: root_radius must be smaller than the flange outer radius")
                    if feature.root_radius <= bore_r:
                        errors.append(f"{tag}: root_radius reaches or crosses the central bore")
                    derived_pitch = feature.root_radius + feature.radius
                    if feature.pitch_radius is not None and abs(feature.pitch_radius - derived_pitch) > max(0.02, derived_pitch * 0.001):
                        errors.append(f"{tag}: pitch_radius conflicts with the specified outer radius, cutout radius and root_radius")
                    centre_radius = derived_pitch
                else:
                    centre_radius = float(feature.pitch_radius or 0)
                if centre_radius <= 0:
                    errors.append(f"{tag}: derived cutter-centre radius is not positive")
                    continue
                if centre_radius - feature.radius >= outer_r or centre_radius + feature.radius <= outer_r:
                    errors.append(f"{tag}: circular cutouts must intersect the outer perimeter to form scallops")
                if centre_radius - feature.radius <= bore_r:
                    errors.append(f"{tag}: cutout reaches or crosses the central bore")
                centre_spacing = 2 * centre_radius * math.sin(math.pi / feature.count)
                if centre_spacing < 2 * feature.radius - 1e-6:
                    errors.append(f"{tag}: adjacent circular cutouts overlap; define a supported explicit profile instead")
                if feature.angular_pitch is not None and abs(feature.angular_pitch - 360 / feature.count) > 0.5:
                    errors.append(f"{tag}: partial/uneven angular cutout patterns are not supported in v1")

            elif feature.type == "ring_step":
                if body != "rotational_flange":
                    errors.append(f"{tag}: concentric ring steps require a rotational_flange body")
                if not (_positive(feature.diameter) and _positive(feature.inner_diameter) and _positive(feature.depth)):
                    errors.append(f"{tag}: needs outer diameter, inner_diameter and positive depth")
                    continue
                if feature.inner_diameter >= feature.diameter:
                    errors.append(f"{tag}: inner_diameter must be smaller than the ring outer diameter")
                if outer_r is not None and feature.diameter > 2 * outer_r + 1e-3:
                    errors.append(f"{tag}: ring outer diameter cannot exceed the base flange diameter")
                if feature.ring_mode == "cut" and feature.depth > h:
                    errors.append(f"{tag}: annular recess depth cannot exceed body thickness")

            elif feature.type in {"through_hole", "pocket"}:
                if feature.type == "through_hole" and not _positive(feature.diameter):
                    errors.append(f"{tag}: needs a positive diameter")
                if feature.type == "pocket" and not (
                    _positive(feature.diameter) or (_positive(feature.length) and _positive(feature.width))
                ):
                    errors.append(f"{tag}: needs a diameter, or a length and width")

            elif feature.type == "fillet" and not _positive(feature.radius):
                errors.append(f"{tag}: needs a positive radius")

    return errors, list(dict.fromkeys(warnings))
