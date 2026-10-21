"""
NLP module for natural language to PartSpec conversion.
Uses local LLM (llama.cpp) for offline processing.
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from pathlib import Path

from ..spec.models import (
    PartSpec, FeatureSpec, ParameterSpec, PrimitiveType,
    OperationType, UnitSystem
)


@dataclass
class ParseResult:
    """Result of parsing natural language."""
    success: bool
    spec: Optional[PartSpec] = None
    error: Optional[str] = None
    raw_response: Optional[str] = None


class PromptTemplates:
    """Prompt templates for LLM interaction."""

    SYSTEM_PROMPT = """You are an expert mechanical engineer and CAD designer.
Convert natural language descriptions into precise PartSpec JSON for a 3D CAD system.

The PartSpec schema:
{
  "name": "string - descriptive part name",
  "description": "string - brief description",
  "unit_system": "mm|cm|in|m",
  "features": [
    {
      "id": "string - unique short ID",
      "type": "box|cylinder|sphere|cone|torus|wedge",
      "name": "string - feature name",
      "parameters": {
        "param_name": {"name": "string", "value": number, "unit": "mm|cm|in|m", "description": "string"}
      },
      "position": [x, y, z],
      "rotation": [rx, ry, rz],
      "operation": "union|difference|intersection",
      "parent_id": "string|null"
    }
  ]
}

Rules:
1. Use ONLY the primitive types listed above
2. All dimensions in the specified unit_system
3. Position/rotation in mm
4. Operations: first feature is union, subsequent can be union/difference/intersection
5. For holes, use cylinder with difference operation
6. Output ONLY valid JSON, no extra text
7. Include all required parameters for each primitive type

Required parameters per type:
- box: width, depth, height
- cylinder: radius, height
- sphere: radius
- cone: radius_bottom, radius_top, height
- torus: major_radius, minor_radius
- wedge: width, depth, height, xmin, zmin, xmax, zmax"""

    USER_PROMPT_TEMPLATE = """Convert this description to PartSpec JSON:

{description}

