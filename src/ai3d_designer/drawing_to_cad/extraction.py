"""Vision-assisted blueprint extraction with dimension grounding and safe fallback."""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
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
VISION_MAX_SIDE = 2048
VISION_DEFAULT_TIMEOUT_SECONDS = 25.0
VISION_MAX_RESPONSE_TOKENS = 2048
logger = logging.getLogger(__name__)
DIAMETER_MARKS = {"ø", "Ø", "Φ", "φ", "⌀", "∅"}
DIMENSION_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?P<prefix>[ØøΦφ⌀∅Rr])\s*(?P<number>\d{1,7}(?:[.,]\d{1,4})?)"
    r"(?P<unit>\s*(?:mm|cm|inches?|inch|in|deg|°|\"))?(?![A-Za-z0-9])",
    re.IGNORECASE,
)
ANGLE_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9.])(?P<number>\d{1,4}(?:[.,]\d{1,4})?)\s*(?:°|deg)(?![A-Za-z])",
    re.IGNORECASE,
)
UNIT_MULTIPLIER = {"mm": 1.0, "millimeter": 1.0, "millimeters": 1.0, "millimetre": 1.0, "millimetres": 1.0, "cm": 10.0, "centimeter": 10.0, "centimeters": 10.0, "centimetre": 10.0, "centimetres": 10.0, "in": 25.4, "inch": 25.4, "inches": 25.4, "m": 1000.0, "meter": 1000.0, "meters": 1000.0, "metre": 1000.0, "metres": 1000.0}


class DimensionToken(BaseModel):
    id: str
    raw: str
    value: float = Field(gt=0, le=1_000_000)
    kind: str
    page: int | None = Field(default=None, ge=1, le=MAX_BLUEPRINT_PAGES)
    x: float | None = None
    y: float | None = None


class ExtractionResult(BaseModel):
    blueprint: Blueprint
    source: str
    source_pages: int
    dimension_inventory: list[DimensionToken]
    cleared_fields: list[str]
    vector_geometry: list[dict[str, Any]] = Field(default_factory=list, max_length=250)
    vision_model: str | None = None


