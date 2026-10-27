"""
Fit check engine for verifying component clearances inside enclosures.
"""

from typing import List, Optional
from math import isfinite

from ai3d_designer.core.spec.models import (
    ComponentSpec,
    EnclosureSpec,
    FitCheckResult,
    FitCheckReport,
    ParameterSource,
)


class FitCheckEngine:
    """Engine for checking component fit inside enclosures."""

    DEFAULT_CLEARANCE_MM = 1.0  # Minimum recommended clearance in mm

    def __init__(self, default_clearance_mm: float = DEFAULT_CLEARANCE_MM):
        self.default_clearance_mm = default_clearance_mm

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

        fits = shortfall_x == 0 and shortfall_y == 0 and shortfall_z == 0

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

        # Check mounting holes if present
        if component.mounting_holes and enclosure.mounting_bosses:
            # Simple check: verify mounting holes align with bosses
            # This is a simplified check - real implementation would be more sophisticated
            pass

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
        results = []
        overall_fit = True

        for component in components:
            result = self.check_component_fit(component, enclosure, clearance_mm)
            results.append(result)
            if not result.fits:
                overall_fit = False

        # Generate summary
        if overall_fit:
            summary = f"All {len(components)} component(s) fit in enclosure '{enclosure.name}' with {clearance_mm or self.default_clearance_mm:.1f} mm clearance."
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
