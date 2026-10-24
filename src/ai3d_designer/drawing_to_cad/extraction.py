"""Vision-assisted blueprint extraction with dimension grounding and safe fallback."""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import pymupdf
from PIL import Image, ImageOps
from pydantic import BaseModel, Field, ValidationError

from ai3d_designer.drawing_to_cad.blueprint import Blueprint, apply_defaults, lint

MAX_BLUEPRINT_PAGES = 4
VISION_MAX_SIDE = 1600
DIAMETER_MARKS = {"ø", "Ø", "Φ", "φ", "⌀", "∅"}
DIMENSION_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?P<prefix>[ØøΦφ⌀∅Rr])\s*(?P<number>\d{1,7}(?:[.,]\d{1,4})?)"
    r"(?P<unit>\s*(?:mm|cm|inches?|inch|in|deg|°|\"))?(?![A-Za-z0-9])",
    re.IGNORECASE,
)
UNIT_MULTIPLIER = {"mm": 1.0, "cm": 10.0, "in": 25.4, "inch": 25.4, "inches": 25.4}


class DimensionToken(BaseModel):
    id: str
    raw: str
    value: float = Field(gt=0, le=1_000_000)
    kind: str
    page: int = Field(ge=1, le=MAX_BLUEPRINT_PAGES)
    x: float | None = None
    y: float | None = None


class ExtractionResult(BaseModel):
    blueprint: Blueprint
    source: str
    source_pages: int
    dimension_inventory: list[DimensionToken]
    cleared_fields: list[str]
    vision_model: str | None = None