class VisionBackend(Protocol):
    async def chat_json(self, images: list[bytes], system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class RenderedDrawing:
    images: list[bytes]
    source: str
    page_texts: list[str]
    vector_geometry: list[dict[str, Any]]


SYSTEM_PROMPT = """You are a cautious mechanical drawing interpreter. Return only one JSON object matching the provided Blueprint schema.
Inspect the supplied drawing IMAGE PIXELS directly, not only its OCR text. Identify front, top, side, section, detail and isometric views across all supplied pages.
The OCR DIMENSION INVENTORY is independent text evidence. It is NOT a whitelist for visual_measurements. Read every clearly visible dimension callout from the image itself, including diameter/radius symbols, linear dimensions, angles, hole counts, thread callouts and tolerances. Put each readable callout in visual_measurements with a short dimension_name, exact raw_callout, numeric value when legible, its printed unit (or unknown), kind, associated feature only when clear, source_page, source_view, normalized image region (x/y/width/height from 0 to 1 when locatable), and an honest low/medium/high self-assessed confidence encoded from 0 to 1. The confidence is not calibrated. Always return visual_measurements as an array (empty when none). Every candidate must include all schema fields: dimension_name, raw_callout, value (number or null), unit, kind, feature (string or null), source_page, source_view, confidence, region (object or null), verification_status="vision_only", and ocr_inventory_id=null. The server overwrites verification fields after deterministic comparison.
If a callout is partially unreadable or ambiguous, preserve its legible raw text, set value=null when the number is uncertain, and explain the uncertainty in warnings. Never invent a number, infer scale from pixel size, or derive an unstated dimension.
Keep visual_measurements separate from CAD geometry. Populate numeric fields in base_sketch/features only with values that are independently corroborated by the OCR DIMENSION INVENTORY and have the correct dimension kind. A value seen only in the image must remain a visual_measurements candidate with verification_status=vision_only; deterministic code will mark a candidate ocr_value_match only when its value, kind, unit and source page agree with OCR evidence. Never treat model self-confidence as confirmation.
All dimensions in CAD geometry are normalized to millimetres. If a drawing's unit is unclear, do not assume mm; set the candidate unit to unknown and add a warning. Do not populate geometry fields from unknown-unit values.
Select a supported primary_body_type only when the views and text support it. Treat a named PCD/BCD value as a pitch-circle diameter, so pitch_radius is PCD / 2, but keep the original PCD as a named visual measurement. A visual count of repeated holes may be reported as a count candidate; do not invent dimensions.
Ignore page numbers, logos and watermarks. For a labelled scalloped flange or circular-gullet sprocket, use radial_cutout_pattern only when the outer radius/diameter, gullet radius, root radius (or explicit cutter-centre radius) and repeat count are grounded in OCR evidence. Distinguish the tooth/gullet count from mounting-hole count. This creates circular scallops, not involute gear teeth; clearly say so in warnings. For true involute gears, unspecified/non-circular tooth profiles, sheet-metal bends/flanges, threads, welds, or other unsupported geometry, add a concise unsupported_geometry entry. Never substitute a smooth flange for a toothed sprocket.
Defaults will be applied by deterministic code and marked for review. Put uncertainties in warnings and set needs_review=true."""


def _json_schema_unsupported(status_code: int, body: str) -> bool:
    """Recognize provider errors that specifically reject strict JSON-schema response format."""
    if status_code not in {400, 422}:
        return False
    message = body.lower()
    format_reference = any(token in message for token in ("response_format", "json_schema", "json schema", "strict"))
    rejection = any(token in message for token in ("unsupported", "not supported", "unknown parameter", "unrecognized", "invalid", "not allowed", "does not support"))
    return format_reference and rejection


def _vision_timeout_seconds() -> float:
    raw = (os.getenv("DRAWING_VISION_TIMEOUT_SECONDS") or str(VISION_DEFAULT_TIMEOUT_SECONDS)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError("DRAWING_VISION_TIMEOUT_SECONDS must be a number between 1 and 600") from exc
    if not 1 <= value <= 600:
        raise ValueError("DRAWING_VISION_TIMEOUT_SECONDS must be between 1 and 600")
    # Never let a deployment override exceed the Vercel OCR request budget.
    # Historical Railway values may still be set to 110 seconds.
    if value > 30:
        logger.warning(
            "DRAWING_VISION_TIMEOUT_SECONDS=%.1f exceeds the web OCR budget; capping vision deadline at 30 seconds",
            value,
        )
        return 30.0
    return value


class OpenAICompatibleVision:
    """OpenAI Chat Completions adapter; prefers strict schema, retries JSON mode only on schema-format rejection."""

    def __init__(self, base_url: str, model: str, api_key: str | None, timeout: float = VISION_DEFAULT_TIMEOUT_SECONDS):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    async def chat_json(
        self, images: list[bytes], system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        import copy

        strict_schema = copy.deepcopy(schema)

        def make_strict(node: Any) -> None:
            if isinstance(node, dict):
                properties = node.get("properties")
                if isinstance(properties, dict):
                    node["required"] = list(properties.keys())
                    node["additionalProperties"] = False
                node.pop("default", None)
                node.pop("examples", None)
                node.pop("exclusiveMinimum", None)
                node.pop("exclusiveMaximum", None)
                for value in node.values():
                    make_strict(value)
            elif isinstance(node, list):
                for value in node:
                    make_strict(value)

        make_strict(strict_schema)
        user_content: list[dict[str, Any]] = [{"type": "text", "text": user}]
        for image_bytes in images:
            encoded = base64.b64encode(image_bytes).decode("ascii")
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{encoded}", "detail": "high"},
                }
            )
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": VISION_MAX_RESPONSE_TOKENS,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "engineering_drawing_blueprint",
                    "strict": True,
                    "schema": strict_schema,
                },
            },
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            status_code = int(getattr(response, "status_code", 200))
            if _json_schema_unsupported(status_code, str(getattr(response, "text", ""))):
                upstream_error = str(getattr(response, "text", ""))[:1200]
                logger.warning(
                    "Vision provider rejected strict response_format=json_schema (HTTP %s, model=%s): %s; retrying once with response_format=json_object",
                    status_code,
                    self.model,
                    upstream_error,
                )
                payload["response_format"] = {"type": "json_object"}
                payload["messages"][0]["content"] = (
                    system
                    + "\n\nCompatibility fallback: output exactly one valid JSON object. "
                    + "Do not use Markdown fences or explanatory text."
                )
                response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                status_code = int(getattr(response, "status_code", 200))
            if status_code >= 400:
                upstream_error = str(getattr(response, "text", "")).strip()[:1500]
                logger.error(
                    "Vision provider request failed (HTTP %s, model=%s, endpoint=%s): %s",
                    status_code,
                    self.model,
                    f"{self.base_url}/chat/completions",
                    upstream_error or "(empty upstream error body)",
                )
                response.raise_for_status()
        choices = response.json().get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("Vision API returned no completion choices")
        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        answer = message.get("content") if isinstance(message, dict) else None
        if isinstance(answer, list):
            answer = "".join(part.get("text", "") for part in answer if isinstance(part, dict))
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Vision API returned no JSON message content")
        parsed = json.loads(answer)
        if not isinstance(parsed, dict):
            raise ValueError("Vision API result must be a JSON object")
        return parsed

