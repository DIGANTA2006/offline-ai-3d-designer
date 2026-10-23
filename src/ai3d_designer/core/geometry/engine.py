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
                # Requires a profile face - handled separately
                raise NotImplementedError("Extrusion requires profile face")
            case PrimitiveType.REVOLUTION:
                raise NotImplementedError("Revolution requires profile face")
            case PrimitiveType.LOFT:
                raise NotImplementedError("Loft requires multiple profiles")
            case PrimitiveType.SWEEP:
                raise NotImplementedError("Sweep requires path and profile")
            case _:
                raise ValueError(f"Unknown primitive type: {feature.type}")
    
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
