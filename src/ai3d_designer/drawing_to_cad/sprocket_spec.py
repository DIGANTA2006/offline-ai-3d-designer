"""ISO 606 B-series chain dimensions and validation for standard sprocket geometry.

The generated seat cuts are a deterministic preview approximation, not a certified ISO
606 tooth profile. Engagement-critical parts require mechanical review.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

CHAIN_TABLE: dict[str, tuple[float, float]] = {
    "06B": (9.525, 6.35),
    "08B": (12.70, 8.51),
    "10B": (15.875, 10.16),
    "12B": (19.05, 12.07),
    "16B": (25.40, 15.88),
}
MIN_TEETH = 9
MAX_TEETH = 120
MAX_BOLTS = 20
SEAT_CLEARANCE_MM = 0.2
MIN_WALL_MM = 3.0
OD_TOLERANCE_MM = 1.0
PD_TOLERANCE_MM = 0.5
STANDARD_PITCH_TOL_MM = 0.5


class Source(str, Enum):
    ANNOTATED = "annotated"
    ESTIMATED = "estimated"


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    severity: Severity
    code: str
    message: str


@dataclass(frozen=True)
class SprocketSpec:
    chain: str
    teeth: int
    thickness_mm: float
    bore_mm: float | None = None
    bolt_count: int = 0
    bolt_hole_dia_mm: float = 0.0
    bolt_pcd_mm: float | None = None
    drawing_od_mm: float | None = None
    drawing_pd_mm: float | None = None
    sources: dict[str, Source] = field(default_factory=dict)


@dataclass(frozen=True)
class Derived:
    pitch_mm: float
    roller_dia_mm: float
    pitch_dia_mm: float
    outside_dia_mm: float
    root_dia_mm: float
    seat_radius_mm: float
    bolt_pcd_mm: float | None


def pitch_mm(chain: str) -> float:
    return CHAIN_TABLE[chain][0]


def roller_dia_mm(chain: str) -> float:
    return CHAIN_TABLE[chain][1]


def pitch_diameter_mm(pitch: float, teeth: int) -> float:
    """Pitch diameter: p / sin(pi / N)."""
    return pitch / math.sin(math.pi / teeth)


def outside_diameter_mm(pitch: float, teeth: int) -> float:
    """Outside diameter: p * (0.6 + cot(pi / N))."""
    return pitch * (0.6 + 1.0 / math.tan(math.pi / teeth))


def implied_pitch_mm(outside_dia: float, teeth: int) -> float:
    return outside_dia / (0.6 + 1.0 / math.tan(math.pi / teeth))


def axis_extent_bounds_mm(d: Derived) -> tuple[float, float]:
    """Allowed half-extent along X/Y for equally spaced circular tooth-seat cuts."""
    big_r = d.outside_dia_mm / 2
    pitch_r = d.pitch_dia_mm / 2
    seat_r = d.seat_radius_mm
    cosine = (big_r * big_r + pitch_r * pitch_r - seat_r * seat_r) / (2 * big_r * pitch_r)
    cosine = max(-1.0, min(1.0, cosine))
    return big_r * cosine, big_r


def derive(spec: SprocketSpec) -> Derived:
    pitch = pitch_mm(spec.chain)
    roller = roller_dia_mm(spec.chain)
    pitch_dia = pitch_diameter_mm(pitch, spec.teeth)
    outside_dia = outside_diameter_mm(pitch, spec.teeth)
    root_dia = pitch_dia - roller
    seat_radius = roller / 2 + SEAT_CLEARANCE_MM
    bolt_pcd = spec.bolt_pcd_mm
    if spec.bolt_count and bolt_pcd is None:
        bolt_pcd = ((spec.bore_mm or 0.0) + (root_dia - 2 * SEAT_CLEARANCE_MM)) / 2
    return Derived(pitch, roller, pitch_dia, outside_dia, root_dia, seat_radius, bolt_pcd)


def has_errors(issues: list[Issue]) -> bool:
    return any(issue.severity is Severity.ERROR for issue in issues)


def validate(spec: SprocketSpec) -> list[Issue]:
    issues: list[Issue] = []

    def error(code: str, message: str) -> None:
        issues.append(Issue(Severity.ERROR, code, message))

    def warning(code: str, message: str) -> None:
        issues.append(Issue(Severity.WARNING, code, message))

    if spec.chain not in CHAIN_TABLE:
        error("UNKNOWN_CHAIN", f"Chain '{spec.chain}' is not supported. Supported: {', '.join(CHAIN_TABLE)}.")
        return issues
    if not MIN_TEETH <= spec.teeth <= MAX_TEETH:
        error("TEETH_RANGE", f"{spec.teeth} teeth is outside the supported range {MIN_TEETH}-{MAX_TEETH}.")
        return issues
    if not math.isfinite(spec.thickness_mm) or spec.thickness_mm <= 0:
        error("THICKNESS", "Thickness must be finite and greater than zero.")
    if spec.bore_mm is not None and (not math.isfinite(spec.bore_mm) or spec.bore_mm <= 0):
        error("BORE", "Bore must be finite and greater than zero when specified.")
    if issues:
        return issues

    d = derive(spec)
    root_r = d.root_dia_mm / 2
    bore_r = (spec.bore_mm or 0.0) / 2
    if bore_r + MIN_WALL_MM > root_r - SEAT_CLEARANCE_MM:
        error(
            "BORE_TOO_LARGE",
            f"A {spec.bore_mm:.1f} mm bore leaves less than {MIN_WALL_MM} mm of material to "
            f"the tooth roots ({d.root_dia_mm:.1f} mm root diameter).",
        )
        return issues

    if spec.bolt_count:
        if not 1 <= spec.bolt_count <= MAX_BOLTS:
            error("BOLT_COUNT", f"Bolt count must be between 1 and {MAX_BOLTS}.")
        if not math.isfinite(spec.bolt_hole_dia_mm) or spec.bolt_hole_dia_mm <= 0:
            error("BOLT_DIA", "Bolt hole diameter must be finite and greater than zero.")
        if not issues and d.bolt_pcd_mm is not None:
            bolt_r = d.bolt_pcd_mm / 2
            hole_r = spec.bolt_hole_dia_mm / 2
            inner_limit = bore_r + MIN_WALL_MM
            outer_limit = root_r - SEAT_CLEARANCE_MM - MIN_WALL_MM
            if bolt_r - hole_r < inner_limit or bolt_r + hole_r > outer_limit:
                error(
                    "BOLT_OUT_OF_HUB",
                    f"A {d.bolt_pcd_mm:.1f} mm bolt circle with {spec.bolt_hole_dia_mm:.1f} mm holes "
                    f"does not fit between the bore and the roots with a {MIN_WALL_MM} mm wall.",
                )
            if spec.bolt_count >= 2:
                spacing = 2 * bolt_r * math.sin(math.pi / spec.bolt_count)
                if spacing < spec.bolt_hole_dia_mm + MIN_WALL_MM:
                    error(
                        "BOLTS_CRAMPED",
                        f"{spec.bolt_count} holes of {spec.bolt_hole_dia_mm:.1f} mm are too close "
                        f"together on a {d.bolt_pcd_mm:.1f} mm circle.",
                    )
            if spec.bolt_pcd_mm is None:
                warning("BOLT_PCD_ESTIMATED", f"Bolt circle not given; placed at {d.bolt_pcd_mm:.1f} mm. Confirm it.")

    if spec.drawing_od_mm is not None:
        if abs(spec.drawing_od_mm - d.outside_dia_mm) > OD_TOLERANCE_MM:
            implied = implied_pitch_mm(spec.drawing_od_mm, spec.teeth)
            is_standard = any(abs(pitch - implied) <= STANDARD_PITCH_TOL_MM for pitch, _ in CHAIN_TABLE.values())
            hint = (
                "This is not a standard chain pitch; use a custom rotational_flange with explicitly dimensioned "
                "radial_cutout_pattern features instead."
                if not is_standard
                else "Check the tooth count and chain designation."
            )
            error(
                "OD_MISMATCH",
                f"Drawing outside diameter {spec.drawing_od_mm:.1f} mm does not match "
                f"{d.outside_dia_mm:.1f} mm for {spec.teeth} teeth on {spec.chain}. "
                f"The drawing implies a {implied:.2f} mm pitch. {hint}",
            )
    if spec.drawing_pd_mm is not None and abs(spec.drawing_pd_mm - d.pitch_dia_mm) > PD_TOLERANCE_MM:
        error(
            "PD_MISMATCH",
            f"Drawing pitch diameter {spec.drawing_pd_mm:.1f} mm does not match "
            f"{d.pitch_dia_mm:.1f} mm for {spec.teeth} teeth on {spec.chain}.",
        )

    for name in ("chain", "teeth"):
        if spec.sources.get(name, Source.ANNOTATED) is Source.ESTIMATED:
            warning("ESTIMATED_VALUE", f"{name} was estimated; verify it against the source drawing before export.")
    return issues