Output JSON only:"""

    FEW_SHOT_EXAMPLES = [
        {
            "input": "A 50x30x10mm box with a 5mm diameter hole through the center",
            "output": {
                "name": "Box with Center Hole",
                "description": "Rectangular box with through hole",
                "unit_system": "mm",
                "features": [
                    {
                        "id": "base",
                        "type": "box",
                        "name": "Base Box",
                        "parameters": {
                            "width": {"name": "width", "value": 50, "unit": "mm", "description": "Box width"},
                            "depth": {"name": "depth", "value": 30, "unit": "mm", "description": "Box depth"},
                            "height": {"name": "height", "value": 10, "unit": "mm", "description": "Box height"}
                        },
                        "position": [0, 0, 0],
                        "rotation": [0, 0, 0],
                        "operation": "union",
                        "parent_id": None
                    },
                    {
                        "id": "hole",
                        "type": "cylinder",
                        "name": "Center Hole",
                        "parameters": {
                            "radius": {"name": "radius", "value": 2.5, "unit": "mm", "description": "Hole radius"},
                            "height": {"name": "height", "value": 12, "unit": "mm", "description": "Hole height (longer than box)"}
                        },
                        "position": [25, 15, -1],
                        "rotation": [0, 0, 0],
                        "operation": "difference",
                        "parent_id": "base"
                    }
                ]
            }
        },
        {
            "input": "A 20mm diameter cylinder, 50mm tall",
            "output": {
                "name": "Cylinder",
                "description": "Simple cylinder",
                "unit_system": "mm",
                "features": [
                    {
                        "id": "cyl",
                        "type": "cylinder",
                        "name": "Cylinder",
                        "parameters": {
                            "radius": {"name": "radius", "value": 10, "unit": "mm", "description": "Cylinder radius"},
                            "height": {"name": "height", "value": 50, "unit": "mm", "description": "Cylinder height"}
                        },
                        "position": [0, 0, 0],
                        "rotation": [0, 0, 0],
                        "operation": "union",
                        "parent_id": None
                    }
                ]
            }
        }
    ]


class NLPEngine:
    """Natural language to PartSpec converter using local LLM."""

    def __init__(self, model_path: Optional[str] = None, n_ctx: int = 4096, n_threads: int = 4):
        self.model_path = model_path or self._find_default_model()
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self._llm = None

    def _find_default_model(self) -> Optional[str]:
        """Find default model in vendor directory."""
        base = Path(__file__).parent.parent.parent.parent / "vendor" / "llama.cpp"
        if base.exists():
            # Look for .gguf files
            models = list(base.glob("*.gguf"))
            if models:
                return str(models[0])
        return None

    def _load_model(self):
        """Lazy load the llama.cpp model."""
        if self._llm is not None:
            return

        if not self.model_path or not os.path.exists(self.model_path):
            raise RuntimeError(
                f"Model not found at {self.model_path}. "
                "Please download a GGUF model to vendor/llama.cpp/"
            )

        try:
            from llama_cpp import Llama
            self._llm = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                verbose=False,
            )
        except ImportError:
            raise RuntimeError("llama-cpp-python not installed. Run: pip install llama-cpp-python")

    def parse(self, description: str, unit_system: UnitSystem = UnitSystem.MM) -> ParseResult:
        """Parse natural language description to PartSpec."""
        if not description or not description.strip():
            return ParseResult(success=False, error="Empty description")

        try:
            self._load_model()

            # Build prompt with few-shot examples
            prompt = self._build_prompt(description)

            # Generate response
            response = self._llm(
                prompt,
                max_tokens=2048,
                temperature=0.1,
                top_p=0.9,
                stop=["```", "```json"],
                echo=False,
            )

            raw_text = response["choices"][0]["text"].strip()

            # Extract JSON from response
            spec = self._extract_json(raw_text)

            if spec is None:
                return ParseResult(
                    success=False,
                    error="Failed to parse JSON from LLM response",
                    raw_response=raw_text
                )

            # Ensure unit_system is set
            spec["unit_system"] = unit_system.value

            # Validate and create PartSpec
            part_spec = PartSpec(**spec)

            # Run validation
            from ..validation import validate_spec
            val_result = validate_spec(part_spec)
            if not val_result.is_valid:
                errors = "; ".join([i.message for i in val_result.errors])
                return ParseResult(
                    success=False,
                    error=f"Generated spec validation failed: {errors}",
                    raw_response=raw_text
                )

            return ParseResult(success=True, spec=part_spec, raw_response=raw_text)

        except Exception as e:
            return ParseResult(success=False, error=str(e))

    def _build_prompt(self, description: str) -> str:
        """Build the full prompt with examples."""
        parts = [PromptTemplates.SYSTEM_PROMPT, ""]

        for ex in PromptTemplates.FEW_SHOT_EXAMPLES:
            parts.append(f"Input: {ex['input']}")
            parts.append(f"Output: {json.dumps(ex['output'], separators=(',', ':'))}")
            parts.append("")

        parts.append(PromptTemplates.USER_PROMPT_TEMPLATE.format(description=description))

        return "\n".join(parts)

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON object from text."""
        # Try to find JSON between ```json and ``` or just the first { ... }
        patterns = [
            r'```json\s*(\{.*?\})\s*```',
            r'```\s*(\{.*?\})\s*```',
            r'(\{.*\})',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    continue

        return None


class RuleBasedParser:
    """Fallback rule-based parser for simple descriptions without LLM."""

    def parse(self, description: str, unit_system: UnitSystem = UnitSystem.MM) -> ParseResult:
        """Parse using simple pattern matching."""
        desc_lower = description.lower()

        try:
            # Try to extract dimensions
            dims = self._extract_dimensions(desc_lower)

            # Determine primitive type
            prim_type = self._detect_primitive(desc_lower)

            if prim_type is None:
                return ParseResult(success=False, error="Could not determine primitive type")

            # Build feature
            feature = self._build_feature(prim_type, dims, desc_lower)

            spec = PartSpec(
                name=self._generate_name(prim_type, desc_lower),
                description=description,
                unit_system=unit_system,
                features=[feature]
            )

            return ParseResult(success=True, spec=spec)

        except Exception as e:
            return ParseResult(success=False, error=str(e))

    def _extract_dimensions(self, text: str) -> Dict[str, float]:
        """Extract numeric dimensions from text."""
        dims = {}

        # Pattern: number followed by unit or dimension word
        patterns = [
            (r'(\d+(?:\.\d+)?)\s*mm', 'mm'),
            (r'(\d+(?:\.\d+)?)\s*cm', 'cm'),
            (r'(\d+(?:\.\d+)?)\s*inch', 'in'),
            (r'(\d+(?:\.\d+)?)\s*in\b', 'in'),
            (r'(\d+(?:\.\d+)?)\s*[\'"]', 'in'),
            (r'(\d+(?:\.\d+)?)\s*(?:wide|width|x)', 'width'),
            (r'(\d+(?:\.\d+)?)\s*(?:deep|depth)', 'depth'),
            (r'(\d+(?:\.\d+)?)\s*(?:tall|high|height)', 'height'),
            (r'(\d+(?:\.\d+)?)\s*(?:diam|diameter)', 'diameter'),
            (r'(\d+(?:\.\d+)?)\s*(?:radius|rad)', 'radius'),
            (r'(\d+(?:\.\d+)?)\s*(?:long|length)', 'length'),
        ]

        for pattern, key in patterns:
            matches = re.findall(pattern, text)
            if matches:
                # Take the last match for each key
                dims[key] = float(matches[-1])

        return dims

    def _detect_primitive(self, text: str) -> Optional[PrimitiveType]:
        """Detect primitive type from keywords."""
        keywords = {
            PrimitiveType.BOX: ["box", "block", "cube", "rectangular", "plate", "slab"],
            PrimitiveType.CYLINDER: ["cylinder", "rod", "shaft", "pin", "pipe", "tube"],
            PrimitiveType.SPHERE: ["sphere", "ball", "globe"],
            PrimitiveType.CONE: ["cone", "conical"],
            PrimitiveType.TORUS: ["torus", "donut", "ring"],
            PrimitiveType.WEDGE: ["wedge", "ramp", "triangle"],
        }

        for prim_type, words in keywords.items():
            if any(w in text for w in words):
                return prim_type

        # Default to box if dimensions suggest it (e.g., "40x20x10" or "50 x 30 x 20")
        # Match patterns like "40x20x10", "50 x 30", "10 by 20 by 30", "10×20×30"
        box_pattern = r'\d+(?:\.\d+)?\s*[x×]\s*\d+(?:\.\d+)?'
        by_pattern = r'\d+(?:\.\d+)?\s+by\s+\d+(?:\.\d+)?'
        if re.search(box_pattern, text) or re.search(by_pattern, text):
            return PrimitiveType.BOX

        return None

    def _build_feature(self, prim_type: PrimitiveType, dims: Dict[str, float], text: str) -> FeatureSpec:
        """Build a FeatureSpec from primitive type and dimensions."""
        params = {}
        feature_id = prim_type.value + "_main"
        feature_name = prim_type.value

        if prim_type == PrimitiveType.BOX:
            width = dims.get('width', dims.get('mm', 40))
            depth = dims.get('depth', dims.get('mm', 20))
            height = dims.get('height', dims.get('mm', 10))

            params = {
                "width": ParameterSpec(name="width", value=width),
                "depth": ParameterSpec(name="depth", value=depth),
                "height": ParameterSpec(name="height", value=height),
            }

            # Check for hole
            hole_diameter = dims.get('diameter')
            if hole_diameter is None and 'hole' in text:
                # Try to find hole size
                hole_match = re.search(r'(\d+(?:\.\d+)?)\s*mm\s*hole', text)
                if not hole_match:
                    hole_match = re.search(r'hole\s*(\d+(?:\.\d+)?)\s*mm', text)
                if hole_match:
                    hole_diameter = float(hole_match.group(1))

            if hole_diameter:
                # Add hole as second feature (will be handled by caller)
                pass

        elif prim_type == PrimitiveType.CYLINDER:
            radius = dims.get('radius', dims.get('diameter', 20) / 2)
            height = dims.get('height', dims.get('length', dims.get('mm', 50)))

            params = {
                "radius": ParameterSpec(name="radius", value=radius),
                "height": ParameterSpec(name="height", value=height),
            }

        elif prim_type == PrimitiveType.SPHERE:
            radius = dims.get('radius', dims.get('diameter', 20) / 2)
            params = {
                "radius": ParameterSpec(name="radius", value=radius),
            }

        elif prim_type == PrimitiveType.CONE:
            radius_bottom = dims.get('radius', dims.get('diameter', 20) / 2)
            radius_top = dims.get('radius_top', 0)
            height = dims.get('height', dims.get('mm', 50))
            params = {
                "radius_bottom": ParameterSpec(name="radius_bottom", value=radius_bottom),
                "radius_top": ParameterSpec(name="radius_top", value=radius_top),
                "height": ParameterSpec(name="height", value=height),
            }

        elif prim_type == PrimitiveType.TORUS:
            major_radius = dims.get('radius', dims.get('major_radius', 20))
            minor_radius = dims.get('minor_radius', dims.get('diameter', 10) / 2)
            params = {
                "major_radius": ParameterSpec(name="major_radius", value=major_radius),
                "minor_radius": ParameterSpec(name="minor_radius", value=minor_radius),
            }

        elif prim_type == PrimitiveType.WEDGE:
            width = dims.get('width', 40)
            depth = dims.get('depth', 20)
            height = dims.get('height', 10)
            params = {
                "width": ParameterSpec(name="width", value=width),
                "depth": ParameterSpec(name="depth", value=depth),
                "height": ParameterSpec(name="height", value=height),
                "xmin": ParameterSpec(name="xmin", value=0),
                "zmin": ParameterSpec(name="zmin", value=0),
                "xmax": ParameterSpec(name="xmax", value=width),
                "zmax": ParameterSpec(name="zmax", value=height),
            }

        return FeatureSpec(
            id=feature_id,
            type=prim_type,
            name=feature_name,
            parameters=params,
            operation=OperationType.UNION,
        )

    def _generate_name(self, prim_type: PrimitiveType, text: str) -> str:
        """Generate a name for the part."""
        base_names = {
            PrimitiveType.BOX: "Box",
            PrimitiveType.CYLINDER: "Cylinder",
            PrimitiveType.SPHERE: "Sphere",
            PrimitiveType.CONE: "Cone",
            PrimitiveType.TORUS: "Torus",
            PrimitiveType.WEDGE: "Wedge",
        }
        return base_names.get(prim_type, "Part")


def parse_natural_language(description: str, use_llm: bool = False, **kwargs) -> ParseResult:
    """Main entry point for parsing natural language to PartSpec."""
    if use_llm:
        engine = NLPEngine(**kwargs)
        return engine.parse(description)
    else:
        parser = RuleBasedParser()
        unit_system = kwargs.get("unit_system", UnitSystem.MM)
        if isinstance(unit_system, str):
            unit_system = UnitSystem(unit_system)
        return parser.parse(description, unit_system=unit_system)
