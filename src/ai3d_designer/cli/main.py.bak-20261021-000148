"""
Command-line interface for the AI 3D Designer.
Updated to use new core module structure.
"""

import argparse
import sys
import os
import re
from pathlib import Path
from typing import Optional

# Import from new core structure
from ai3d_designer.core.spec.models import PartSpec, FeatureSpec, PrimitiveType, OperationType, UnitSystem, ParameterSpec
from ai3d_designer.core.geometry.engine import create_part_from_spec
from ai3d_designer.core.export.exporter import export_step, export_stl, validate_export


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
    
    # Optional hole
    if hole_diameter and hole_diameter > 0:
        hole_feature = FeatureSpec(
            id="hole_center",
            type=PrimitiveType.CYLINDER,
            name="center_hole",
            parameters={
                "radius": ParameterSpec(name="radius", value=hole_diameter / 2),
                "height": ParameterSpec(name="height", value=height + 2),  # Slightly taller for clean cut
            },
            position=[width/2, depth/2, -1],  # Centered, slightly below bottom
            operation=OperationType.DIFFERENCE,
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
    This is a simplified version - in production would use LLM.
    """
    text_lower = text.lower()
    
    # Check for cylinder
    if "cylinder" in text_lower:
        # Extract radius and height
        radius_match = re.search(r'radius\s*[=:]?\s*(\d+(?:\.\d+)?)', text_lower)
        height_match = re.search(r'height\s*[=:]?\s*(\d+(?:\.\d+)?)', text_lower)
        # Alternative: "cylinder 10x50" or "cylinder radius 10 height 50"
        if not radius_match:
            dims = re.findall(r'(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)', text)
            if dims and len(dims[0]) == 2:
                radius, height = map(float, dims[0])
            else:
                radius, height = 10, 50  # defaults
        else:
            radius = float(radius_match.group(1))
            height = float(height_match.group(1)) if height_match else 50
        return create_cylinder_spec("cylinder", radius, height)
    
    # Check for sphere
    if "sphere" in text_lower:
        radius_match = re.search(r'radius\s*[=:]?\s*(\d+(?:\.\d+)?)', text_lower)
        if not radius_match:
            radius_match = re.search(r'sphere\s+(\d+(?:\.\d+)?)', text_lower)
        radius = float(radius_match.group(1)) if radius_match else 10
        return create_sphere_spec("sphere", radius)
    
    # Default to box
    # Extract dimensions
    dims = re.findall(r'(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)', text)
    if not dims:
        # Try alternative format with units
        dims = re.findall(r'(\d+(?:\.\d+)?)\s*(?:mm|cm|in)?\s*[x×]\s*(\d+(?:\.\d+)?)\s*(?:mm|cm|in)?\s*[x×]\s*(\d+(?:\.\d+)?)\s*(?:mm|cm|in)?', text)
    
    width, depth, height = 40, 20, 10  # defaults
    if dims:
        width, depth, height = map(float, dims[0])
    
    # Check for hole - multiple patterns
    hole_diameter = None
    # Pattern 1: "5mm hole" or "5 mm hole"
    hole_match = re.search(r'(\d+(?:\.\d+)?)\s*mm\s*hole', text_lower)
    if not hole_match:
        # Pattern 2: "hole 5mm" or "hole 5 mm"
        hole_match = re.search(r'hole\s*(\d+(?:\.\d+)?)\s*mm', text_lower)
    if not hole_match:
        # Pattern 3: "with a 5mm hole"
        hole_match = re.search(r'with\s+a\s+(\d+(?:\.\d+)?)\s*mm\s*hole', text_lower)
    if hole_match:
        hole_diameter = float(hole_match.group(1))
    
    name = "box"
    
    return create_box_spec(name, width, depth, height, hole_diameter)


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
    
    spec = create_part_from_text(args.prompt)
    
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
    
    formats = [f.strip().lower() for f in args.format.split(",")]
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
