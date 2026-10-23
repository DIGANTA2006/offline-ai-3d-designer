"""
Reliable build123d geometry generation from a validated PartSpec.

Coordinates:
- Primitive dimensions are converted to millimeters per ParameterSpec.unit.
- If a parameter unit was omitted, PartSpec.unit_system is used for backward compatibility.
- Feature positions are always expressed in millimeters; rotations are Euler degrees (XYZ).
- Polygon profiles are provided in metadata and inherit PartSpec.unit_system unless metadata.unit is set.
"""
from __future__ import annotations

from math import isfinite
from typing import Any, List, Optional

from build123d import (
    Axis, Box, Cone, Cylinder, Face, Location, Part, Pos, Rot, Sphere,
    Torus, Vector, Wedge, Wire, extrude, loft, revolve, sweep,
)
from build123d.topology import Shape

from ..spec.models import FeatureSpec, OperationType, PartSpec, PrimitiveType, UnitSystem


class GeometryEngine:
    """Create build123d shapes from explicit feature specifications."""

    UNIT_FACTORS = {
        UnitSystem.MM: 1.0,
        UnitSystem.CM: 10.0,
        UnitSystem.INCH: 25.4,
        UnitSystem.M: 1000.0,
    }

    REQUIRED_PARAMETERS = {
        PrimitiveType.BOX: ("width", "depth", "height"),
        PrimitiveType.CYLINDER: ("radius", "height"),
        PrimitiveType.SPHERE: ("radius",),
        PrimitiveType.CONE: ("radius_bottom", "radius_top", "height"),
        PrimitiveType.TORUS: ("major_radius", "minor_radius"),
        PrimitiveType.WEDGE: ("width", "depth", "height"),
    }

    def __init__(self, unit_system: UnitSystem = UnitSystem.MM):
        self.unit_system = UnitSystem(unit_system)
        self.unit_factor = self.UNIT_FACTORS[self.unit_system]

    def _convert(self, value: float) -> float:
        """Convert a dimension in the specification's default unit to mm."""
        return float(value) * self.unit_factor

    @staticmethod
    def _check_finite(value: float, label: str) -> float:
        number = float(value)
        if not isfinite(number):
            raise ValueError(f"{label} must be a finite number.")
        return number

    def _length_parameter(
        self,
        feature: FeatureSpec,
        name: str,
        *,
        default: Optional[float] = None,
    ) -> float:
        """Read a length parameter in mm, respecting explicit per-parameter units."""
        parameter = feature.parameters.get(name)
        if parameter is None:
            if default is None:
                raise ValueError(
                    f"Feature '{feature.name or feature.id}' ({feature.type.value}) "
                    f"is missing required parameter '{name}'."
                )
            return self._check_finite(default, f"{feature.id}.{name}")

        value = self._check_finite(parameter.value, f"{feature.id}.{name}")
        # Pydantic records explicitly provided fields. An omitted unit means the
        # historical behavior: inherit PartSpec unit. Explicit units always win.
        if "unit" in parameter.model_fields_set:
            return self._check_finite(parameter.to_mm(), f"{feature.id}.{name}")
        return self._convert(value)

    def _profile_wire(
        self,
        profile: Any,
        *,
        default_unit: UnitSystem,
        close: bool = True,
        label: str = "profile",
        plane: str = "xy",
    ) -> Wire:
        """Build a polygon wire from [[x, y], ...] or [[x, y, z], ...] metadata."""
        profile_unit = default_unit
        points: Any = profile
        offset = [0.0, 0.0, 0.0]
        if isinstance(profile, dict):
            points = profile.get("points")
            unit_value = profile.get("unit")
            if unit_value is not None:
                try:
                    profile_unit = UnitSystem(unit_value)
                except ValueError as exc:
                    raise ValueError(f"{label}.unit must be one of mm, cm, in, m.") from exc
            if profile.get("offset") is not None:
                offset_value = profile["offset"]
                if not isinstance(offset_value, (list, tuple)) or len(offset_value) != 3:
                    raise ValueError(f"{label}.offset must contain three coordinates.")
                offset = [self._check_finite(v, f"{label}.offset") for v in offset_value]
            elif profile.get("z") is not None:
                offset[2] = self._check_finite(profile["z"], f"{label}.z")

        if plane not in {"xy", "xz"}:
            raise ValueError("Profile plane must be 'xy' or 'xz'.")
        if not isinstance(points, list):
            raise ValueError(f"{label} must be a list of polygon points or an object with a points list.")
        minimum = 3 if close else 2
        if len(points) < minimum:
            raise ValueError(f"{label} needs at least {minimum} points.")

        factor = self.UNIT_FACTORS[profile_unit]
        vectors: list[Vector] = []
        for index, point in enumerate(points):
            if not isinstance(point, (list, tuple)) or len(point) not in (2, 3):
                raise ValueError(f"{label}[{index}] must have two or three coordinates.")
            coords = [self._check_finite(v, f"{label}[{index}]") * factor for v in point]
            if len(coords) == 2 and plane == "xz":
                coords = [coords[0], 0.0, coords[1]]
            elif len(coords) == 2:
                coords.append(0.0)
            coords = [
                coords[axis] + offset[axis] * factor
                for axis in range(3)
            ]
            vectors.append(Vector(*coords))

        for left, right in zip(vectors, vectors[1:]):
            if (left - right).length < 1e-7:
                raise ValueError(f"{label} contains duplicate adjacent points.")
        if close and (vectors[0] - vectors[-1]).length < 1e-7:
            vectors.pop()
        if close and len(vectors) < 3:
            raise ValueError(f"{label} must contain at least three distinct points.")

        try:
            return Wire.make_polygon(vectors, close=close)
        except Exception as exc:
            raise ValueError(f"Could not construct {label}: {exc}") from exc

    def _create_primitive(self, feature: FeatureSpec) -> Shape:
        """Create one primitive/profile feature without applying its transform."""
        params: dict[str, float] = {}
        for name in self.REQUIRED_PARAMETERS.get(feature.type, ()):
            params[name] = self._length_parameter(feature, name)

        match feature.type:
            case PrimitiveType.BOX:
                return Box(params["width"], params["depth"], params["height"])
            case PrimitiveType.CYLINDER:
                return Cylinder(params["radius"], params["height"])
            case PrimitiveType.SPHERE:
                return Sphere(params["radius"])
            case PrimitiveType.CONE:
                if params["radius_bottom"] <= 0 or params["radius_top"] < 0:
                    raise ValueError("Cone radii must be non-negative and the bottom radius must be positive.")
                return Cone(params["radius_bottom"], params["radius_top"], params["height"])
            case PrimitiveType.TORUS:
                if params["major_radius"] <= 0 or params["minor_radius"] <= 0:
                    raise ValueError("Torus radii must be positive.")
                if params["minor_radius"] >= params["major_radius"]:
                    raise ValueError("Torus minor radius must be smaller than its major radius.")
                return Torus(params["major_radius"], params["minor_radius"])
            case PrimitiveType.WEDGE:
                width, depth, height = params["width"], params["depth"], params["height"]
                xmin = self._length_parameter(feature, "xmin", default=0.0)
                zmin = self._length_parameter(feature, "zmin", default=0.0)
                xmax = self._length_parameter(feature, "xmax", default=width)
                zmax = self._length_parameter(feature, "zmax", default=height)
                if not (0 <= xmin < xmax <= width and 0 <= zmin < zmax <= height):
                    raise ValueError("Wedge bounds must satisfy 0 <= xmin < xmax <= width and 0 <= zmin < zmax <= height.")
                return Wedge(width, depth, height, xmin, zmin, xmax, zmax)
            case PrimitiveType.EXTRUSION:
                profile = self._profile_wire(
                    feature.metadata.get("profile"), default_unit=self.unit_system,
                    label=f"{feature.id}.profile",
                )
                height = self._length_parameter(feature, "height")
                if height <= 0:
                    raise ValueError("Extrusion height must be positive.")
                return extrude(Face(profile), amount=height)
            case PrimitiveType.REVOLUTION:
                profile = self._profile_wire(
                    feature.metadata.get("profile"), default_unit=self.unit_system,
                    label=f"{feature.id}.profile", plane="xz",
                )
                angle = feature.parameters.get("angle")
                sweep_angle = 360.0 if angle is None else self._check_finite(angle.value, f"{feature.id}.angle")
                if not 0 < sweep_angle <= 360:
                    raise ValueError("Revolution angle must be greater than 0 and at most 360 degrees.")
                return revolve(Face(profile), axis=Axis.Z, revolution_arc=sweep_angle)
            case PrimitiveType.LOFT:
                profiles = feature.metadata.get("profiles")
                if not isinstance(profiles, list) or len(profiles) < 2:
                    raise ValueError("Loft requires metadata.profiles with at least two polygon profiles.")
                wires = [
                    self._profile_wire(profile, default_unit=self.unit_system, label=f"{feature.id}.profiles[{i}]")
                    for i, profile in enumerate(profiles)
                ]
                return loft(sections=wires)
            case PrimitiveType.SWEEP:
                profile = self._profile_wire(
                    feature.metadata.get("profile"), default_unit=self.unit_system,
                    label=f"{feature.id}.profile",
                )
                path = self._profile_wire(
                    feature.metadata.get("path"), default_unit=self.unit_system, close=False,
                    label=f"{feature.id}.path",
                )
                return sweep(sections=Face(profile), path=path)
            case _:
                raise ValueError(f"Unsupported primitive type: {feature.type}")

    def _apply_transform(self, shape: Shape, feature: FeatureSpec) -> Shape:
        """Apply millimeter translation and Euler-degree rotation to a feature."""
        if len(feature.position) != 3 or len(feature.rotation) != 3:
            raise ValueError(f"Feature '{feature.id}' must have three position and three rotation values.")
        pos = [self._check_finite(v, f"{feature.id}.position") for v in feature.position]
        rot = [self._check_finite(v, f"{feature.id}.rotation") for v in feature.rotation]
        # FeatureSpec position is defined in millimeters in the prompt; it must not
        # be multiplied by the part's dimensional unit factor.
        transform = Pos(*pos) * Rot(*rot) if any(rot) else Pos(*pos)
        return shape.move(Location(transform))

    def _topological_sort(self, features: List[FeatureSpec]) -> List[FeatureSpec]:
        """Stable topological ordering; rejects duplicate IDs, missing parents and cycles."""
        by_id: dict[str, FeatureSpec] = {}
        order: dict[str, int] = {}
        for index, feature in enumerate(features):
            if feature.id in by_id:
                raise ValueError(f"Duplicate feature id '{feature.id}'.")
            by_id[feature.id] = feature
            order[feature.id] = index

        children: dict[str, list[str]] = {feature.id: [] for feature in features}
        indegree = {feature.id: 0 for feature in features}
        for feature in features:
            if not feature.parent_id:
                continue
            if feature.parent_id not in by_id:
                raise ValueError(f"Feature '{feature.id}' references missing parent '{feature.parent_id}'.")
            if feature.parent_id == feature.id:
                raise ValueError(f"Feature '{feature.id}' cannot be its own parent.")
            children[feature.parent_id].append(feature.id)
            indegree[feature.id] += 1

        ready = sorted(
            (order[feature_id], feature_id)
            for feature_id, degree in indegree.items()
            if degree == 0
        )
        sorted_features: list[FeatureSpec] = []
        while ready:
            _, feature_id = ready.pop(0)
            sorted_features.append(by_id[feature_id])
            for child_id in sorted(children[feature_id], key=order.__getitem__):
                indegree[child_id] -= 1
                if indegree[child_id] == 0:
                    ready.append((order[child_id], child_id))
                    ready.sort()

        if len(sorted_features) != len(features):
            cyclic = [feature_id for feature_id, degree in indegree.items() if degree > 0]
            raise ValueError(f"Feature dependency cycle detected: {', '.join(cyclic)}.")
        return sorted_features

    def create_part(self, spec: PartSpec) -> Part:
        """Create a part and apply ordered boolean operations; fail on invalid inputs."""
        if not spec.features:
            raise ValueError("No features in specification.")
        spec_errors = spec.validate_spec()
        if spec_errors:
            raise ValueError("Invalid part specification: " + "; ".join(spec_errors))

        ordered_features = self._topological_sort(spec.features)
        result: Optional[Part] = None

        for feature in ordered_features:
            try:
                primitive = self._create_primitive(feature)
                transformed = self._apply_transform(primitive, feature)
                part = Part(transformed)

                if result is None:
                    if feature.operation != OperationType.UNION:
                        raise ValueError(f"First feature '{feature.id}' must use the 'union' operation.")
                    result = part
                elif feature.operation == OperationType.UNION:
                    result = result + part
                elif feature.operation == OperationType.DIFFERENCE:
                    result = result - part
                elif feature.operation == OperationType.INTERSECTION:
                    result = result & part
                else:
                    raise ValueError(f"Unsupported boolean operation: {feature.operation}")

                if result is None or not isfinite(float(result.volume)) or result.volume <= 1e-9:
                    raise ValueError("Boolean operation produced an empty or non-finite solid.")
            except Exception as exc:
                if isinstance(exc, ValueError) and str(exc).startswith("First feature"):
                    raise
                raise ValueError(
                    f"Feature '{feature.name or feature.id}' ({feature.type.value}) failed: {exc}"
                ) from exc

        if result is None:
            raise ValueError("Failed to create part from specification.")
        return result


def create_part_from_spec(spec: PartSpec) -> Part:
    """Create a part using the unit system and features in a PartSpec."""
    return GeometryEngine(spec.unit_system).create_part(spec)
