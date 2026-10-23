"""
Geometry engine using build123d for CAD operations.
Converts PartSpec to build123d Part objects.
"""

from typing import Optional, List, Dict, Any
import math
from build123d import (
    Part, Box, Cylinder, Sphere, Cone, Torus, Wedge,
    Pos, Rot, Location, Vector, Axis,
    extrude, revolve, loft, sweep,
    Compound, Solid, Face, Edge, Wire,
    export_step, export_stl,
)
from build123d.topology import Shape

from ..spec.models import (
    PartSpec, FeatureSpec, PrimitiveType, OperationType, UnitSystem, ParameterSpec
)


class GeometryEngine:
    """Converts PartSpec to build123d geometry."""
    
    # Unit conversion factors to mm
    UNIT_FACTORS = {
        UnitSystem.MM: 1.0,
        UnitSystem.CM: 10.0,
        UnitSystem.INCH: 25.4,
        UnitSystem.M: 1000.0,
    }
    
    def __init__(self, unit_system: UnitSystem = UnitSystem.MM):
        self.unit_system = unit_system
        self.unit_factor = self.UNIT_FACTORS[unit_system]
    
    def _convert(self, value: float) -> float:
        """Convert value from unit_system to mm (build123d native)."""
        return value * self.unit_factor
    
    def _convert_vec(self, vec: List[float]) -> Vector:
        """Convert a position expressed in millimeters to a build123d Vector.

        Feature positions are defined in millimeters by the PartSpec/NLP contract;
        only individual dimensional parameters carry their own unit metadata.
        """
        if len(vec) != 3 or any(not math.isfinite(float(value)) for value in vec):
            raise ValueError("Feature position must contain three finite millimeter values.")
        return Vector(*[float(value) for value in vec])
    
    def _create_primitive(self, feature: FeatureSpec) -> Shape:
        """Create a primitive shape from feature spec."""
        params = {key: parameter.to_mm() for key, parameter in feature.parameters.items()}
        for key, value in params.items():
            if not math.isfinite(value):
                raise ValueError(f"Parameter '{key}' must be a finite number.")

        required = {
            PrimitiveType.BOX: ("width", "depth", "height"),
            PrimitiveType.CYLINDER: ("radius", "height"),
            PrimitiveType.SPHERE: ("radius",),
            PrimitiveType.CONE: ("radius_bottom", "radius_top", "height"),
            PrimitiveType.TORUS: ("major_radius", "minor_radius"),
            PrimitiveType.WEDGE: ("width", "depth", "height"),
            PrimitiveType.EXTRUSION: ("height",),
            PrimitiveType.REVOLUTION: (),
        }
        missing = [key for key in required.get(feature.type, ()) if key not in params]
        if missing:
            raise ValueError(
                f"Feature '{feature.name or feature.id}' is missing required parameter(s): "
                + ", ".join(missing)
            )
        for key in required.get(feature.type, ()):
            value = params[key]
            allow_zero = feature.type == PrimitiveType.CONE and key == "radius_top"
            if value < 0 or (value == 0 and not allow_zero):
                requirement = "non-negative" if allow_zero else "positive"
                raise ValueError(f"Parameter '{key}' must be {requirement}.")

        match feature.type:
            case PrimitiveType.BOX:
                return Box(
                    params.get("width", 10),
                    params.get("depth", 10),
                    params.get("height", 10)
                )
            case PrimitiveType.CYLINDER:
                return Cylinder(
                    params.get("radius", 5),
                    params.get("height", 10)
                )
            case PrimitiveType.SPHERE:
                return Sphere(params.get("radius", 5))
            case PrimitiveType.CONE:
                return Cone(
                    params.get("radius_bottom", 5),
                    params.get("radius_top", 0),
                    params.get("height", 10)
                )
            case PrimitiveType.TORUS:
                return Torus(
                    params.get("major_radius", 10),
                    params.get("minor_radius", 3)
                )
            case PrimitiveType.WEDGE:
                return Wedge(
                    params.get("width", 10),
                    params.get("depth", 10),
                    params.get("height", 10),
                    params.get("xmin", 0),
                    params.get("zmin", 0),
                    params.get("xmax", 10),
                    params.get("zmax", 10),
                )
            case PrimitiveType.EXTRUSION:
                profile = self._validated_profile(feature, "xy")
                face = Face(Wire.make_polygon(profile, close=True))
                return extrude(face, amount=params["height"])
            case PrimitiveType.REVOLUTION:
                profile = self._validated_profile(feature, "rz")
                face = Face(Wire.make_polygon(profile, close=True))
                return revolve(face, axis=Axis.Z, revolution_arc=360)
            case PrimitiveType.LOFT:
                raise NotImplementedError("Loft requires multiple profiles")
            case PrimitiveType.SWEEP:
                raise NotImplementedError("Sweep requires path and profile")
            case _:
                raise ValueError(f"Unknown primitive type: {feature.type}")
    
    @staticmethod
    def _validated_profile(feature: FeatureSpec, plane: str) -> List[Vector]:
        """Read a simple polygon profile; profile coordinates are millimetres.

        XY profiles are used for extrusion ([x, y]); RZ profiles are
        [radius, z] coordinates revolved around the Z axis. Curved edges, holes,
        splines and multi-loop profiles are not inferred.
        """
        raw = feature.metadata.get("profile")
        if not isinstance(raw, list) or len(raw) < 3:
            raise ValueError(
                f"{feature.type.value} requires metadata.profile with at least three [x, y] points in mm."
            )

        points: List[tuple[float, float]] = []
        for index, item in enumerate(raw):
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise ValueError(f"Profile point {index + 1} must contain exactly two coordinates.")
            try:
                x, y = float(item[0]), float(item[1])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Profile point {index + 1} has non-numeric coordinates.") from exc
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError(f"Profile point {index + 1} must contain finite coordinates.")
            points.append((x, y))

        if len(points) > 3 and points[-1] == points[0]:
            points.pop()
        if len(set(points)) < 3:
            raise ValueError("Profile needs at least three distinct points.")
        if plane == "rz":
            if any(radius < 0 for radius, _ in points):
                raise ValueError("Revolution profile radii cannot be negative.")
            if not any(radius > 0 for radius, _ in points):
                raise ValueError("Revolution profile must enclose a nonzero radius.")

        def orient(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> float:
            return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])

        def on_segment(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> bool:
            eps = 1e-9
            return (min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps
                    and min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps)

        def intersects(a: tuple[float, float], b: tuple[float, float],
                       d: tuple[float, float], e: tuple[float, float]) -> bool:
            o1, o2 = orient(a, b, d), orient(a, b, e)
            o3, o4 = orient(d, e, a), orient(d, e, b)
            eps = 1e-9
            if ((o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps)) and (
                (o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps)
            ):
                return True
            return ((abs(o1) <= eps and on_segment(a, b, d))
                    or (abs(o2) <= eps and on_segment(a, b, e))
                    or (abs(o3) <= eps and on_segment(d, e, a))
                    or (abs(o4) <= eps and on_segment(d, e, b)))

        count = len(points)
        for i in range(count):
            a, b = points[i], points[(i + 1) % count]
            if a == b:
                raise ValueError("Profile contains a zero-length edge.")
            for j in range(i + 1, count):
                if j == (i + 1) % count or i == (j + 1) % count:
                    continue
                d, e = points[j], points[(j + 1) % count]
                if intersects(a, b, d, e):
                    raise ValueError("Profile self-intersects; provide a simple non-crossing polygon.")

        area_twice = sum(
            points[i][0] * points[(i + 1) % count][1]
            - points[(i + 1) % count][0] * points[i][1]
            for i in range(count)
        )
        if not math.isfinite(area_twice) or abs(area_twice) <= 1e-9:
            raise ValueError("Profile polygon has zero area.")

        if plane == "xy":
            return [Vector(x, y, 0.0) for x, y in points]
        if plane == "rz":
            return [Vector(radius, 0.0, z) for radius, z in points]
        raise ValueError(f"Unsupported profile plane: {plane}")

    def _apply_transform(self, shape: Shape, feature: FeatureSpec) -> Shape:
        """Apply position and rotation to shape."""
        pos = self._convert_vec(feature.position)
        rot = feature.rotation
        
        # Apply rotation then translation using Pos and Rot
        if any(r != 0 for r in rot):
            transform = Pos(pos.X, pos.Y, pos.Z) * Rot(rot[0], rot[1], rot[2])
        else:
            transform = Pos(pos.X, pos.Y, pos.Z)
        
        return shape.move(Location(transform))
    
    def create_part(self, spec: PartSpec) -> Part:
        """Build geometry in the explicit feature-history order of the PartSpec."""
        if not spec.features:
            raise ValueError("No features in specification")

        # Feature order is significant for sequential boolean history; do not reorder
        # by parent_id because that would silently change the meaning of operations.
        ordered_features = list(spec.features)
        result: Optional[Part] = None

        for index, feature in enumerate(ordered_features):
            if index == 0 and feature.operation != OperationType.UNION:
                raise ValueError("The first feature must use the union operation to define a base solid.")

            shape = self._create_primitive(feature)
            shape = self._apply_transform(shape, feature)
            part = Part(shape)

            if result is None:
                result = part
            elif feature.operation == OperationType.UNION:
                result = result + part
            elif feature.operation == OperationType.DIFFERENCE:
                result = result - part
            elif feature.operation == OperationType.INTERSECTION:
                result = result & part
            else:
                raise ValueError(f"Unsupported boolean operation: {feature.operation}")

            # A failed/empty boolean must stop the pipeline before exports can be
            # reported as successful. Multiple solids remain valid for assemblies.
            try:
                volume = float(result.volume)
            except Exception as exc:
                raise ValueError(f"Could not evaluate the result after feature '{feature.id}'.") from exc
            if not math.isfinite(volume) or volume <= 1e-9:
                raise ValueError(
                    f"Feature '{feature.name or feature.id}' produced empty or invalid geometry. "
                    "Check feature order, placement, and boolean overlap."
                )

            validity = getattr(result, "is_valid", None)
            try:
                is_valid = validity() if callable(validity) else validity
            except Exception as exc:
                raise ValueError(f"Could not validate geometry after feature '{feature.id}'.") from exc
            if is_valid is False:
                raise ValueError(
                    f"Feature '{feature.name or feature.id}' produced an invalid solid. "
                    "Adjust dimensions or feature placement."
                )

        if result is None:
            raise ValueError("Failed to create part from specification.")
        return result

    def _topological_sort(self, features: List[FeatureSpec]) -> List[FeatureSpec]:
        """Return feature history in input order; boolean order is semantically significant."""
        return list(features)


def create_part_from_spec(spec: PartSpec) -> Part:
    """Convenience function to create part from spec."""
    engine = GeometryEngine(spec.unit_system)
    return engine.create_part(spec)