class OllamaVision:
    """JSON-schema-constrained Ollama chat adapter for a vision-capable model."""

    def __init__(self, base_url: str, model: str, timeout: float = VISION_DEFAULT_TIMEOUT_SECONDS):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def chat_json(
        self, images: list[bytes], system: str, user: str, schema: dict[str, Any]
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
                    "images": [base64.b64encode(image).decode("ascii") for image in images],
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


def get_vision_backend() -> VisionBackend | None:
    """Only call a vision model when an endpoint is explicitly configured."""
    provider = (os.getenv("DRAWING_VISION_PROVIDER") or "ollama").strip().lower()
    if provider == "ollama":
        base_url = (os.getenv("DRAWING_VISION_URL") or os.getenv("OLLAMA_URL") or "").strip()
    elif provider in {"openai", "openai_compatible", "openai-compatible"}:
        # Drawings are client data. A hosted model receives them only after the owner enables it
        # explicitly (plan T02/T84, OPEN-08). Blocked by default: OCR-only extraction continues.
        if os.getenv("DRAWING_VISION_ALLOW_HOSTED", "").strip().lower() not in {"1", "true", "yes"}:
            return None
        base_url = os.getenv("DRAWING_VISION_URL", "").strip()
    else:
        raise ValueError("DRAWING_VISION_PROVIDER must be 'ollama' or 'openai_compatible'")
    if not base_url:
        return None
    model = (os.getenv("DRAWING_VISION_MODEL") or os.getenv("VISION_MODEL") or "qwen2.5vl:7b").strip()
    if not model:
        return None
    timeout = _vision_timeout_seconds()
    if provider == "ollama":
        return OllamaVision(base_url, model, timeout=timeout)
    api_key = os.getenv("DRAWING_VISION_API_KEY", "").strip() or None
    return OpenAICompatibleVision(base_url, model, api_key, timeout=timeout)


def _prepare_vision_image(image_bytes: bytes) -> bytes:
    """Resize and compress drawings to high-quality JPEG for vision transport.

    The 2048 px maximum side preserves callout detail; 4:4:4 chroma sampling and
    quality 92 avoid the softness associated with aggressively compressed text.
    """
    with Image.open(io.BytesIO(image_bytes)) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        image.thumbnail((VISION_MAX_SIDE, VISION_MAX_SIDE), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=92, optimize=True, progressive=True, subsampling=0)
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
                vector_geometry: list[dict[str, Any]] = []
                vector_pages = 0
                scale = 180 / 72
                for page_number, page in enumerate(document, start=1):
                    words = page.get_text("words")
                    if len(words) >= 5:
                        vector_pages += 1
                    texts.append(page.get_text("text")[:20_000])
                    # Treat vector paths as geometric evidence, not as fully understood features.
                    for drawing in page.get_drawings():
                        rect = drawing.get("rect")
                        if rect is None:
                            continue
                        width, height = float(rect.width), float(rect.height)
                        if width < 2.0 or height < 2.0:
                            continue
                        items = drawing.get("items", [])
                        curve_count = sum(1 for item in items if item and item[0] == "c")
                        rect_count = sum(1 for item in items if item and item[0] == "re")
                        aspect = width / height if height else 0.0
                        kind = None
                        if 0.92 <= aspect <= 1.08 and curve_count >= 4:
                            kind = "circle_candidate"
                        elif rect_count >= 1:
                            kind = "rectangle_candidate"
                        if kind and len(vector_geometry) < 250:
                            vector_geometry.append(
                                {
                                    "page": page_number,
                                    "kind": kind,
                                    "center_x_pt": round((float(rect.x0) + float(rect.x1)) / 2, 3),
                                    "center_y_pt": round((float(rect.y0) + float(rect.y1)) / 2, 3),
                                    "width_pt": round(width, 3),
                                    "height_pt": round(height, 3),
                                    "curve_segments": curve_count,
                                }
                            )
                    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                    pages.append(_prepare_vision_image(pixmap.tobytes("png")))
                source = "vector_pdf" if vector_pages else "scanned_pdf"
                return RenderedDrawing(pages, source, texts, vector_geometry)
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
            png = _prepare_vision_image(buffer.getvalue())
    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError(f"Could not decode the image for visual inspection: {exc}") from exc
    return RenderedDrawing([png], "raster", [""], [])



def _has_callout_label(raw: str, labels: tuple[str, ...]) -> bool:
    """Return true only when a normalized raw callout contains a whole semantic label."""
    normalized = re.sub(r"\s+", " ", str(raw or "")).strip()
    for label in labels:
        escaped = re.escape(label.strip()).replace(r"\ ", r"\s+")
        if re.search(r"(?<![A-Za-z0-9])" + escaped + r"(?![A-Za-z0-9])", normalized, re.IGNORECASE):
            return True
    return False


def _semantic_callout_key(raw: str) -> str:
    """Keep distinct measurement meanings even when their numeric value and kind match."""
    label_groups = (
        ("ring_outer_diameter", ("ring outer diameter", "outer ring diameter", "step outer diameter")),
        ("ring_inner_diameter", ("ring inner diameter", "inner ring diameter", "step inner diameter")),
        ("outer_diameter", ("outer diameter", "outside diameter", "outer dia", "od")),
        ("inner_bore_diameter", ("inner bore diameter", "bore diameter", "bore dia", "bore", "inner diameter", "id")),
        ("pitch_circle_diameter", ("pitch circle diameter", "pitch circle dia", "bolt circle diameter", "pcd", "bcd")),
        ("hole_diameter", ("hole diameter", "hole dia", "dia of holes", "hole")),
        ("outer_radius", ("outer radius", "outside radius")),
        ("root_radius", ("root circle radius", "root radius", "dedendum radius")),
        ("gullet_radius", ("gullet radius", "radial cutout radius", "cutout radius", "notch radius")),
        ("wall_thickness", ("wall thickness", "sheet thickness")),
        ("fillet_radius", ("fillet radius", "edge radius")),
        ("pocket_depth", ("pocket depth", "slot depth")),
        ("hole_depth", ("hole depth", "drill depth")),
        ("ring_depth", ("ring depth", "recess depth", "step depth")),
        ("pocket_length", ("pocket length", "slot length")),
        ("pocket_width", ("pocket width", "slot width")),
        ("width", ("overall width", "width")),
        ("length", ("overall length", "length")),
        ("thickness", ("overall thickness", "plate thickness", "thickness", "thk", "height")),
    )
    for key, labels in label_groups:
        if _has_callout_label(raw, labels):
            return key
    return re.sub(r"\s+", " ", str(raw or "")).strip().casefold()


def _dimension_inventory(
    raw_text: str, dimension_data: dict[str, Any], page_count: int
) -> list[DimensionToken]:
    """Build a millimetre inventory from the existing parser's explicit annotations."""
    found: list[DimensionToken] = []
    keys: dict[tuple[str, float, str, int | None], DimensionToken] = {}

    def add(
        value: Any,
        raw: str,
        kind: str,
        page: int | None = None,
        x: float | None = None,
        y: float | None = None,
    ) -> None:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return
        if not (0 < numeric <= 1_000_000):
            return
        normalized_kind = kind.lower()
        semantic_key = _semantic_callout_key(raw)
        normalized_page = max(1, min(page, MAX_BLUEPRINT_PAGES)) if page is not None else None
        key = (normalized_kind, round(numeric, 4), semantic_key, normalized_page)
        if key in keys:
            existing = keys[key]
            if len(raw) > len(existing.raw):
                existing.raw = raw
            if existing.page is None and page is not None:
                existing.page = max(1, min(page, MAX_BLUEPRINT_PAGES))
                existing.x = x
                existing.y = y
            return
        token = DimensionToken(
            id=f"D{len(found) + 1}",
            raw=raw[:100] if raw else f"{numeric:g}",
            value=numeric,
            kind=normalized_kind,
            page=max(1, min(page, MAX_BLUEPRINT_PAGES)) if page is not None else None,
            x=x,
            y=y,
        )
        keys[key] = token
        found.append(token)

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
                unit = str(entry.get("unit") or "mm").lower()
                if entry.get("valueMm") is not None:
                    # valueMm is already normalized; never multiply it by the source unit again.
                    value = entry.get("valueMm")
                else:
                    value = entry.get("value")
                    if value is not None:
                        value = float(value) * UNIT_MULTIPLIER.get(unit, 1.0)
                add(value, str(entry.get("raw", value)), kind)

    # Add labelled values such as OD 155, PCD 98 and hole dia 8.
    # Labels are strong semantic evidence and also let the half-PCD grounding rule work.
    for labels, kind in (
        (["outer diameter", "outside diameter", "outer dia", "od"], "diameter"),
        (["outer radius", "outside radius", "root radius", "root circle radius", "dedendum radius", "gullet radius", "radial cutout radius", "cutout radius", "notch radius", "pitch circle radius", "bolt circle radius", "pitch radius"], "radius"),
        (["inner bore diameter", "bore diameter", "bore dia", "inner diameter", "id"], "diameter"),
        (["pitch circle diameter", "pitch circle dia", "pcd", "bcd", "bolt circle diameter"], "diameter"),
        (["hole diameter", "hole dia", "dia of holes"], "diameter"),
        (["ring outer diameter", "outer ring diameter", "step outer diameter"], "diameter"),
        (["ring inner diameter", "inner ring diameter", "step inner diameter"], "diameter"),
        (["fillet radius", "edge radius"], "radius"),
        (["pocket depth", "slot depth", "hole depth", "drill depth", "ring depth", "recess depth", "step depth"], "linear"),
        (["pocket length", "slot length"], "linear"),
        (["pocket width", "slot width"], "linear"),
        (["width", "overall width"], "linear"),
        (["length", "overall length"], "linear"),
        (["overall thickness", "plate thickness", "thickness", "thk", "height"], "linear"),
        (["wall thickness", "sheet thickness"], "linear"),
    ):
        if kind == "radius":
            for single_label in labels:
                value = _labeled_radius_value(raw_text, [single_label])
                if value is not None:
                    add(value, f"{single_label} R{value:g}", kind)
            continue
        callout = _labeled_callout(raw_text, labels)
        if callout is not None:
            value, raw_callout = callout
            add(value, raw_callout, kind)

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

    for match in ANGLE_TOKEN_RE.finditer(raw_text[:50_000]):
        add(float(match.group("number").replace(",", ".")), match.group(0).strip(), "angle")

    # Prefer exact page attribution from a vector PDF's text layer where available.
    page_texts = dimension_data.get("pageTexts", [])
    if isinstance(page_texts, list):
        labels = (
            (["outer diameter", "outside diameter", "outer dia", "od"], "diameter"),
            (["outer radius", "outside radius", "root radius", "root circle radius", "dedendum radius", "gullet radius", "radial cutout radius", "cutout radius", "notch radius", "pitch circle radius", "bolt circle radius", "pitch radius"], "radius"),
            (["inner bore diameter", "bore diameter", "bore dia", "inner diameter", "id"], "diameter"),
            (["pitch circle diameter", "pitch circle dia", "pcd", "bcd", "bolt circle diameter"], "diameter"),
            (["hole diameter", "hole dia", "dia of holes"], "diameter"),
            (["ring outer diameter", "outer ring diameter", "step outer diameter"], "diameter"),
            (["ring inner diameter", "inner ring diameter", "step inner diameter"], "diameter"),
            (["fillet radius", "edge radius"], "radius"),
            (["pocket depth", "slot depth", "hole depth", "drill depth", "ring depth", "recess depth", "step depth"], "linear"),
            (["pocket length", "slot length"], "linear"),
            (["pocket width", "slot width"], "linear"),
            (["width", "overall width"], "linear"),
            (["length", "overall length"], "linear"),
            (["overall thickness", "plate thickness", "thickness", "thk", "height"], "linear"),
            (["wall thickness", "sheet thickness"], "linear"),
        )
        for page_index, page_text in enumerate(page_texts[:MAX_BLUEPRINT_PAGES], start=1):
            if not isinstance(page_text, str):
                continue
            for match in DIMENSION_TOKEN_RE.finditer(page_text[:20_000]):
                raw = match.group(0).strip()
                prefix = match.group("prefix")
                unit = (match.group("unit") or "").strip().lower()
                number = float(match.group("number").replace(",", "."))
                kind = "diameter" if prefix in DIAMETER_MARKS else "radius" if prefix and prefix.lower() == "r" else "linear"
                if unit:
                    number *= UNIT_MULTIPLIER.get(unit, 1.0)
                add(number, raw, kind, page=page_index)
            for match in ANGLE_TOKEN_RE.finditer(page_text[:20_000]):
                add(float(match.group("number").replace(",", ".")), match.group(0).strip(), "angle", page=page_index)
            for field_labels, kind in labels:
                if kind == "radius":
                    for single_label in field_labels:
                        value = _labeled_radius_value(page_text, [single_label])
                        if value is not None:
                            add(value, f"{single_label} R{value:g}", kind, page=page_index)
                    continue
                callout = _labeled_callout(page_text, list(field_labels))
                if callout is not None:
                    value, raw_callout = callout
                    add(value, raw_callout, kind, page=page_index)

    return found[:200]


def _inventory_message(
    inventory: list[DimensionToken], page_count: int, vector_geometry: list[dict[str, Any]]
) -> str:
    if inventory:
        lines = "\n".join(
            f'{token.id}: "{token.raw}" => {token.kind}, {token.value:g} mm-equivalent, page {token.page if token.page is not None else "unknown"}'
            for token in inventory[:200]
        )
    else:
        lines = "(no dimension tokens were grounded; leave all dimension fields null)"
    vector_counts: dict[str, int] = {}
    for item in vector_geometry:
        key = f"page {item.get('page', '?')} {item.get('kind', 'path')}"
        vector_counts[key] = vector_counts.get(key, 0) + 1
    geometry_summary = (
        "\n".join(f"{key}: {count}" for key, count in sorted(vector_counts.items()))
        if vector_counts else "(no simple vector circle/rectangle candidates were detected)"
    )
    vector_details = (
        "\n".join(
            f"P{item.get('page', '?')} V{index + 1}: {item.get('kind', 'path')}, "
            f"center=({item.get('center_x_pt')}, {item.get('center_y_pt')}) pt, "
            f"size=({item.get('width_pt')} x {item.get('height_pt')}) pt, "
            f"curve_segments={item.get('curve_segments', 0)}"
            for index, item in enumerate(vector_geometry[:80])
        )
        if vector_geometry else "(no detailed vector candidates)"
    )
    return (
        f"Drawing has {page_count} page(s). Classify all supplied views together.\n"
        f"OCR DIMENSION INVENTORY — these are text-extraction results. Only values independently corroborated here may populate numeric CAD geometry fields:\n"
        f"{lines}\n"
        f"IMPORTANT: inspect the image pixels independently and list readable callouts missing from this inventory in visual_measurements. Do not omit them just because OCR missed them. Visual-only values are review candidates, never trusted geometry.\n"
        f"VECTOR PDF GEOMETRY CANDIDATES — path sizes are PDF points, not millimetres; use as spatial clues only:\n"
        f"Summary:\n{geometry_summary}\nFirst candidate details:\n{vector_details}\n\n"
        f"Return Blueprint JSON. Add unsupported_geometry rather than approximating unsupported features."
    )


def _is_grounded(
    value: float | None,
    inventory: list[DimensionToken],
    allowed_kinds: set[str] | None = None,
    allow_half_diameter: bool = False,
    required_labels: tuple[str, ...] = (),
    excluded_labels: tuple[str, ...] = (),
) -> bool:
    """Match a value, unit-kind and (for named fields) its semantic drawing callout."""
    if value is None:
        return True
    if abs(value) < 1e-6:
        return True
    for token in inventory:
        if required_labels and not _has_callout_label(token.raw, required_labels):
            continue
        if excluded_labels and _has_callout_label(token.raw, excluded_labels):
            continue
        kind_matches = allowed_kinds is None or token.kind in allowed_kinds
        if kind_matches and abs(value - token.value) <= max(0.02, abs(token.value) * 0.001):
            return True
        if (
            allow_half_diameter
            and token.kind == "diameter"
            and abs(2 * value - token.value) <= max(0.02, abs(token.value) * 0.001)
        ):
            return True
    return False


def ground_blueprint(bp: Blueprint, inventory: list[DimensionToken]) -> list[str]:
    """Clear fields lacking matching value, dimension kind and semantic callout evidence."""
    cleared: list[str] = []
    sketch = bp.base_sketch
    sketch_rules: dict[str, tuple[set[str], tuple[str, ...], tuple[str, ...]]] = {
        "outer_diameter": (
            {"diameter"},
            ("outer diameter", "outside diameter", "outer dia", "od"),
            ("ring outer diameter", "outer ring diameter", "step outer diameter"),
        ),
        "inner_bore_diameter": (
            {"diameter"},
            ("inner bore diameter", "bore diameter", "bore dia", "bore", "inner diameter", "id"),
            ("ring inner diameter", "inner ring diameter", "step inner diameter"),
        ),
        "width": (
            {"linear"},
            ("overall width", "width"),
            ("slot width", "pocket width", "hole width"),
        ),
        "length": (
            {"linear"},
            ("overall length", "length"),
            ("slot length", "pocket length", "hole spacing", "bolt spacing"),
        ),
        "thickness": (
            {"linear"},
            ("overall thickness", "plate thickness", "thickness", "thk", "height"),
            ("wall thickness", "sheet thickness", "rib thickness", "web thickness", "pocket depth", "hole depth"),
        ),
        "wall_thickness": (
            {"linear"},
            ("wall thickness", "sheet thickness"),
            (),
        ),
    }
    for name, (allowed_kinds, required_labels, excluded_labels) in sketch_rules.items():
        value = getattr(sketch, name)
        grounded = _is_grounded(
            value,
            inventory,
            allowed_kinds=allowed_kinds,
            required_labels=required_labels,
            excluded_labels=excluded_labels,
        )
        if name == "outer_diameter" and value is not None and not grounded:
            grounded = _is_grounded(
                value / 2,
                inventory,
                allowed_kinds={"radius"},
                required_labels=("outer radius", "outside radius"),
            )
        if not grounded:
            setattr(sketch, name, None)
            cleared.append(f"base_sketch.{name}={value:g}")

    # Do not accept arbitrary model-invented profile coordinates. Each coordinate
    # must correspond to an explicit drawing measurement or the profile is blocked.
    if sketch.points:
        points_are_grounded = True
        for point in sketch.points:
            if len(point) != 2:
                points_are_grounded = False
                break
            for axis, coordinate in enumerate(point):
                if bp.primary_body_type == "revolved_profile" and axis == 0:
                    allowed_kinds = {"radius"}
                    allow_half_diameter = True
                else:
                    allowed_kinds = {"linear"}
                    allow_half_diameter = False
                if not _is_grounded(
                    abs(coordinate),
                    inventory,
                    allowed_kinds=allowed_kinds,
                    allow_half_diameter=allow_half_diameter,
                ):
                    points_are_grounded = False
                    break
            if not points_are_grounded:
                break
        if not points_are_grounded:
            sketch.points = None
            cleared.append("base_sketch.points=profile coordinates were not grounded to the correct dimension types")

    feature_kinds = {
        "diameter": {"diameter"},
        "inner_diameter": {"diameter"},
        "root_radius": {"radius"},
        "length": {"linear"},
        "width": {"linear"},
        "depth": {"linear"},
        "radius": {"radius"},
    }
    for index, feature in enumerate(bp.features):
        for name, allowed_kinds in feature_kinds.items():
            value = getattr(feature, name)
            required_labels: tuple[str, ...] = ()
            excluded_labels: tuple[str, ...] = ()
            if name == "diameter" and feature.type in {"through_hole", "hole_pattern", "circular_pattern_cut"}:
                required_labels = ("hole diameter", "hole dia", "dia of holes", "hole")
            elif name == "diameter" and feature.type == "ring_step":
                required_labels = ("ring outer diameter", "outer ring diameter", "step outer diameter")
            elif name == "inner_diameter" and feature.type == "ring_step":
                required_labels = ("ring inner diameter", "inner ring diameter", "step inner diameter")
            elif name == "root_radius":
                required_labels = ("root radius", "root circle radius", "dedendum radius")
            elif name == "radius" and feature.type == "radial_cutout_pattern":
                required_labels = ("gullet radius", "radial cutout radius", "cutout radius", "notch radius")
            elif name == "radius" and feature.type == "fillet":
                required_labels = ("fillet radius", "edge radius")
            elif name == "length" and feature.type == "pocket":
                required_labels = ("pocket length", "slot length")
            elif name == "width" and feature.type == "pocket":
                required_labels = ("pocket width", "slot width")
            elif name == "depth" and feature.type == "pocket":
                required_labels = ("pocket depth", "slot depth")
            elif name == "depth" and feature.type in {"through_hole", "hole_pattern", "circular_pattern_cut"}:
                required_labels = ("hole depth", "drill depth")
            elif name == "depth" and feature.type == "ring_step":
                required_labels = ("ring depth", "recess depth", "step depth")
            if not _is_grounded(
                value,
                inventory,
                allowed_kinds=allowed_kinds,
                required_labels=required_labels,
                excluded_labels=excluded_labels,
            ):
                if value is not None:
                    setattr(feature, name, None)
                    cleared.append(f"features[{index}].{name}={value:g}")
        value = feature.pitch_radius
        if not _is_grounded(
            value,
            inventory,
            allowed_kinds={"radius"},
            allow_half_diameter=True,
            required_labels=(
                "pitch circle diameter",
                "pitch circle dia",
                "pcd",
                "bcd",
                "bolt circle diameter",
                "pitch circle radius",
                "bolt circle radius",
                "pitch radius",
            ),
        ):
            if value is not None:
                feature.pitch_radius = None
                cleared.append(f"features[{index}].pitch_radius={value:g}")
        if feature.angular_pitch is not None and not _is_grounded(feature.angular_pitch, inventory, allowed_kinds={"angle"}):
            value = feature.angular_pitch
            feature.angular_pitch = None
            cleared.append(f"features[{index}].angular_pitch={value:g}")
        if feature.start_angle and not _is_grounded(feature.start_angle, inventory, allowed_kinds={"angle"}):
            value = feature.start_angle
            feature.start_angle = 0.0
            cleared.append(f"features[{index}].start_angle={value:g}")
        x_value = feature.x
        if x_value and not _is_grounded(x_value, inventory, allowed_kinds={"linear"}):
            feature.x = 0.0
            cleared.append(f"features[{index}].x={x_value:g}")
        y_value = feature.y
        if y_value and not _is_grounded(y_value, inventory, allowed_kinds={"linear"}):
            feature.y = 0.0
            cleared.append(f"features[{index}].y={y_value:g}")

    return cleared


def reconcile_visual_measurements(bp: Blueprint, inventory: list[DimensionToken]) -> None:
    """Mark visual callouts as OCR-corroborated only on deterministic same-page agreement."""
    length_units_to_mm = {
        "mm": 1.0,
        "cm": 10.0,
        "m": 1000.0,
        "in": 25.4,
        "inch": 25.4,
    }
    inventory_kinds = {
        "linear": "linear",
        "diameter": "diameter",
        "radius": "radius",
        "angle": "angle",
    }

    for candidate in bp.visual_measurements:
        # Model-supplied verification fields and inventory IDs are never trusted.
        candidate.verification_status = "vision_only"
        candidate.ocr_inventory_id = None
        if candidate.value is None:
            continue

        if candidate.kind == "angle":
            if candidate.unit not in {"deg", "°"}:
                continue
            normalized_value = candidate.value
        elif candidate.kind in {"linear", "diameter", "radius"} and candidate.unit in length_units_to_mm:
            normalized_value = candidate.value * length_units_to_mm[candidate.unit]
        else:
            # Counts, unknown types and unknown units cannot be cross-checked safely.
            continue

        expected_kind = inventory_kinds.get(candidate.kind)
        if expected_kind is None:
            continue
        tolerance = max(0.02, abs(normalized_value) * 0.001)
        match = next(
            (
                token
                for token in inventory
                if token.kind == expected_kind
                and (token.page == candidate.source_page or (token.page is None and len(bp.source_pages) == 1 and candidate.source_page == 1))
                and abs(token.value - normalized_value) <= tolerance
            ),
            None,
        )
        if match is not None:
            candidate.verification_status = "ocr_value_match"
            candidate.ocr_inventory_id = match.id


def _labeled_radius_value(text: str, labels: list[str]) -> float | None:
    """Read an explicitly labelled radius such as 'root radius R63.4'."""
    label_group = "(?:" + "|".join(re.escape(label) for label in labels) + ")"
    number = r"(\d{1,7}(?:[.,]\d{1,4})?)"
    match = re.search(
        rf"(?<![A-Za-z]){label_group}(?![A-Za-z])\s*(?:[:=]|is|of)?\s*R\s*{number}\b",
        text[:50_000],
        re.IGNORECASE,
    )
    if not match:
        match = re.search(
            rf"(?<![A-Za-z])R\s*{number}\s*(?:mm\s*)?{label_group}(?![A-Za-z])",
            text[:50_000],
            re.IGNORECASE,
        )
    return float(match.group(1).replace(",", ".")) if match else None


def _labeled_callout(text: str, labels: list[str]) -> tuple[float, str] | None:
    """Return the normalized value and the actual matched source callout label."""
    label_group = "(?:" + "|".join(re.escape(label) for label in labels) + ")"
    pattern = re.compile(
        rf"(?<![A-Za-z])(?P<label>{label_group})(?![A-Za-z])\s*(?:[:=]|is|of)?\s*[ØøΦ⌀∅]?\s*(?P<number>\d{{1,7}}(?:[.,]\d{{1,4}})?)\s*(?P<unit>mm|cm|inches?|inch|in)?\b",
        re.IGNORECASE,
    )
    source = text[:50_000]

    def ring_scoped(match: re.Match[str]) -> bool:
        # "RING OUTER DIAMETER" is not the parent body's "OUTER DIAMETER".
        label = match.group("label")
        preceding = source[:match.start("label")]
        return not label.lower().startswith("ring ") and bool(
            re.search(r"\bring\s*$", preceding, re.IGNORECASE)
        )

    for match in pattern.finditer(source):
        if ring_scoped(match):
            continue
        raw_number = match.group("number")
        raw_unit = match.group("unit") or "mm"
        value = float(raw_number.replace(",", ".")) * UNIT_MULTIPLIER.get(raw_unit.lower(), 1.0)
        return value, match.group(0).strip()

    # Also support reverse forms such as "Ø155 OD" while respecting ring scope.
    reverse = re.compile(
        rf"[ØøΦ⌀∅]\s*(?P<number>\d{{1,7}}(?:[.,]\d{{1,4}})?)\s*(?:mm\s*)?(?P<label>{label_group})(?![A-Za-z])",
        re.IGNORECASE,
    )
    for match in reverse.finditer(source):
        if ring_scoped(match):
            continue
        value = float(match.group("number").replace(",", "."))
        return value, match.group(0).strip()

    return None


def _labeled_value(text: str, labels: list[str]) -> float | None:
    """Compatibility wrapper for callers that need only the normalized numeric value."""
    callout = _labeled_callout(text, labels)
    return callout[0] if callout is not None else None


def _heuristic_blueprint(raw_text: str, inventory: list[DimensionToken]) -> Blueprint:
    """No vision configured: only use explicit labels; never infer a shape from random OCR numbers."""
    text = raw_text.lower()
    if re.search(r"\b(sprocket|scalloped flange)\b", text):
        # Explicitly dimensioned circular gulleys are supported; this is not involute gear geometry.
        outer_diameter = _labeled_value(raw_text, ["outer diameter", "outside diameter", "outer dia", "od"])
        outer_radius = _labeled_radius_value(raw_text, ["outer radius", "outside radius"])
        if outer_diameter is None and outer_radius is not None:
            outer_diameter = 2 * outer_radius
        bore = _labeled_value(raw_text, ["inner bore diameter", "bore diameter", "bore dia", "inner diameter", "id"])
        thickness = _labeled_value(raw_text, ["overall thickness", "plate thickness", "thickness", "thk", "height"])
        root_radius = _labeled_radius_value(raw_text, ["root radius", "root circle radius", "dedendum radius"])
        gullet_radius = _labeled_radius_value(raw_text, ["gullet radius", "radial cutout radius", "cutout radius", "notch radius"])
        teeth_match = re.search(r"\b(\d{1,3})\s*(?:equally spaced\s*)?(?:teeth|tooth|gullets|notches)\b", text)
        features: list[dict[str, Any]] = []
        unsupported: list[str] = []
        if outer_diameter and root_radius and gullet_radius and teeth_match:
            features.append({
                "type": "radial_cutout_pattern",
                "count": int(teeth_match.group(1)),
                "radius": gullet_radius,
                "root_radius": root_radius,
            })
        else:
            unsupported.append(
                "Scalloped perimeter needs a labelled outer diameter/outer radius, root radius, gullet radius and tooth/gullet count; inspect the drawing and complete these fields before export."
            )
        pcd = _labeled_value(raw_text, ["pitch circle diameter", "pitch circle dia", "pcd", "bcd", "bolt circle diameter"])
        hole_diameter = _labeled_value(raw_text, ["hole diameter", "hole dia", "hole Ø", "dia of holes"])
        holes_match = re.search(r"\b(\d{1,3})\s*(?:x\s*)?(?:equally spaced\s*)?(?:holes|hole|positions)\b", text)
        if pcd and hole_diameter and holes_match:
            features.append({
                "type": "hole_pattern",
                "count": int(holes_match.group(1)),
                "pitch_radius": pcd / 2,
                "diameter": hole_diameter,
                "start_angle": 0.0,
            })
        return Blueprint(
            part_name="scalloped flange",
            primary_body_type="rotational_flange",
            base_sketch={
                "profile": "circle",
                "outer_diameter": outer_diameter,
                "inner_bore_diameter": bore,
                "thickness": thickness,
            },
            features=features,
            unsupported_geometry=unsupported,
            warnings=[
                "Vision model is not configured. Only explicitly labelled dimensions were used; this scalloped profile does not represent an involute gear tooth."
            ],
            needs_review=True,
        )

    if re.search(r"\b(gear|involute|toothed|serration|serrated)\b", text):
        return Blueprint(
            part_name="unresolved toothed part",
            primary_body_type=None,
            unsupported_geometry=[
                "Involute gear teeth or non-circular tooth profiles are not represented by radial circular cutouts; a specified tooth/profile definition is required."
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

    outer_diameter = _labeled_value(raw_text, ["outer diameter", "outside diameter", "outer dia", "od"]) if body == "rotational_flange" else None
    inner_bore = _labeled_value(raw_text, ["inner bore diameter", "bore diameter", "bore dia", "inner diameter", "id"]) if body == "rotational_flange" else None
    thickness = _labeled_value(raw_text, ["overall thickness", "plate thickness", "thickness", "thk", "height"])
    wall = _labeled_value(raw_text, ["wall thickness", "sheet thickness"]) if body == "sheet_enclosure" else None
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


async def _extract_with_vision(
    vision: VisionBackend,
    images: list[bytes],
    inventory: list[DimensionToken],
    pages: int,
    vector_geometry: list[dict[str, Any]],
) -> Blueprint:
    prompt = _inventory_message(inventory, pages, vector_geometry)
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
    inventory_data = {**dimension_data, "pageTexts": rendered.page_texts}
    inventory = _dimension_inventory(raw_text, inventory_data, len(rendered.images))
    if vision is None:
        vision = get_vision_backend()

    vision_model: str | None = None
    if vision is not None:
        try:
            # Bound the entire vision attempt, including schema-validation retries, so
            # the conservative fallback returns before the outer web request expires.
            vision_timeout = max(0.01, float(getattr(vision, "timeout", VISION_DEFAULT_TIMEOUT_SECONDS)))
            blueprint = await asyncio.wait_for(
                _extract_with_vision(vision, rendered.images, inventory, len(rendered.images), rendered.vector_geometry),
                timeout=vision_timeout,
            )
            vision_model = getattr(vision, "model", type(vision).__name__)
        except (httpx.HTTPError, TimeoutError, asyncio.TimeoutError, ValueError, ValidationError) as exc:
            if isinstance(exc, httpx.HTTPStatusError):
                body = str(getattr(exc.response, "text", "")).strip()[:1500]
                status = getattr(exc.response, "status_code", "unknown")
                detail = f"HTTP {status}: {body or str(exc)}"
            elif isinstance(exc, (httpx.TimeoutException, TimeoutError, asyncio.TimeoutError)):
                request = getattr(exc, "request", None)
                endpoint = str(getattr(request, "url", "(URL unavailable)"))
                detail = f"{type(exc).__name__} after {getattr(vision, 'timeout', VISION_DEFAULT_TIMEOUT_SECONDS):g}s at {endpoint}"
            else:
                detail = f"{type(exc).__name__}: {str(exc)[:1200]}"
            logger.warning("Drawing vision extraction failed for model %s: %s", getattr(vision, "model", type(vision).__name__), detail)
            blueprint = _heuristic_blueprint(raw_text, inventory)
            blueprint.warnings.append(
                f"Vision extraction failed ({detail[:420]}); a conservative text-only fallback was used."
            )
            blueprint.needs_review = True
    else:
        blueprint = _heuristic_blueprint(raw_text, inventory)

    blueprint.source_pages = list(range(1, len(rendered.images) + 1))
    reconcile_visual_measurements(blueprint, inventory)
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
        source_pages=len(rendered.images),
        dimension_inventory=inventory,
        cleared_fields=cleared,
        vector_geometry=rendered.vector_geometry,
        vision_model=vision_model,
    )
