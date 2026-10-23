"""
NLP module for natural language to PartSpec conversion.
Uses local LLM (llama.cpp) for offline processing.
"""

import json
from math import isfinite
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
3. Position/rotation in mm; build123d primitives are centered at their local origin unless a documented profile says otherwise
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
                        "position": [0, 0, 0],
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
    """Deterministic parser for common, explicitly dimensioned mechanical primitives.

    This rule-based path is intentionally conservative. It normalizes recognized
    lengths to mm, creates actual boolean hole features, and does not infer hidden
    geometry from descriptions it cannot parse.
    """

    _NUMBER = r"\d+(?:\.\d+)?"
    _UNIT = r"(?:millimeters?|millimetres?|mm|centimeters?|centimetres?|cm|inches?|inch|in\b|meters?|metres?|m\b|['\"])"

    @staticmethod
    def _normalize_unit(unit_text: Optional[str], default_unit: UnitSystem) -> UnitSystem:
        if not unit_text:
            return default_unit
        unit = unit_text.strip().lower()
        if unit in {"mm", "millimeter", "millimeters", "millimetre", "millimetres"}:
            return UnitSystem.MM
        if unit in {"cm", "centimeter", "centimeters", "centimetre", "centimetres"}:
            return UnitSystem.CM
        if unit in {"in", "inch", "inches", "'", '"'}:
            return UnitSystem.INCH
        if unit in {"m", "meter", "meters", "metre", "metres"}:
            return UnitSystem.M
        return default_unit

    @classmethod
    def _to_mm(cls, raw_value: str | float, unit_text: Optional[str], default_unit: UnitSystem) -> float:
        unit = cls._normalize_unit(unit_text, default_unit)
        factors = {
            UnitSystem.MM: 1.0,
            UnitSystem.CM: 10.0,
            UnitSystem.INCH: 25.4,
            UnitSystem.M: 1000.0,
        }
        value = float(raw_value)
        if not value > 0:
            raise ValueError("Dimensions must be positive.")
        return value * factors[unit]

    def parse(self, description: str, unit_system: UnitSystem = UnitSystem.MM) -> ParseResult:
        """Parse a small, known subset of descriptions using explicit rules."""
        if not description or not description.strip():
            return ParseResult(success=False, error="Empty description")
        if isinstance(unit_system, str):
            unit_system = UnitSystem(unit_system)
        text = description.lower()

        try:
            dims = self._extract_dimensions(text, unit_system)
            prim_type = self._detect_primitive(text)
            if prim_type is None:
                return ParseResult(
                    success=False,
                    error="Could not identify a supported primitive. Try a dimensioned box, cylinder, sphere, cone, torus, or wedge.",
                )

            hole_mentioned = bool(re.search(r"\b(?:holes?|bores?)\b", text))
            tube_mentioned = bool(re.search(r"\b(?:tube|pipe)\b", text))
            count_match = re.search(r"\b(\d+)\s+holes?\b", text)
            word_counts = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "eight": 8}
            word_count_match = re.search(r"\b(two|three|four|five|six|eight)\s+holes?\b", text)
            hole_count = int(count_match.group(1)) if count_match else (
                word_counts[word_count_match.group(1)] if word_count_match else 1
            )
            if hole_mentioned and hole_count > 1:
                return ParseResult(
                    success=False,
                    error="Multiple-hole patterns need explicit hole coordinates/spacing. No guessed hole pattern was generated.",
                )

            if tube_mentioned and prim_type != PrimitiveType.CYLINDER:
                return ParseResult(success=False, error="Tube/pipe hollowing is supported only for a dimensioned cylindrical tube.")

            if tube_mentioned:
                outer_diameter = dims.get("outer_diameter")
                if outer_diameter is None:
                    outer_diameter = dims.get("diameter")
                if outer_diameter is None and dims.get("radius") is not None:
                    outer_diameter = dims["radius"] * 2.0
                inner_diameter = dims.get("inner_diameter")
                if inner_diameter is None and dims.get("wall_thickness") is not None and outer_diameter is not None:
                    inner_diameter = outer_diameter - (2.0 * dims["wall_thickness"])
                if outer_diameter is None:
                    return ParseResult(success=False, error="A tube/pipe needs an explicit outer diameter or radius.")
                if inner_diameter is None:
                    return ParseResult(success=False, error="A tube/pipe needs an explicit inner diameter or wall thickness; a solid cylinder would be a misleading result.")
                if not 0 < inner_diameter < outer_diameter:
                    return ParseResult(success=False, error="Tube dimensions must satisfy 0 < inner diameter < outer diameter.")
                dims["outer_diameter"] = outer_diameter
                dims["diameter"] = outer_diameter
                dims["inner_diameter"] = inner_diameter
                hole_mentioned = True
                dims["hole_diameter"] = inner_diameter

            if hole_mentioned and prim_type not in (PrimitiveType.BOX, PrimitiveType.CYLINDER):
                return ParseResult(
                    success=False,
                    error="Through-holes are currently supported only for dimensioned boxes and cylinders. No approximate substitute was generated.",
                )
            if hole_mentioned and dims.get("hole_diameter") is None:
                return ParseResult(success=False, error="A hole/bore requires an explicit diameter.")

            base_feature = self._build_feature(prim_type, dims)
            features = [base_feature]

            if hole_mentioned:
                hole_diameter = dims["hole_diameter"]
                if prim_type == PrimitiveType.BOX:
                    width, depth, height = (
                        base_feature.parameters["width"].value,
                        base_feature.parameters["depth"].value,
                        base_feature.parameters["height"].value,
                    )
                    if hole_diameter >= min(width, depth):
                        return ParseResult(success=False, error="Hole diameter must be smaller than both box width and depth.")
                    cutter_height = height + max(2.0, height * 0.1)
                else:
                    outer_radius = base_feature.parameters["radius"].value
                    if hole_diameter >= 2.0 * outer_radius:
                        return ParseResult(success=False, error="Bore diameter must be smaller than the cylinder diameter.")
                    cutter_height = base_feature.parameters["height"].value + max(
                        2.0, base_feature.parameters["height"].value * 0.1
                    )
                features.append(
                    FeatureSpec(
                        id="through_bore",
                        type=PrimitiveType.CYLINDER,
                        name="Through Hole" if not tube_mentioned else "Tube Bore",
                        parameters={
                            "radius": ParameterSpec(name="radius", value=hole_diameter / 2.0, unit=UnitSystem.MM),
                            "height": ParameterSpec(name="height", value=cutter_height, unit=UnitSystem.MM),
                        },
                        position=[0.0, 0.0, 0.0],
                        rotation=[0.0, 0.0, 0.0],
                        operation=OperationType.DIFFERENCE,
                        parent_id=base_feature.id,
                        metadata={"generated_by": "rule_parser", "feature_role": "through_hole"},
                    )
                )

            spec = PartSpec(
                name=self._generate_name(prim_type, text),
                description=description,
                unit_system=unit_system,
                features=features,
            )
            return ParseResult(success=True, spec=spec)
        except Exception as exc:
            return ParseResult(success=False, error=str(exc))

    def _extract_dimensions(
        self, text: str, unit_system: UnitSystem = UnitSystem.MM
    ) -> Dict[str, float]:
        """Extract recognized measurements and normalize all values to millimeters."""
        dims: Dict[str, float] = {}
        number = self._NUMBER
        unit = self._UNIT
        triplet_pattern = re.compile(
            rf"(?<![\w.])(?P<n1>{number})\s*(?P<u1>{unit})?\s*(?:x|×|by)\s*"
            rf"(?P<n2>{number})\s*(?P<u2>{unit})?\s*(?:x|×|by)\s*"
            rf"(?P<n3>{number})\s*(?P<u3>{unit})?",
            re.IGNORECASE,
        )
        match = triplet_pattern.search(text)
        cleaned = text
        if match:
            unit_values = [match.group("u1"), match.group("u2"), match.group("u3")]
            common_unit = next((candidate for candidate in reversed(unit_values) if candidate), None)
            normalized = [
                self._to_mm(match.group(f"n{i}"), unit_values[i - 1] or common_unit, unit_system)
                for i in (1, 2, 3)
            ]
            dims.update(width=normalized[0], depth=normalized[1], height=normalized[2])
            cleaned = text[:match.start()] + " " * (match.end() - match.start()) + text[match.end():]
        else:
            # A two-dimensional box description remains useful; height falls back
            # to the documented simple-box default instead of shifting dimensions.
            pair_pattern = re.compile(
                rf"(?<![\w.])(?P<n1>{number})\s*(?P<u1>{unit})?\s*(?:x|×|by)\s*"
                rf"(?P<n2>{number})\s*(?P<u2>{unit})?",
                re.IGNORECASE,
            )
            pair = pair_pattern.search(text)
            if pair:
                units = [pair.group("u1"), pair.group("u2")]
                common_unit = next((candidate for candidate in reversed(units) if candidate), None)
                dims["width"] = self._to_mm(pair.group("n1"), units[0] or common_unit, unit_system)
                dims["depth"] = self._to_mm(pair.group("n2"), units[1] or common_unit, unit_system)
                cleaned = text[:pair.start()] + " " * (pair.end() - pair.start()) + text[pair.end():]

        def capture(key: str, patterns: list[str]) -> None:
            for pattern in patterns:
                found = re.search(pattern, cleaned, re.IGNORECASE)
                if found:
                    dims[key] = self._to_mm(found.group("num"), found.groupdict().get("unit"), unit_system)
                    return

        scalar_rules = {
            "width": [
                rf"(?P<num>{number})\s*(?P<unit>{unit})?\s*(?:wide|width)\b",
                rf"\b(?:width|wide)\s*(?:of|=|:)?\s*(?P<num>{number})\s*(?P<unit>{unit})?",
            ],
            "depth": [
                rf"(?P<num>{number})\s*(?P<unit>{unit})?\s*(?:deep|depth)\b",
                rf"\b(?:depth|deep)\s*(?:of|=|:)?\s*(?P<num>{number})\s*(?P<unit>{unit})?",
            ],
            "height": [
                rf"(?P<num>{number})\s*(?P<unit>{unit})?\s*(?:tall|high|height)\b",
                rf"\b(?:height|tall|high)\s*(?:of|=|:)?\s*(?P<num>{number})\s*(?P<unit>{unit})?",
            ],
            "diameter": [
                rf"(?P<num>{number})\s*(?P<unit>{unit})?\s*(?:diameter|diam|dia)\b",
                rf"\b(?:diameter|diam|dia)\s*(?:of|=|:)?\s*(?P<num>{number})\s*(?P<unit>{unit})?",
            ],
            "radius": [
                rf"(?P<num>{number})\s*(?P<unit>{unit})?\s*(?:radius|rad)\b",
                rf"\b(?:radius|rad)\s*(?:of|=|:)?\s*(?P<num>{number})\s*(?P<unit>{unit})?",
            ],
            "length": [
                rf"(?P<num>{number})\s*(?P<unit>{unit})?\s*(?:long|length)\b",
                rf"\b(?:length|long)\s*(?:of|=|:)?\s*(?P<num>{number})\s*(?P<unit>{unit})?",
            ],
            "outer_diameter": [
                rf"(?P<num>{number})\s*(?P<unit>{unit})?\s*(?:outer|outside|external|od)\s*(?:diameter|diam|dia)?\b",
                rf"\b(?:outer|outside|external|od)\s*(?:diameter|diam|dia)?\s*(?:of|=|:)?\s*(?P<num>{number})\s*(?P<unit>{unit})?",
            ],
            "inner_diameter": [
                rf"(?P<num>{number})\s*(?P<unit>{unit})?\s*(?:inner|inside|internal|id)\s*(?:diameter|diam|dia)?\b",
                rf"\b(?:inner|inside|internal|id)\s*(?:diameter|diam|dia)?\s*(?:of|=|:)?\s*(?P<num>{number})\s*(?P<unit>{unit})?",
            ],
            "wall_thickness": [
                rf"(?P<num>{number})\s*(?P<unit>{unit})?\s*wall\s*thickness\b",
                rf"\bwall\s*thickness\s*(?:of|=|:)?\s*(?P<num>{number})\s*(?P<unit>{unit})?",
            ],
            "major_radius": [
                rf"(?P<num>{number})\s*(?P<unit>{unit})?\s*major\s*radius\b",
                rf"\bmajor\s*radius\s*(?:of|=|:)?\s*(?P<num>{number})\s*(?P<unit>{unit})?",
            ],
            "minor_radius": [
                rf"(?P<num>{number})\s*(?P<unit>{unit})?\s*minor\s*radius\b",
                rf"\bminor\s*radius\s*(?:of|=|:)?\s*(?P<num>{number})\s*(?P<unit>{unit})?",
            ],
            "radius_top": [
                rf"(?P<num>{number})\s*(?P<unit>{unit})?\s*(?:top|upper)\s*radius\b",
                rf"\b(?:top|upper)\s*radius\s*(?:of|=|:)?\s*(?P<num>{number})\s*(?P<unit>{unit})?",
            ],
        }
        for key, patterns in scalar_rules.items():
            capture(key, patterns)

        if "plate" in text and "height" not in dims and "wall_thickness" in dims:
            dims["height"] = dims["wall_thickness"]

        if "hole" in text or "bore" in text:
            hole_patterns = [
                rf"(?P<num>{number})\s*(?P<unit>{unit})?\s*(?:diameter|diam|dia)?\s*(?:through\s+)?(?:hole|bore)\b",
                rf"\b(?:hole|bore)\s*(?:diameter|diam|dia)?\s*(?:of|=|:)?\s*(?P<num>{number})\s*(?P<unit>{unit})?",
            ]
            capture("hole_diameter", hole_patterns)
            if "hole_diameter" not in dims and "diameter" in dims:
                dims["hole_diameter"] = dims["diameter"]

        return dims

    def _detect_primitive(self, text: str) -> Optional[PrimitiveType]:
        """Detect explicit primitive keywords before falling back to dimension triplets."""
        keywords = {
            PrimitiveType.BOX: ["box", "block", "cube", "rectangular", "plate", "slab"],
            PrimitiveType.CYLINDER: ["cylinder", "rod", "shaft", "pin", "pipe", "tube"],
            PrimitiveType.SPHERE: ["sphere", "ball", "globe"],
            PrimitiveType.CONE: ["cone", "conical"],
            PrimitiveType.TORUS: ["torus", "donut", "ring"],
            PrimitiveType.WEDGE: ["wedge", "ramp", "triangle"],
        }
        for prim_type, words in keywords.items():
            if any(word in text for word in words):
                return prim_type
        if re.search(r"\d+(?:\.\d+)?\s*(?:x|×)\s*\d+(?:\.\d+)?", text) or re.search(
            r"\d+(?:\.\d+)?\s+by\s+\d+(?:\.\d+)?", text
        ):
            return PrimitiveType.BOX
        return None

    @staticmethod
    def _parameter(name: str, value: float) -> ParameterSpec:
        return ParameterSpec(name=name, value=value, unit=UnitSystem.MM)

    @staticmethod
    def _require_dimension(dims: Dict[str, float], keys: tuple[str, ...], label: str) -> float:
        for key in keys:
            value = dims.get(key)
            if value is not None:
                if not isfinite(float(value)) or value <= 0:
                    raise ValueError(f"{label} must be finite and greater than zero.")
                return float(value)
        raise ValueError(f"An explicit {label} is required; no default dimension was guessed.")

    def _build_feature(self, prim_type: PrimitiveType, dims: Dict[str, float]) -> FeatureSpec:
        """Create an explicit feature with millimeter-valued parameters.

        Underspecified descriptions fail rather than silently receive arbitrary
        default dimensions that could produce a misleading CAD model.
        """
        if prim_type == PrimitiveType.BOX:
            params = {
                "width": self._parameter("width", self._require_dimension(dims, ("width",), "box width")),
                "depth": self._parameter("depth", self._require_dimension(dims, ("depth",), "box depth")),
                "height": self._parameter("height", self._require_dimension(dims, ("height",), "box height/thickness")),
            }
        elif prim_type == PrimitiveType.CYLINDER:
            if dims.get("outer_diameter") is not None:
                radius = self._require_dimension(dims, ("outer_diameter",), "cylinder outer diameter") / 2.0
            elif dims.get("radius") is not None:
                radius = self._require_dimension(dims, ("radius",), "cylinder radius")
            else:
                radius = self._require_dimension(dims, ("diameter",), "cylinder diameter") / 2.0
            height = self._require_dimension(dims, ("height", "length"), "cylinder height/length")
            params = {
                "radius": self._parameter("radius", radius),
                "height": self._parameter("height", height),
            }
        elif prim_type == PrimitiveType.SPHERE:
            if dims.get("radius") is not None:
                radius = self._require_dimension(dims, ("radius",), "sphere radius")
            else:
                radius = self._require_dimension(dims, ("diameter",), "sphere diameter") / 2.0
            params = {"radius": self._parameter("radius", radius)}
        elif prim_type == PrimitiveType.CONE:
            if dims.get("radius") is not None:
                radius_bottom = self._require_dimension(dims, ("radius",), "cone base radius")
            else:
                radius_bottom = self._require_dimension(dims, ("diameter",), "cone base diameter") / 2.0
            height = self._require_dimension(dims, ("height", "length"), "cone height")
            radius_top = dims.get("radius_top", 0.0)
            if not isfinite(float(radius_top)) or radius_top < 0 or radius_top >= radius_bottom:
                raise ValueError("Cone top radius must be non-negative and smaller than its base radius.")
            params = {
                "radius_bottom": self._parameter("radius_bottom", radius_bottom),
                "radius_top": self._parameter("radius_top", radius_top),
                "height": self._parameter("height", height),
            }
        elif prim_type == PrimitiveType.TORUS:
            major_radius = self._require_dimension(dims, ("major_radius", "radius"), "torus major radius")
            if dims.get("minor_radius") is not None:
                minor_radius = self._require_dimension(dims, ("minor_radius",), "torus minor radius")
            elif dims.get("diameter") is not None:
                minor_radius = self._require_dimension(dims, ("diameter",), "torus tube diameter") / 2.0
            else:
                raise ValueError("An explicit torus minor radius or tube diameter is required.")
            if minor_radius >= major_radius:
                raise ValueError("Torus minor radius must be smaller than its major radius.")
            params = {
                "major_radius": self._parameter("major_radius", major_radius),
                "minor_radius": self._parameter("minor_radius", minor_radius),
            }
        elif prim_type == PrimitiveType.WEDGE:
            width = self._require_dimension(dims, ("width",), "wedge width")
            depth = self._require_dimension(dims, ("depth",), "wedge depth")
            height = self._require_dimension(dims, ("height",), "wedge height")
            params = {
                "width": self._parameter("width", width),
                "depth": self._parameter("depth", depth),
                "height": self._parameter("height", height),
                "xmin": self._parameter("xmin", 0.0),
                "zmin": self._parameter("zmin", 0.0),
                "xmax": self._parameter("xmax", width),
                "zmax": self._parameter("zmax", height),
            }
        else:
            raise ValueError(f"Unsupported primitive: {prim_type.value}")

        return FeatureSpec(
            id=f"{prim_type.value}_main",
            type=prim_type,
            name=prim_type.value,
            parameters=params,
            position=[0.0, 0.0, 0.0],
            rotation=[0.0, 0.0, 0.0],
            operation=OperationType.UNION,
        )

    @staticmethod
    def _generate_name(prim_type: PrimitiveType, text: str) -> str:
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
