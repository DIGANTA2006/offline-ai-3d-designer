"""
Command-line interface for the AI 3D Designer.
Updated to use new core module structure.
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

# Import from new core structure
from ai3d_designer.core.spec.models import PartSpec, FeatureSpec, PrimitiveType, OperationType, UnitSystem, ParameterSpec
from ai3d_designer.core.geometry.engine import create_part_from_spec
from ai3d_designer.core.export.exporter import export_step, export_stl, validate_export
from ai3d_designer.core.nlp.parser import RuleBasedParser, parse_natural_language


def create_box_spec(name: str, width: float, depth: float, height: float, 
                    hole_diameter: Optional[float] = None) -> PartSpec:
    """Create a simple box specification, optionally with a hole."""
    spec = PartSpec(
        name=name,
        description=f"Box {width}x{depth}x{height}mm",
        unit_system=UnitSystem.MM,
    )
    
    # Main box
    box_feature = FeatureSpec(
        id="box_main",
        type=PrimitiveType.BOX,
        name="main_box",
        parameters={
            "width": ParameterSpec(name="width", value=width),
            "depth": ParameterSpec(name="depth", value=depth),
            "height": ParameterSpec(name="height", value=height),
        },
        operation=OperationType.UNION,
    )
    spec.add_feature(box_feature)
    
    # Optional centered through-hole; primitives are centered on the origin.
    if hole_diameter is not None:
        if hole_diameter <= 0 or hole_diameter >= min(width, depth):
            raise ValueError("A centered through-hole diameter must be positive and smaller than both box width and depth.")
        hole_feature = FeatureSpec(
            id="hole_center",
            type=PrimitiveType.CYLINDER,
            name="center_hole",
            parameters={
                "radius": ParameterSpec(name="radius", value=hole_diameter / 2),
                "height": ParameterSpec(name="height", value=height + 2),
            },
            position=[0.0, 0.0, 0.0],
            operation=OperationType.DIFFERENCE,
            parent_id=box_feature.id,
        )
        spec.add_feature(hole_feature)
    
    return spec


def create_cylinder_spec(name: str, radius: float, height: float) -> PartSpec:
    """Create a cylinder specification."""
    spec = PartSpec(
        name=name,
        description=f"Cylinder radius={radius} height={height}mm",
        unit_system=UnitSystem.MM,
    )
    
    cyl_feature = FeatureSpec(
        id="cylinder_main",
        type=PrimitiveType.CYLINDER,
        name="main_cylinder",
        parameters={
            "radius": ParameterSpec(name="radius", value=radius),
            "height": ParameterSpec(name="height", value=height),
        },
        operation=OperationType.UNION,
    )
    spec.add_feature(cyl_feature)
    
    return spec


def create_sphere_spec(name: str, radius: float) -> PartSpec:
    """Create a sphere specification."""
    spec = PartSpec(
        name=name,
        description=f"Sphere radius={radius}mm",
        unit_system=UnitSystem.MM,
    )
    
    sphere_feature = FeatureSpec(
        id="sphere_main",
        type=PrimitiveType.SPHERE,
        name="main_sphere",
        parameters={
            "radius": ParameterSpec(name="radius", value=radius),
        },
        operation=OperationType.UNION,
    )
    spec.add_feature(sphere_feature)
    
    return spec


def create_part_from_text(text: str) -> PartSpec:
    """
    Parse natural language text into a PartSpec.
    Uses the core RuleBasedParser for consistent parsing.
    """
    # Use the core parser
    result = parse_natural_language(text)
    
    if result.success:
        return result.spec
    
    # If parsing fails, raise an error instead of silently defaulting
    raise ValueError(f"Could not parse description: {result.error}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Offline AI 3D Designer - Generate CAD from natural language",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m ai3d_designer.cli "Create a 40x20x10mm box with a 5mm hole"
  python -m ai3d_designer.cli --output ./parts --format step,stl "50x30x20 box"
  python -m ai3d_designer.cli --validate-only "cylinder radius 10 height 50"
        """
    )
    
    parser.add_argument(
        "prompt",
        nargs="?",
        help="Natural language description of the part"
    )
    
    parser.add_argument(
        "-o", "--output",
        default="./output",
        help="Output directory (default: ./output)"
    )
    
    parser.add_argument(
        "-f", "--format",
        default="step,stl",
        help="Export formats: step, stl, or both (default: step,stl)"
    )
    
    parser.add_argument(
        "-n", "--name",
        default=None,
        help="Part name (default: auto-generated)"
    )
    
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate, don't export files"
    )
    
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip export validation"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    if not args.prompt:
        parser.print_help()
        return 1
    
    # Parse prompt into spec
    if args.verbose:
        print(f"Parsing: {args.prompt}")
    
    try:
        spec = create_part_from_text(args.prompt)
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    
    if args.name:
        spec.name = args.name
    
    if args.verbose:
        print(f"Part: {spec.name}")
        print(f"Features: {len(spec.features)}")
        for f in spec.features:
            print(f"  - {f.name} ({f.type.value})")
    
    # Validate spec
    spec_errors = spec.validate_spec()
    if spec_errors:
        print("Specification errors:")
        for err in spec_errors:
            print(f"  ERROR: {err}")
        return 1
    
    # Create geometry
    if args.verbose:
        print("Generating geometry...")
    
    try:
        part = create_part_from_spec(spec)
        if args.verbose:
            print(f"Volume: {part.volume:.2f} mm³")
            print(f"Bounding box: {part.bounding_box()}")
    except Exception as e:
        print(f"Geometry generation failed: {e}")
        return 1
    
    if args.validate_only:
        print("Validation only - skipping export")
        results = validate_export(part)
        for fmt, result in results.items():
            status = "PASS" if result.get("success") else "FAIL"
            print(f"  {fmt.upper()}: {status}")
            if result.get("errors"):
                for err in result["errors"]:
                    print(f"    ERROR: {err}")
            if result.get("warnings"):
                for warn in result["warnings"]:
                    print(f"    WARN: {warn}")
        return 0
    
    # Export
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    formats = [f.strip().lower() for f in args.format.split(",") if f.strip()]
    invalid_formats = sorted(set(formats) - {"step", "stl"})
    if not formats or invalid_formats:
        print(f"Unsupported export format(s): {', '.join(invalid_formats) if invalid_formats else '(none selected)'}. Choose step, stl, or both.")
        return 2
    validate = not args.no_validate
    
    for fmt in formats:
        if fmt == "step":
            file_path = output_dir / f"{spec.name}.step"
            result = export_step(part, str(file_path), validate=validate)
        elif fmt == "stl":
            file_path = output_dir / f"{spec.name}.stl"
            result = export_stl(part, str(file_path), validate=validate)
        else:
            print(f"Unknown format: {fmt}")
            continue
        
        if result.success:
            print(f"✓ Exported {result.format}: {result.file_path} ({result.file_size} bytes)")
            if result.warnings and args.verbose:
                for w in result.warnings:
                    print(f"  WARN: {w}")
        else:
            print(f"✗ Export {fmt.upper()} failed:")
            for err in result.validation_errors:
                print(f"  ERROR: {err}")
            return 1
    
    print(f"Done! Files saved to {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
