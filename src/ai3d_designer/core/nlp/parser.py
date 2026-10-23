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
    """Conservative parser for dimensioned primitive CAD parts.

    This parser deliberately rejects feature requests it cannot represent, rather
    than silently returning a simplified shape that could be mistaken for a
    dimensionally accurate engineering model.
    """

    _NUMBER = r"\d+(?:\.\d+)?"
    _UNIT = r"""(?:millimeters?|mm|centimeters?|cm|inches?|inch|in\b|meters?|m|["'])"""
    _TUPLE_PATTERN = re.compile(
        rf"(?<![\w.])(?P<a>{_NUMBER})\s*(?P<ua>{_UNIT})?\s*(?:x|×|\bby\b)\s*"
        rf"(?P<b>{_NUMBER})\s*(?P<ub>{_UNIT})?\s*(?:x|×|\bby\b)\s*"
        rf"(?P<c>{_NUMBER})\s*(?P<uc>{_UNIT})?(?!\w)",
        re.IGNORECASE,
    )

    _UNIT_FACTORS = {
        UnitSystem.MM: 1.0,
        UnitSystem.CM: 10.0,
        UnitSystem.INCH: 25.4,
        UnitSystem.M: 1000.0,
    }

    _UNSUPPORTED = {
        "fillet": "fillets",
        "chamfer": "chamfers",
        "thread": "threads",
        "gear": "gears",
        "helical": "helical features",
        "lattice": "lattice structures",
        "impeller": "impellers",
        "turbine": "turbines",
        "counterbore": "counterbores",
        "countersink": "countersinks",
        "slot": "slots",
        "pocket": "pockets",
        "loft": "lofts",
        "sweep": "sweeps",
    }

    def parse(self, description: str, unit_system: UnitSystem = UnitSystem.MM) -> ParseResult:
        """Parse supported, explicitly dimensioned primitive geometry."""
        if not description or not description.strip():
            return ParseResult(success=False, error="Enter a part description with dimensions.")

        try:
            unit_system = UnitSystem(unit_system)
        except (TypeError, ValueError):
            return ParseResult(success=False, error="Choose a supported unit system: mm, cm, in, or m.")

        text = re.sub(r"\s+", " ", description.strip().lower().replace("×", "x"))
        for keyword, label in self._UNSUPPORTED.items():
            if re.search(rf"\b{re.escape(keyword)}\w*\b", text):
                return ParseResult(
                    success=False,
                    error=(
                        f"This rule-based CAD engine does not yet model {label}. "
                        "The requested feature was not approximated; use only supported, "
                        "dimensioned primitives or implement this feature explicitly."
                    ),
                )

        primitive = self._detect_primitive(text)
        if primitive is None:
            return ParseResult(
                success=False,
                error="Could not identify a supported primitive. Try a dimensioned box, cylinder, sphere, cone, torus, wedge, pipe, or tube.",
            )

        mentioned = self._mentioned_primitives(text)
        if len(mentioned) > 1:
            return ParseResult(
                success=False,
                error=(
                    "This description appears to combine multiple primitive bodies. "
                    "The rule-based parser will not silently omit a body; describe one supported "
                    "body and its supported through-hole, or use an explicit PartSpec."
                ),
            )

        try:
            features = self._build_features(primitive, text, unit_system)
            if not features:
                return ParseResult(success=False, error="No supported geometric features were produced.")
            spec = PartSpec(
                name=self._generate_name(primitive, text),
                description=description,
                unit_system=unit_system,
                features=features,
                metadata={"generator": "rule-based-v2", "coordinate_convention": "centered_mm"},
            )
            from ..validation import validate_spec

            validation = validate_spec(spec)
            if not validation.is_valid:
                messages = "; ".join(issue.message for issue in validation.errors)
                return ParseResult(success=False, error=f"Generated specification is invalid: {messages}")
            return ParseResult(success=True, spec=spec)
        except (ValueError, TypeError, OverflowError) as exc:
            return ParseResult(success=False, error=str(exc))

    @classmethod
    def _unit_from_token(cls, token: Optional[str], default: UnitSystem) -> UnitSystem:
        unit = (token or "").strip().lower()
        if not unit:
            return default
        if unit in {"mm", "millimeter", "millimeters"}:
            return UnitSystem.MM
        if unit in {"cm", "centimeter", "centimeters"}:
            return UnitSystem.CM
        if unit in {"in", "inch", "inches", '"', "'"}:
            return UnitSystem.INCH
        if unit in {"m", "meter", "meters"}:
            return UnitSystem.M
        return default

    @classmethod
    def _to_mm(cls, dimension: tuple[float, UnitSystem]) -> float:
        value, unit = dimension
        return value * cls._UNIT_FACTORS[unit]

    @classmethod
    def _parameter(cls, name: str, dimension: tuple[float, UnitSystem], description: str = "") -> ParameterSpec:
        value, unit = dimension
        return ParameterSpec(name=name, value=value, unit=unit, description=description)

    def _dimension_tuple(
        self, text: str, default_unit: UnitSystem
    ) -> Optional[list[tuple[float, UnitSystem]]]:
        match = self._TUPLE_PATTERN.search(text)
        if not match:
            return None
        tokens = [match.group(f"u{axis}") for axis in ("a", "b", "c")]
        # A unit written only once at the end of a dimension tuple conventionally
        # applies to the entire tuple, e.g. 40 x 20 x 10 mm.
        inherited = next(
            (self._unit_from_token(token, default_unit) for token in reversed(tokens) if token),
            default_unit,
        )
        return [
            (float(match.group(axis)), self._unit_from_token(match.group(f"u{axis}"), inherited))
            for axis in ("a", "b", "c")
        ]

    def _find_dimension(
        self,
        text: str,
        labels: list[str],
        default_unit: UnitSystem,
    ) -> Optional[tuple[float, UnitSystem]]:
        number = self._NUMBER
        unit = rf"(?P<unit>{self._UNIT})?"
        label = "(?:" + "|".join(labels) + ")"
        # Prefer label-first forms such as "ID 10 mm" before trailing-label
        # forms such as "20 mm ID"; otherwise the outer diameter can be captured
        # as the inner diameter in text like "OD 20 mm ID 10 mm".
        patterns = (
            rf"\b{label}\s*(?:of\s*)?(?P<value>{number})\s*{unit}(?!\w)",
            rf"(?<![\w.])(?P<value>{number})\s*{unit}\s*{label}\b",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = float(match.group("value"))
                unit_system = self._unit_from_token(match.group("unit"), default_unit)
                if value <= 0:
                    raise ValueError(f"Dimension for {labels[0]} must be greater than zero.")
                return value, unit_system
        return None

    def _find_hole_diameter(
        self, text: str, default_unit: UnitSystem
    ) -> Optional[tuple[float, UnitSystem]]:
        number = self._NUMBER
        unit = rf"(?P<unit>{self._UNIT})?"
        patterns = (
            rf"(?<![\w.])(?P<value>{number})\s*{unit}\s*(?:diameter\s+)?(?:through\s+)?hole\b",
            rf"\bhole\s*(?:of\s*)?(?:(?:diameter|dia)\s*)?(?P<value>{number})\s*{unit}(?!\w)",
            rf"\b(?:diameter|dia)\s*(?P<value>{number})\s*{unit}\s+hole\b",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = float(match.group("value"))
                if value <= 0:
                    raise ValueError("Hole diameter must be greater than zero.")
                return value, self._unit_from_token(match.group("unit"), default_unit)
        return None

    def _dimension_or_error(
        self, dimension: Optional[tuple[float, UnitSystem]], label: str
    ) -> tuple[float, UnitSystem]:
        if dimension is None:
            raise ValueError(
                f"Could not determine {label}. Include its numeric dimension and unit, "
                "or select the intended unit system in the app."
            )
        return dimension

    def _mentioned_primitives(self, text: str) -> set[PrimitiveType]:
        terms = {
            PrimitiveType.BOX: r"\b(box|block|cube|rectangular|plate|slab)\b",
            PrimitiveType.CYLINDER: r"\b(cylinder|cylindrical|rod|shaft|pin|pipe|tube)\b",
            PrimitiveType.SPHERE: r"\b(sphere|spherical|ball|globe)\b",
            PrimitiveType.CONE: r"\b(cone|conical|frustum)\b",
            PrimitiveType.TORUS: r"\b(torus|donut|doughnut|ring)\b",
            PrimitiveType.WEDGE: r"\b(wedge|ramp)\b",
        }
        return {kind for kind, pattern in terms.items() if re.search(pattern, text)}

    def _detect_primitive(self, text: str) -> Optional[PrimitiveType]:
        mentioned = self._mentioned_primitives(text)
        # Prefer an explicitly named primitive. The multi-primitive guard runs
        # separately so ambiguous compound descriptions are rejected.
        order = (
            PrimitiveType.BOX,
            PrimitiveType.CYLINDER,
            PrimitiveType.SPHERE,
            PrimitiveType.CONE,
            PrimitiveType.TORUS,
            PrimitiveType.WEDGE,
        )
        for primitive in order:
            if primitive in mentioned:
                return primitive
        if self._dimension_tuple(text, UnitSystem.MM):
            return PrimitiveType.BOX
        return None

    def _build_features(
        self, primitive: PrimitiveType, text: str, default_unit: UnitSystem
    ) -> list[FeatureSpec]:
        """Build one solid feature history, or fail on details not represented."""
        tuple_dims = self._dimension_tuple(text, default_unit)
        width_labels = [r"width", r"wide"]
        depth_labels = [r"depth", r"deep"]
        height_labels = [r"height", r"high", r"tall"]
        length_labels = [r"length", r"long", r"height", r"tall", r"high"]
        features: list[FeatureSpec] = []

        if primitive == PrimitiveType.BOX:
            if tuple_dims:
                width, depth, height = tuple_dims
            else:
                cube_match = re.search(
                    rf"(?<![\w.])(?P<value>{self._NUMBER})\s*(?P<unit>{self._UNIT})?\s*(?:sized\s*)?cube\b",
                    text,
                    re.IGNORECASE,
                )
                if cube_match:
                    dim = (
                        float(cube_match.group("value")),
                        self._unit_from_token(cube_match.group("unit"), default_unit),
                    )
                    width = depth = height = dim
                else:
                    width = self._dimension_or_error(
                        self._find_dimension(text, width_labels, default_unit), "box width"
                    )
                    depth = self._dimension_or_error(
                        self._find_dimension(text, depth_labels, default_unit), "box depth"
                    )
                    height = self._dimension_or_error(
                        self._find_dimension(text, height_labels, default_unit), "box height"
                    )

            base = FeatureSpec(
                id="base",
                type=PrimitiveType.BOX,
                name="Base box",
                parameters={
                    "width": self._parameter("width", width),
                    "depth": self._parameter("depth", depth),
                    "height": self._parameter("height", height),
                },
                position=[0.0, 0.0, 0.0],
                operation=OperationType.UNION,
            )
            features.append(base)

            if re.search(r"\bholes\b|\b\d+\s+holes?\b", text):
                return self._raise("Multiple holes are not yet supported by the rule-based parser.")
            if re.search(r"\bhole\b", text):
                hole_diameter = self._dimension_or_error(
                    self._find_hole_diameter(text, default_unit), "through-hole diameter"
                )
                if not re.search(r"\bthrough\b|\bcenter(?:ed|ed)?\b|\bcentre\b|\bcenter\b", text):
                    return self._raise(
                        "Only a centered through-hole is supported for box descriptions. "
                        "The requested hole was not placed approximately."
                    )
                cutter_height_mm = self._to_mm(height) + 2.0
                cutter = FeatureSpec(
                    id="center_hole",
                    type=PrimitiveType.CYLINDER,
                    name="Centered through-hole",
                    parameters={
                        "radius": self._parameter(
                            "radius", (hole_diameter[0] / 2.0, hole_diameter[1]), "Hole radius"
                        ),
                        "height": self._parameter("height", (cutter_height_mm, UnitSystem.MM), "Through cutter"),
                    },
                    position=[0.0, 0.0, 0.0],
                    operation=OperationType.DIFFERENCE,
                    parent_id="base",
                )
                features.append(cutter)
            return features

        if primitive == PrimitiveType.CYLINDER:
            is_hollow = bool(re.search(r"\b(pipe|tube)\b", text))
            height = self._dimension_or_error(
                self._find_dimension(text, length_labels, default_unit), "cylinder height/length"
            )
            if tuple_dims and not self._find_dimension(text, length_labels, default_unit):
                height = tuple_dims[2]
            if is_hollow:
                outer_diameter = self._dimension_or_error(
                    self._find_dimension(
                        text, [r"outer\s+diameter", r"outer\s+dia", r"\bod\b"], default_unit
                    ),
                    "pipe/tube outer diameter (OD)",
                )
                inner_diameter = self._dimension_or_error(
                    self._find_dimension(
                        text, [r"inner\s+diameter", r"inner\s+dia", r"\bid\b"], default_unit
                    ),
                    "pipe/tube inner diameter (ID)",
                )
                if self._to_mm(inner_diameter) >= self._to_mm(outer_diameter):
                    raise ValueError("Pipe/tube inner diameter must be smaller than its outer diameter.")
                outer = FeatureSpec(
                    id="outer_cylinder",
                    type=PrimitiveType.CYLINDER,
                    name="Pipe/tube outside",
                    parameters={
                        "radius": self._parameter(
                            "radius", (outer_diameter[0] / 2.0, outer_diameter[1])
                        ),
                        "height": self._parameter("height", height),
                    },
                    operation=OperationType.UNION,
                )
                cutter_height = self._to_mm(height) + 2.0
                inner = FeatureSpec(
                    id="inner_bore",
                    type=PrimitiveType.CYLINDER,
                    name="Pipe/tube bore",
                    parameters={
                        "radius": self._parameter(
                            "radius", (inner_diameter[0] / 2.0, inner_diameter[1])
                        ),
                        "height": self._parameter("height", (cutter_height, UnitSystem.MM)),
                    },
                    operation=OperationType.DIFFERENCE,
                    parent_id="outer_cylinder",
                )
                return [outer, inner]

            radius = self._find_dimension(text, [r"radius", r"rad"], default_unit)
            diameter = self._find_dimension(text, [r"diameter", r"dia", r"\bdia\b"], default_unit)
            if radius is None and diameter is not None:
                radius = (diameter[0] / 2.0, diameter[1])
            radius = self._dimension_or_error(radius, "cylinder radius or diameter")
            return [FeatureSpec(
                id="cylinder_main",
                type=PrimitiveType.CYLINDER,
                name="Cylinder",
                parameters={
                    "radius": self._parameter("radius", radius),
                    "height": self._parameter("height", height),
                },
                position=[0.0, 0.0, 0.0],
                operation=OperationType.UNION,
            )]

        if primitive == PrimitiveType.SPHERE:
            radius = self._find_dimension(text, [r"radius", r"rad"], default_unit)
            diameter = self._find_dimension(text, [r"diameter", r"dia"], default_unit)
            if radius is None and diameter is not None:
                radius = (diameter[0] / 2.0, diameter[1])
            radius = self._dimension_or_error(radius, "sphere radius or diameter")
            if re.search(r"\bhole\b", text):
                return self._raise("Sphere holes are not yet supported by the rule-based parser.")
            return [FeatureSpec(
                id="sphere_main",
                type=PrimitiveType.SPHERE,
                name="Sphere",
                parameters={"radius": self._parameter("radius", radius)},
                operation=OperationType.UNION,
            )]

        if primitive == PrimitiveType.CONE:
            radius_bottom = self._find_dimension(
                text, [r"bottom\s+radius", r"base\s+radius", r"radius", r"rad"], default_unit
            )
            bottom_diameter = self._find_dimension(
                text, [r"base\s+diameter", r"diameter", r"dia"], default_unit
            )
            if radius_bottom is None and bottom_diameter is not None:
                radius_bottom = (bottom_diameter[0] / 2.0, bottom_diameter[1])
            radius_bottom = self._dimension_or_error(radius_bottom, "cone base radius or diameter")
            height = self._dimension_or_error(
                self._find_dimension(text, length_labels, default_unit), "cone height"
            )
            radius_top = self._find_dimension(
                text, [r"top\s+radius", r"upper\s+radius"], default_unit
            )
            top_diameter = self._find_dimension(
                text, [r"top\s+diameter", r"upper\s+diameter"], default_unit
            )
            if radius_top is None and top_diameter is not None:
                radius_top = (top_diameter[0] / 2.0, top_diameter[1])
            if re.search(r"\bfrustum\b|\btruncated\s+cone\b", text) and radius_top is None:
                return self._raise("A truncated cone/frustum requires its top radius or top diameter.")
            if radius_top is None:
                radius_top = (0.0, radius_bottom[1])
            if self._to_mm(radius_top) >= self._to_mm(radius_bottom):
                raise ValueError("Cone top radius must be smaller than its base radius.")
            return [FeatureSpec(
                id="cone_main",
                type=PrimitiveType.CONE,
                name="Cone or conical frustum",
                parameters={
                    "radius_bottom": self._parameter("radius_bottom", radius_bottom),
                    "radius_top": self._parameter("radius_top", radius_top),
                    "height": self._parameter("height", height),
                },
                operation=OperationType.UNION,
            )]

        if primitive == PrimitiveType.TORUS:
            outer_diameter = self._find_dimension(
                text, [r"outer\s+diameter", r"outer\s+dia", r"\bod\b"], default_unit
            )
            inner_diameter = self._find_dimension(
                text, [r"inner\s+diameter", r"inner\s+dia", r"\bid\b"], default_unit
            )
            if outer_diameter and inner_diameter:
                outer_mm = self._to_mm(outer_diameter)
                inner_mm = self._to_mm(inner_diameter)
                if inner_mm >= outer_mm:
                    raise ValueError("Torus inner diameter must be smaller than its outer diameter.")
                major = ((outer_mm + inner_mm) / 4.0, UnitSystem.MM)
                minor = ((outer_mm - inner_mm) / 4.0, UnitSystem.MM)
            else:
                major = self._find_dimension(
                    text, [r"major\s+radius", r"mean\s+radius", r"radius"], default_unit
                )
                minor = self._find_dimension(text, [r"minor\s+radius", r"tube\s+radius"], default_unit)
                major = self._dimension_or_error(major, "torus major radius")
                minor = self._dimension_or_error(minor, "torus minor radius")
            if self._to_mm(minor) >= self._to_mm(major):
                raise ValueError("A printable ring torus requires its minor radius to be smaller than its major radius.")
            return [FeatureSpec(
                id="torus_main",
                type=PrimitiveType.TORUS,
                name="Torus",
                parameters={
                    "major_radius": self._parameter("major_radius", major),
                    "minor_radius": self._parameter("minor_radius", minor),
                },
                operation=OperationType.UNION,
            )]

        if primitive == PrimitiveType.WEDGE:
            if tuple_dims:
                width, depth, height = tuple_dims
            else:
                width = self._dimension_or_error(
                    self._find_dimension(text, width_labels, default_unit), "wedge width"
                )
                depth = self._dimension_or_error(
                    self._find_dimension(text, depth_labels, default_unit), "wedge depth"
                )
                height = self._dimension_or_error(
                    self._find_dimension(text, height_labels, default_unit), "wedge height"
                )
            return [FeatureSpec(
                id="wedge_main",
                type=PrimitiveType.WEDGE,
                name="Wedge",
                parameters={
                    "width": self._parameter("width", width),
                    "depth": self._parameter("depth", depth),
                    "height": self._parameter("height", height),
                    "xmin": self._parameter("xmin", (0.0, width[1])),
                    "zmin": self._parameter("zmin", (0.0, height[1])),
                    "xmax": self._parameter("xmax", width),
                    "zmax": self._parameter("zmax", height),
                },
                operation=OperationType.UNION,
            )]

        return self._raise(f"Unsupported primitive type: {primitive.value}")

    @staticmethod
    def _raise(message: str):
        raise ValueError(message)

    def _generate_name(self, primitive: PrimitiveType, text: str) -> str:
        """Generate a descriptive stable name."""
        names = {
            PrimitiveType.BOX: "Box",
            PrimitiveType.CYLINDER: "Pipe" if re.search(r"\b(pipe|tube)\b", text) else "Cylinder",
            PrimitiveType.SPHERE: "Sphere",
            PrimitiveType.CONE: "Conical Part",
            PrimitiveType.TORUS: "Ring",
            PrimitiveType.WEDGE: "Wedge",
        }
        return names.get(primitive, "Part")

def parse_natural_language(description: str, use_llm: bool = False, **kwargs) -> ParseResult:
    """Main entry point for parsing natural language to PartSpec."""
    unit_system = kwargs.pop("unit_system", UnitSystem.MM)
    try:
        if isinstance(unit_system, str):
            unit_system = UnitSystem(unit_system.strip().lower())
        else:
            unit_system = UnitSystem(unit_system)
    except (ValueError, TypeError):
        return ParseResult(success=False, error="Choose a supported unit system: mm, cm, in, or m.")

    if use_llm:
        engine = NLPEngine(**kwargs)
        return engine.parse(description, unit_system=unit_system)

    parser = RuleBasedParser()
    return parser.parse(description, unit_system=unit_system)
