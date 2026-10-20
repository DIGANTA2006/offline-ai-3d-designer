"""
Geometry engine using build123d for CAD operations.
Converts PartSpec to build123d Part objects.
"""

from typing import Optional, List, Dict, Any
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
        """Convert list to build123d Vector in mm."""
        return Vector(*[self._convert(v) for v in vec])
    
    def _create_primitive(self, feature: FeatureSpec) -> Shape:
        """Create a primitive shape from feature spec."""
        params = {k: self._convert(v.value) for k, v in feature.parameters.items()}
        
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
        """Create a build123d Part from PartSpec."""
        if not spec.features:
            raise ValueError("No features in specification")
        
        # Sort features by dependency (parent before children)
        features_by_id = {f.id: f for f in spec.features}
        ordered_features = self._topological_sort(spec.features)
        
        parts: Dict[str, Part] = {}
        result: Optional[Part] = None
        
        for feature in ordered_features:
            # Create primitive
            shape = self._create_primitive(feature)
            
            # Apply transform
            shape = self._apply_transform(shape, feature)
            
            # Convert to Part
            part = Part(shape)
            parts[feature.id] = part
            
            # Apply boolean operation
            if feature.operation == OperationType.UNION:
                if result is None:
                    result = part
                else:
                    result += part
            elif feature.operation == OperationType.DIFFERENCE:
                if result is None:
                    result = part
                else:
                    result -= part
            elif feature.operation == OperationType.INTERSECTION:
                if result is None:
                    result = part
                else:
                    result &= part
        
        if result is None:
            raise ValueError("Failed to create part from features")
        
        return result
    
    def _topological_sort(self, features: List[FeatureSpec]) -> List[FeatureSpec]:
        """Sort features so parents come before children."""
        # Simple approach: features with no parent_id first, then by parent_id
        # For now, just return as-is since build123d handles operations sequentially
        return features


def create_part_from_spec(spec: PartSpec) -> Part:
    """Convenience function to create part from spec."""
    engine = GeometryEngine(spec.unit_system)
    return engine.create_part(spec)
