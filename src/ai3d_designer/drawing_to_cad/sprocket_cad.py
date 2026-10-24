"""Deterministic build123d standard chain-sprocket builder and post-build verifier."""
from __future__ import annotations

import math
from pathlib import Path

from build123d import BuildPart, Cylinder, Mode, PolarLocations, export_step, export_stl

from ai3d_designer.drawing_to_cad.sprocket_spec import (
    Issue, SprocketSpec, Severity, axis_extent_bounds_mm, derive, has_errors, validate,
)

BBOX_TOLERANCE_MM = 0.3
THICKNESS_TOLERANCE_MM = 0.05


class ExportBlocked(Exception):
    def __init__(self, issues: list[Issue]):
        self.issues = issues
        errors = [issue.message for issue in issues if issue.severity is Severity.ERROR]
        super().__init__("; ".join(errors) or "Sprocket export was blocked.")


def build_sprocket(spec: SprocketSpec):
    """Return one build123d Part. Validate the spec before calling this function."""
    d = derive(spec)
    with BuildPart() as part:
        Cylinder(radius=d.outside_dia_mm / 2, height=spec.thickness_mm)
        # A circular seat-cut pattern is a preview approximation, not the full ISO tooth form.
        with PolarLocations(d.pitch_dia_mm / 2, spec.teeth):
            Cylinder(radius=d.seat_radius_mm, height=spec.thickness_mm, mode=Mode.SUBTRACT)
        if spec.bore_mm is not None:
            Cylinder(radius=spec.bore_mm / 2, height=spec.thickness_mm, mode=Mode.SUBTRACT)
        if spec.bolt_count:
            assert d.bolt_pcd_mm is not None
            with PolarLocations(d.bolt_pcd_mm / 2, spec.bolt_count):
                Cylinder(
                    radius=spec.bolt_hole_dia_mm / 2,
                    height=spec.thickness_mm,
                    mode=Mode.SUBTRACT,
                )
    return part.part


def verify(part, spec: SprocketSpec) -> list[Issue]:
    """Post-build checks. Any ERROR means STEP/STL must not be exported."""
    d = derive(spec)
    issues: list[Issue] = []

    def error(code: str, message: str) -> None:
        issues.append(Issue(Severity.ERROR, code, message))

    if not part.is_valid:
        error("INVALID_SOLID", "Generated solid failed the OpenCascade validity check.")
        return issues

    solids = list(part.solids())
    if len(solids) != 1:
        error("SOLID_COUNT", f"Expected one contiguous solid; generated {len(solids)} solids.")
        return issues

    size = part.bounding_box().size
    lo, hi = axis_extent_bounds_mm(d)
    for axis, extent in (("X", size.X), ("Y", size.Y)):
        half_extent = extent / 2
        if not (lo - BBOX_TOLERANCE_MM <= half_extent <= hi + BBOX_TOLERANCE_MM):
            error(
                "BBOX_DIAMETER",
                f"{axis} extent {extent:.3f} mm is outside the computed range "
                f"{2 * lo:.3f}-{2 * hi:.3f} mm.",
            )
    if abs(size.Z - spec.thickness_mm) > THICKNESS_TOLERANCE_MM:
        error(
            "BBOX_THICKNESS",
            f"Thickness {size.Z:.3f} mm differs from {spec.thickness_mm:.3f} mm by more than "
            f"{THICKNESS_TOLERANCE_MM:.2f} mm.",
        )

    disc_volume = math.pi * (d.outside_dia_mm / 2) ** 2 * spec.thickness_mm
    if not math.isfinite(float(part.volume)) or part.volume <= 0:
        error("EMPTY_SOLID", "Generated solid has no positive finite volume.")
    elif part.volume >= disc_volume:
        error("FEATURES_MISSING", "No material was removed. The sprocket tooth seats, bore or bolt holes are missing.")
    return issues


def export_sprocket(spec: SprocketSpec, out_dir: str | Path, stem: str = "sprocket") -> list[Issue]:
    """Validate, build, verify, then export STEP/STL. No export occurs when checks fail."""
    pre = validate(spec)
    if has_errors(pre):
        raise ExportBlocked(pre)
    part = build_sprocket(spec)
    post = verify(part, spec)
    if has_errors(post):
        raise ExportBlocked(pre + post)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    step_path, stl_path = out / f"{stem}.step", out / f"{stem}.stl"
    export_step(part, str(step_path))
    export_stl(part, str(stl_path))
    for path in (step_path, stl_path):
        if not path.is_file() or path.stat().st_size < 100:
            raise RuntimeError(f"{path.suffix.upper()} exporter produced an empty file.")
    return [issue for issue in pre + post if issue.severity is Severity.WARNING]