class VisionBackend(Protocol):
    async def chat_json(self, images_png: list[bytes], system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class RenderedDrawing:
    images_png: list[bytes]
    source: str
    page_texts: list[str]


SYSTEM_PROMPT = """You are a cautious mechanical drawing interpreter. Return only one JSON object matching the provided Blueprint schema.
All dimensions are millimetres. Select a supported primary_body_type only when the views and text support it.
Use only values from DIMENSION INVENTORY for numeric dimensions. If a value cannot be tied to the inventory, set that field to null; do not estimate it.
Treat a named PCD/BCD value as a pitch-circle diameter, so pitch_radius is PCD / 2. A visual count of repeated holes may be used for count, but do not invent dimensions.
Ignore title blocks, page numbers, logos and watermarks. Identify front, top, side and section views across the supplied pages.
For teeth, involute gears, sprocket tooth forms, sheet-metal bends/flanges, threads, welds, or other unsupported geometry, add a concise unsupported_geometry entry. Never substitute a smooth flange for a toothed sprocket.
Defaults will be applied by deterministic code and marked for review. Put uncertainties in warnings and set needs_review=true."""


class OllamaVision:
    """JSON-schema-constrained Ollama chat adapter for a vision-capable model."""

    def __init__(self, base_url: str, model: str, timeout: float = 38.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def chat_json(
        self, images_png: list[bytes], system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "stream": False,
            "format": schema,
            "options": {"temperature": 0, "num_ctx": 8192},
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": user,
                    "images": [base64.b64encode(image).decode("ascii") for image in images_png],
                },
            ],
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
        result = response.json()
        message = result.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ValueError("Vision backend returned no JSON message content")
        parsed = json.loads(message["content"])
        if not isinstance(parsed, dict):
            raise ValueError("Vision backend result must be a JSON object")
        return parsed


def get_vision_backend() -> OllamaVision | None:
    """Only call a vision model when an endpoint is explicitly configured."""
    base_url = (os.getenv("DRAWING_VISION_URL") or os.getenv("OLLAMA_URL") or "").strip()
    if not base_url:
        return None
    model = (os.getenv("DRAWING_VISION_MODEL") or os.getenv("VISION_MODEL") or "qwen2.5vl:7b").strip()
    if not model:
        return None
    return OllamaVision(base_url, model)


def _fit_png(image_bytes: bytes) -> bytes:
    with Image.open(io.BytesIO(image_bytes)) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        image.thumbnail((VISION_MAX_SIDE, VISION_MAX_SIDE))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()


def _render_drawing(data: bytes, file_name: str, mime_type: str) -> RenderedDrawing:
    suffix = os.path.splitext(file_name)[1].lower()
    normalized_mime = mime_type.split(";", 1)[0].lower().strip()
    if suffix == ".pdf" or normalized_mime == "application/pdf" or data.startswith(b"%PDF"):
        try:
            with pymupdf.open(stream=data, filetype="pdf") as document:
                if document.page_count < 1:
                    raise ValueError("PDF has no pages")
                if document.page_count > MAX_BLUEPRINT_PAGES:
                    raise ValueError(f"Drawing pack exceeds the {MAX_BLUEPRINT_PAGES}-page blueprint review limit")
                pages: list[bytes] = []
                texts: list[str] = []
                vector_pages = 0
                scale = 144 / 72
                for page in document:
                    words = page.get_text("words")
                    if len(words) >= 5:
                        vector_pages += 1
                    texts.append(page.get_text("text")[:20_000])
                    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                    pages.append(_fit_png(pixmap.tobytes("png")))
                source = "vector_pdf" if vector_pages else "scanned_pdf"
                return RenderedDrawing(pages, source, texts)
        except Exception as exc:
            if isinstance(exc, ValueError):
                raise
            raise ValueError(f"Could not render the PDF for visual inspection: {exc}") from exc

    try:
        with Image.open(io.BytesIO(data)) as image:
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("Animated/multi-frame images are not supported")
            image = ImageOps.exif_transpose(image).convert("RGB")
            if image.width * image.height > 24_000_000:
                raise ValueError("Drawing image exceeds the 24-megapixel processing limit")
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            png = _fit_png(buffer.getvalue())
    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError(f"Could not decode the image for visual inspection: {exc}") from exc
    return RenderedDrawing([png], "raster", [""])


def _dimension_inventory(
    raw_text: str, dimension_data: dict[str, Any], page_count: int
) -> list[DimensionToken]:
    """Build a millimetre inventory from the existing parser's explicit annotations."""
    found: list[DimensionToken] = []
    keys: set[tuple[str, float]] = set()

    def add(value: Any, raw: str, kind: str, page: int = 1, x: float | None = None, y: float | None = None) -> None:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return
        if not (0 < numeric <= 1_000_000):
            return
        normalized_kind = kind.lower()
        key = (normalized_kind, round(numeric, 4))
        if key in keys:
            return
        keys.add(key)
        found.append(
            DimensionToken(
                id=f"D{len(found) + 1}",
                raw=raw[:100] if raw else f"{numeric:g}",
                value=numeric,
                kind=normalized_kind,
                page=max(1, min(page, MAX_BLUEPRINT_PAGES)),
                x=x,
                y=y,
            )
        )

    dimensions = dimension_data.get("dimensions", {})
    if not isinstance(dimensions, dict):
        dimensions = {}
    for triplet in dimensions.get("triplets", []) if isinstance(dimensions.get("triplets"), list) else []:
        if not isinstance(triplet, dict):
            continue
        values = triplet.get("valuesMm")
        if isinstance(values, list):
            for value in values[:3]:
                add(value, str(triplet.get("raw", value)), "linear")
    for kind, property_names in (
        ("linear", ("linear",)),
        ("diameter", ("diameters",)),
        ("radius", ("radii",)),
    ):
        for property_name in property_names:
            entries = dimensions.get(property_name, [])
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                value = entry.get("valueMm", entry.get("value"))
                unit = str(entry.get("unit") or "mm").lower()
                if kind != "linear" and value is not None:
                    value = float(value) * UNIT_MULTIPLIER.get(unit, 1.0)
                add(value, str(entry.get("raw", value)), kind)

    # Add explicitly marked Ø/R/angle/unit-bearing values from native text and OCR.
    # Bare title-block numbers are deliberately not treated as dimensions.
    for match in DIMENSION_TOKEN_RE.finditer(raw_text[:50_000]):
        raw = match.group(0).strip()
        prefix = match.group("prefix")
        unit = (match.group("unit") or "").strip().lower()
        number = float(match.group("number").replace(",", "."))
        if prefix in DIAMETER_MARKS:
            kind = "diameter"
        elif prefix and prefix.lower() == "r":
            kind = "radius"
        elif unit in {"°", "deg"}:
            kind = "angle"
        else:
            # A unit-bearing linear value is explicit; avoid adding plain numbers.
            if not unit:
                continue
            kind = "linear"
            number *= UNIT_MULTIPLIER.get(unit, 1.0)
        add(number, raw, kind)

    return found[:200]


def _inventory_message(inventory: list[DimensionToken], page_count: int) -> str:
    if inventory:
        lines = "\n".join(
            f'{token.id}: "{token.raw}" => {token.kind}, {token.value:g} mm-equivalent, page {token.page}'
            for token in inventory[:200]
        )
    else:
        lines = "(no dimension tokens were grounded; leave all dimension fields null)"
    return (
        f"Drawing has {page_count} page(s). Classify all supplied views together.\n"
        f"DIMENSION INVENTORY — only these numeric measurements may populate blueprint dimensions:\n"
        f"{lines}\n\nReturn Blueprint JSON. Add unsupported_geometry rather than approximating unsupported features."
    )


def _is_grounded(value: float | None, inventory: list[DimensionToken], allow_half_diameter: bool = False) -> bool:
    if value is None:
        return True
    if abs(value) < 1e-6:
        return True
    for token in inventory:
        if abs(value - token.value) <= max(0.02, abs(token.value) * 0.001):
            return True
        if allow_half_diameter and token.kind == "diameter" and abs(2 * value - token.value) <= max(0.02, abs(token.value) * 0.001):
            return True
    return False


def ground_blueprint(bp: Blueprint, inventory: list[DimensionToken]) -> list[str]:
    """Clear dimensions that cannot be grounded in printed/recognized measurements."""
    cleared: list[str] = []
    sketch = bp.base_sketch
    for name in (
        "outer_diameter",
        "inner_bore_diameter",
        "width",
        "length",
        "thickness",
        "wall_thickness",
    ):
        value = getattr(sketch, name)
        if not _is_grounded(value, inventory):
            setattr(sketch, name, None)
            cleared.append(f"base_sketch.{name}={value:g}")

    for index, feature in enumerate(bp.features):
        for name in ("diameter", "length", "width", "depth", "radius"):
            value = getattr(feature, name)
            if not _is_grounded(value, inventory):
                setattr(feature, name, None)
                cleared.append(f"features[{index}].{name}={value:g}")
        value = feature.pitch_radius
        if not _is_grounded(value, inventory, allow_half_diameter=True):
            feature.pitch_radius = None
            cleared.append(f"features[{index}].pitch_radius={value:g}")
        if feature.angular_pitch is not None and not _is_grounded(feature.angular_pitch, inventory):
            feature.angular_pitch = None
            cleared.append(f"features[{index}].angular_pitch={value:g}")
        if feature.start_angle and not _is_grounded(feature.start_angle, inventory):
            feature.start_angle = 0.0
            cleared.append(f"features[{index}].start_angle={value:g}")
        # Absolute X/Y coordinates are not accepted as guessed millimetres.
        if feature.x and not _is_grounded(feature.x, inventory):
            feature.x = 0.0
            cleared.append(f"features[{index}].x={value:g}")
        if feature.y and not _is_grounded(feature.y, inventory):
            feature.y = 0.0
            cleared.append(f"features[{index}].y={value:g}")

    return cleared


def _labeled_value(text: str, labels: list[str]) -> float | None:
    """Return a number only when adjacent to a recognized dimension label."""
    label_group = "|".join(labels)
    pattern = re.compile(
        rf"(?:{label_group})\s*(?:[:=]|is|of)?\s*[ØøΦ⌀∅]?\s*(\d{{1,7}}(?:[.,]\d{{1,4}})?)\s*(mm|cm|inches?|inch|in)?\b",
        re.IGNORECASE,
    )
    match = pattern.search(text[:50_000])
    if not match:
        # Also support forms such as 'Ø155 OD'.
        reverse = re.compile(
            rf"[ØøΦ⌀∅]\s*(\d{{1,7}}(?:[.,]\d{{1,4}})?)\s*(?:mm\s*)?(?:{label_group})\b",
            re.IGNORECASE,
        ).search(text[:50_000])
        if not reverse:
            return None
        raw_number, raw_unit = reverse.group(1), "mm"
    else:
        raw_number, raw_unit = match.group(1), match.group(2) or "mm"
    return float(raw_number.replace(",", ".")) * UNIT_MULTIPLIER.get(raw_unit.lower(), 1.0)


def _heuristic_blueprint(raw_text: str, inventory: list[DimensionToken]) -> Blueprint:
    """No vision configured: only use explicit labels; never infer a shape from random OCR numbers."""
    text = raw_text.lower()
    if re.search(r"\b(sprocket|gear|involute|teeth|toothed|serration|serrated)\b", text):
        return Blueprint(
            part_name="unresolved toothed part",
            primary_body_type=None,
            unsupported_geometry=[
                "Sprocket/gear teeth or serrations are outside the v1 deterministic generator; a dedicated tooth/profile definition is required."
            ],
            warnings=["No vision model was configured. The image cannot be semantically interpreted from OCR text alone."],
            needs_review=True,
        )

    if re.search(r"\b(enclosure|sheet metal|housing|cabinet)\b", text):
        body = "sheet_enclosure"
        width = _labeled_value(raw_text, ["width", "overall width", "w"])
        length = _labeled_value(raw_text, ["length", "overall length", "overall long", "l"])
        profile = "rectangle"
    elif re.search(r"\b(flange|pcd|bcd|bolt circle|pitch circle)\b", text):
        body = "rotational_flange"
        width = length = None
        profile = "circle"
    elif re.search(r"\b(rectangular|rectangular plate|block|box|plate|prismatic)\b", text):
        body = "prismatic_box"
        width = _labeled_value(raw_text, ["width", "overall width", "w"])
        length = _labeled_value(raw_text, ["length", "overall length", "overall long", "l"])
        profile = "rectangle"
    else:
        return Blueprint(
            part_name="unresolved drawing",
            primary_body_type=None,
            warnings=[
                "No vision model was configured and OCR text did not identify a supported body type. Configure DRAWING_VISION_URL and DRAWING_VISION_MODEL to enable visual blueprint extraction."
            ],
            needs_review=True,
        )

    outer_diameter = _labeled_value(raw_text, ["outer diameter", "outside diameter", "outer dia", "od"])
    inner_bore = _labeled_value(raw_text, ["inner bore diameter", "bore diameter", "bore dia", "inner diameter", "id"])
    thickness = _labeled_value(raw_text, ["overall thickness", "plate thickness", "thickness", "thk", "height"])
    wall = _labeled_value(raw_text, ["wall thickness", "wall", "sheet thickness"])
    features = []
    pcd = _labeled_value(raw_text, ["pitch circle diameter", "pitch circle dia", "pcd", "bcd", "bolt circle diameter"])
    hole_diameter = _labeled_value(raw_text, ["hole diameter", "hole dia", "hole Ø", "dia of holes"])
    count_match = re.search(r"\b(\d{1,3})\s*(?:x\s*)?(?:equally spaced\s*)?(?:holes|hole|positions)\b", text)
    if pcd and hole_diameter and count_match:
        count = int(count_match.group(1))
        if 2 <= count <= 360:
            features.append(
                {
                    "type": "circular_pattern_cut",
                    "count": count,
                    "pitch_radius": pcd / 2,
                    "diameter": hole_diameter,
                    "start_angle": 0.0,
                }
            )
    sketch = {
        "profile": profile,
        "outer_diameter": outer_diameter,
        "inner_bore_diameter": inner_bore,
        "width": width,
        "length": length,
        "thickness": thickness,
        "wall_thickness": wall,
    }
    # Grounding still runs after this fallback, including every named measurement.
    return Blueprint(
        part_name="drawing part",
        primary_body_type=body,  # type: ignore[arg-type]
        base_sketch=sketch,
        features=features,
        warnings=[
            "Vision model is not configured. Only explicitly labelled dimensions were used; inspect the source and fill any blank dimensions before generating."
        ],
        needs_review=True,
    )


async def _extract_with_vision(vision: VisionBackend, images: list[bytes], inventory: list[DimensionToken], pages: int) -> Blueprint:
    prompt = _inventory_message(inventory, pages)
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            raw = await vision.chat_json(images, SYSTEM_PROMPT, prompt, Blueprint.model_json_schema())
            return Blueprint.model_validate(raw)
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == 0:
                prompt += f"\n\nYour previous output failed validation: {str(exc)[:1200]}\nReturn corrected JSON only."
    raise ValueError(f"Vision output did not satisfy the Blueprint schema: {last_error}")


async def extract_blueprint(
    file_bytes: bytes,
    file_name: str,
    mime_type: str,
    raw_text: str,
    dimension_data: dict[str, Any],
    vision: VisionBackend | None = None,
) -> ExtractionResult:
    """Render all supported pages, optionally call a VLM, and ground numeric fields."""
    rendered = await asyncio.to_thread(_render_drawing, file_bytes, file_name, mime_type)
    inventory = _dimension_inventory(raw_text, dimension_data, len(rendered.images_png))
    if vision is None:
        vision = get_vision_backend()

    vision_model: str | None = None
    if vision is not None:
        try:
            blueprint = await _extract_with_vision(vision, rendered.images_png, inventory, len(rendered.images_png))
            vision_model = getattr(vision, "model", type(vision).__name__)
        except (httpx.HTTPError, TimeoutError, ValueError, ValidationError) as exc:
            blueprint = _heuristic_blueprint(raw_text, inventory)
            blueprint.warnings.append(
                f"Vision extraction failed ({type(exc).__name__}); a conservative text-only fallback was used."
            )
            blueprint.needs_review = True
    else:
        blueprint = _heuristic_blueprint(raw_text, inventory)

    blueprint.source_pages = list(range(1, len(rendered.images_png) + 1))
    cleared = ground_blueprint(blueprint, inventory)
    defaults = apply_defaults(blueprint)
    errors, warnings = lint(blueprint)
    blueprint.warnings = list(
        dict.fromkeys(
            blueprint.warnings
            + defaults
            + warnings
            + errors
            + (["Numeric fields not grounded in drawing text were cleared: " + ", ".join(cleared)] if cleared else [])
        )
    )
    blueprint.needs_review = blueprint.needs_review or bool(cleared or defaults or errors or blueprint.unsupported_geometry)

    return ExtractionResult(
        blueprint=blueprint,
        source=rendered.source,
        source_pages=len(rendered.images_png),
        dimension_inventory=inventory,
        cleared_fields=cleared,
        vision_model=vision_model,
    )
