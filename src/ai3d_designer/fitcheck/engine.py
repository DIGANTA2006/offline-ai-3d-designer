"""
Fit check engine for verifying component clearances inside enclosures.
"""

from typing import List, Optional
from math import hypot, isfinite

from ai3d_designer.core.spec.models import (
    ComponentSpec,
    EnclosureSpec,
    FitCheckResult,
    FitCheckReport,
)


class FitCheckEngine:
    """Engine for checking component fit inside enclosures."""

    DEFAULT_CLEARANCE_MM = 1.0  # Minimum recommended clearance in mm

    def __init__(self, default_clearance_mm: float = DEFAULT_CLEARANCE_MM):
        if not isfinite(default_clearance_mm) or default_clearance_mm < 0:
            raise ValueError("default_clearance_mm must be finite and non-negative")
        self.default_clearance_mm = float(default_clearance_mm)

    def check_component_fit(
        self,
        component: ComponentSpec,
        enclosure: EnclosureSpec,
        clearance_mm: Optional[float] = None,
    ) -> FitCheckResult:
        """
        Check if a single component fits inside an enclosure with required clearance.

        Args:
            component: The component to check
            enclosure: The enclosure to check against
            clearance_mm: Required clearance in mm (uses default if not specified)

        Returns:
            FitCheckResult with fit status, clearances, and any issues
        """
        if clearance_mm is None:
            clearance_mm = self.default_clearance_mm
        if not isfinite(clearance_mm) or clearance_mm < 0:
            raise ValueError("clearance_mm must be finite and non-negative")

        # Calculate available space (interior minus clearance on each side)
        available_width = enclosure.interior_width - (2 * clearance_mm)
        available_depth = enclosure.interior_depth - (2 * clearance_mm)
        available_height = enclosure.interior_height - (2 * clearance_mm)

        # Calculate clearances (positive = fits with margin, negative = doesn't fit)
        clearance_x = available_width - component.width
        clearance_y = available_depth - component.depth
        clearance_z = available_height - component.height

        # Calculate shortfalls (positive = how much it exceeds)
        shortfall_x = max(0.0, component.width - available_width)
        shortfall_y = max(0.0, component.depth - available_depth)
        shortfall_z = max(0.0, component.height - available_height)

        dimension_fit = shortfall_x == 0 and shortfall_y == 0 and shortfall_z == 0
        fits = dimension_fit

        issues = []
        warnings = []

        if not fits:
            if shortfall_x > 0:
                issues.append(
                    f"Component width ({component.width:.1f} mm) exceeds available width "
                    f"({available_width:.1f} mm) by {shortfall_x:.1f} mm"
                )
            if shortfall_y > 0:
                issues.append(
                    f"Component depth ({component.depth:.1f} mm) exceeds available depth "
                    f"({available_depth:.1f} mm) by {shortfall_y:.1f} mm"
                )
            if shortfall_z > 0:
                issues.append(
                    f"Component height ({component.height:.1f} mm) exceeds available height "
                    f"({available_height:.1f} mm) by {shortfall_z:.1f} mm"
                )
        else:
            # Check for tight fits (clearance less than 2x recommended)
            min_clearance = min(clearance_x, clearance_y, clearance_z)
            if min_clearance < 2 * clearance_mm:
                warnings.append(
                    f"Tight fit: minimum clearance is {min_clearance:.1f} mm "
                    f"(recommended: {2 * clearance_mm:.1f} mm)"
                )

        # Component mounting-hole coordinates are component-local: X follows depth and
        # Y follows width. Enclosure boss coordinates use the outer enclosure origin.
        # Compare them after assuming the component is centred within the interior.
        if component.mounting_holes and enclosure.mounting_bosses and dimension_fit:
            mounting_issues: list[str] = []

            def normalise_points(points: List[List[float]]) -> Optional[list[tuple[float, float]]]:
                normalised: list[tuple[float, float]] = []
                for point in points:
                    if not isinstance(point, (list, tuple)) or len(point) < 2:
                        return None
                    try:
                        x, y = float(point[0]), float(point[1])
                    except (TypeError, ValueError):
                        return None
                    if not isfinite(x) or not isfinite(y):
                        return None
                    normalised.append((x, y))
                return normalised

            holes = normalise_points(component.mounting_holes)
            bosses = normalise_points(enclosure.mounting_bosses)
            if holes is None or bosses is None:
                mounting_issues.append(
                    "Mounting-hole and boss coordinates must contain finite X/Y values."
                )
            elif len(holes) != len(bosses):
                mounting_issues.append(
                    f"Mounting pattern mismatch: component has {len(holes)} hole(s), "
                    f"but enclosure has {len(bosses)} boss(es)."
                )
            else:
                offset_x = enclosure.wall_thickness + (
                    enclosure.interior_depth - component.depth
                ) / 2
                offset_y = enclosure.wall_thickness + (
                    enclosure.interior_width - component.width
                ) / 2
                unmatched_bosses = list(bosses)
                tolerance_mm = 0.5

                for hole_x, hole_y in holes:
                    expected_x = offset_x + hole_x
                    expected_y = offset_y + hole_y
                    if not unmatched_bosses:
                        mounting_issues.append(
                            f"Mounting hole at ({hole_x:.2f}, {hole_y:.2f}) mm has no matching boss."
                        )
                        continue

                    nearest_index = min(
                        range(len(unmatched_bosses)),
                        key=lambda index: hypot(
                            unmatched_bosses[index][0] - expected_x,
                            unmatched_bosses[index][1] - expected_y,
                        ),
                    )
                    actual_x, actual_y = unmatched_bosses[nearest_index]
                    distance = hypot(actual_x - expected_x, actual_y - expected_y)
                    if distance > tolerance_mm:
                        mounting_issues.append(
                            f"Mounting hole at ({hole_x:.2f}, {hole_y:.2f}) mm does not align "
                            f"with an enclosure boss within {tolerance_mm:.2f} mm."
                        )
                    else:
                        unmatched_bosses.pop(nearest_index)

                if unmatched_bosses:
                    mounting_issues.append(
                        f"{len(unmatched_bosses)} enclosure mounting boss(es) do not match a hole."
                    )

            if mounting_issues:
                issues.extend(mounting_issues)
                fits = False
        elif component.mounting_holes and not enclosure.mounting_bosses:
            warnings.append(
                "Mounting-hole alignment was not checked because no enclosure mounting bosses were supplied."
            )
        elif enclosure.mounting_bosses and not component.mounting_holes:
            warnings.append(
                "Mounting-boss alignment was not checked because the component has no mounting-hole coordinates."
            )

        return FitCheckResult(
            component_id=component.id,
            component_name=component.name,
            fits=fits,
            clearance_mm={"x": clearance_x, "y": clearance_y, "z": clearance_z},
            shortfall_mm={"x": shortfall_x, "y": shortfall_y, "z": shortfall_z},
            issues=issues,
            warnings=warnings,
            suggested_clearance_mm=clearance_mm,
        )

    def check_all_components(
        self,
        components: List[ComponentSpec],
        enclosure: EnclosureSpec,
        clearance_mm: Optional[float] = None,
    ) -> FitCheckReport:
        """
        Check fit for all components in an enclosure.

        Args:
            components: List of components to check
            enclosure: The enclosure to check against
            clearance_mm: Required clearance in mm

        Returns:
            FitCheckReport with results for all components
        """
        effective_clearance = (
            self.default_clearance_mm if clearance_mm is None else clearance_mm
        )
        if not isfinite(effective_clearance) or effective_clearance < 0:
            raise ValueError("clearance_mm must be finite and non-negative")

        results = []
        overall_fit = bool(components)

        for component in components:
            result = self.check_component_fit(component, enclosure, effective_clearance)
            results.append(result)
            if not result.fits:
                overall_fit = False

        # An empty list is not evidence that an enclosure is suitable.
        if not components:
            summary = "No components were supplied; fit could not be verified."
        elif overall_fit:
            summary = (
                f"All {len(components)} component(s) fit in enclosure '{enclosure.name}' "
                f"with {effective_clearance:.1f} mm clearance."
            )
        else:
            failed = [r for r in results if not r.fits]
            summary = (
                f"{len(failed)} of {len(components)} component(s) do not fit in "
                f"enclosure '{enclosure.name}'. See details for shortfalls."
            )

        return FitCheckReport(
            enclosure_id=enclosure.id,
            enclosure_name=enclosure.name,
            overall_fit=overall_fit,
            results=results,
            summary=summary,
        )


def check_fit(
    components: List[ComponentSpec],
    enclosure: EnclosureSpec,
    clearance_mm: float = 1.0,
) -> FitCheckReport:
    """Convenience function to check component fit."""
    engine = FitCheckEngine(default_clearance_mm=clearance_mm)
    return engine.check_all_components(components, enclosure, clearance_mm)
