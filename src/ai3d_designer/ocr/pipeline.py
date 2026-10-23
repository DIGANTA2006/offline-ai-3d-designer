"""Conservative OCR for uploaded engineering drawings.

This module extracts text and recognizable annotations; it does not infer a full
parametric solid from an arbitrary drawing. OCR and parsed dimensions must be
reviewed before any geometry is manufactured.
"""
from __future__ import annotations

import io
import math
import os
import re
import shutil
from pathlib import Path
from typing import Any

MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 4
MAX_IMAGE_PIXELS = 24_000_000
SUPPORTED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/bmp",
    "image/tiff",
    "image/webp",
}
UNIT_PATTERN = r"(?:millimeters?|millimetres?|mm|centimeters?|centimetres?|cm|inches?|inch|in|meters?|metres?|m)"
NUMBER_PATTERN = r"(?:\d+(?:\.\d+)?|\.\d+)"
TRIPLET_PATTERN = re.compile(
    rf"(?<![\w.])(?P<a>{NUMBER_PATTERN})\s*(?P<ua>{UNIT_PATTERN})?\s*[x×]\s*"
    rf"(?P<b>{NUMBER_PATTERN})\s*(?P<ub>{UNIT_PATTERN})?\s*[x×]\s*"
    rf"(?P<c>{NUMBER_PATTERN})\s*(?P<uc>{UNIT_PATTERN})?(?![\w.])",
    re.IGNORECASE,
)
LENGTH_PATTERN = re.compile(
    rf"(?<![\w.])(?P<value>{NUMBER_PATTERN})\s*(?P<unit>{UNIT_PATTERN})\b",
    re.IGNORECASE,
)
THREAD_PATTERN = re.compile(
    r"\b(?:M\s*\d+(?:\.\d+)?(?:\s*[x×]\s*\d+(?:\.\d+)?)?|"
    r"\d+\s*-\s*\d+\s*(?:UNC|UNF|UNEF|UN))\b",
    re.IGNORECASE,
)
FIT_PATTERN = re.compile(r"\b[A-Z]{1,2}\d{1,2}\s*/\s*[a-z]{1,2}\d{1,2}\b")
SURFACE_PATTERN = re.compile(r"\b(?:Ra|Rz|Rq)\s*[=:]?\s*\d+(?:\.\d+)?\s*(?:µm|um|μm)?", re.IGNORECASE)
TOLERANCE_PATTERN = re.compile(
    rf"(?:±\s*{NUMBER_PATTERN}\s*(?:{UNIT_PATTERN})?|"
    rf"\+\s*/\s*-\s*{NUMBER_PATTERN}\s*(?:{UNIT_PATTERN})?|"
    rf"\+\s*{NUMBER_PATTERN}\s*/\s*-\s*{NUMBER_PATTERN}\s*(?:{UNIT_PATTERN})?)",
    re.IGNORECASE,
)
MATERIAL_PATTERN = re.compile(
    r"\b(stainless\s+steel|mild\s+steel|carbon\s+steel|aluminium|aluminum|"
    r"brass|bronze|copper|titanium|ABS|PLA|PETG|nylon|polycarbonate|acetal|POM)\b",
    re.IGNORECASE,
)
VIEW_PATTERN = re.compile(
    r"\b(front|top|side|left|right|bottom|rear|back|isometric|iso|section\s*[A-Z]?\s*[-–]?\s*[A-Z]?)\s+view\b",
    re.IGNORECASE,
)


class OCRInputError(ValueError):
    """The uploaded file is unsupported, corrupt, or too large."""


class OCRUnavailableError(RuntimeError):
    """A required OCR runtime dependency is not installed."""


class OCRProcessingError(RuntimeError):
    """The OCR runtime failed to process a valid upload."""


def _tesseract_executable() -> str | None:
    explicit = os.environ.get("TESSERACT_CMD", "").strip()
    if explicit:
        return explicit if Path(explicit).is_file() else None
    return shutil.which("tesseract")


def is_ocr_available() -> bool:
    """True only when image OCR dependencies and the Tesseract binary are available."""
    if not _tesseract_executable():
        return False
    try:
        import fitz  # noqa: F401
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False


def _unit_to_mm(unit: str | None, fallback: str = "mm") -> float:
    normalized = (unit or fallback).strip().lower()
    if normalized.startswith(("millimeter", "millimetre")) or normalized == "mm":
        return 1.0
    if normalized.startswith(("centimeter", "centimetre")) or normalized == "cm":
        return 10.0
    if normalized in {"in", "inch", "inches"}:
        return 25.4
    if normalized in {"m", "meter", "meters", "metre", "metres"}:
        return 1000.0
    return 1.0


def extract_drawing_annotations(raw_text: str) -> dict[str, Any]:
    """Extract explicit dimensional/engineering tokens without inventing missing data."""
    text = raw_text[:50_000]
    triplets: list[dict[str, Any]] = []
    excluded_spans: list[tuple[int, int]] = []
    for match in TRIPLET_PATTERN.finditer(text):
        units = [match.group("ua"), match.group("ub"), match.group("uc")]
        common_unit = next((unit for unit in reversed(units) if unit), "mm")
        values = [
            float(match.group(name)) * _unit_to_mm(units[index] or common_unit)
            for index, name in enumerate(("a", "b", "c"))
        ]
        triplets.append({
            "valuesMm": values,
            "unit": "mm",
            "raw": match.group(0),
            "source": "explicit_triplet",
        })
        excluded_spans.append(match.span())

    def inside_triplet(span: tuple[int, int]) -> bool:
        return any(span[0] < end and span[1] > start for start, end in excluded_spans)

    linear: list[dict[str, Any]] = []
    for match in LENGTH_PATTERN.finditer(text):
        if inside_triplet(match.span()):
            continue
        value = float(match.group("value"))
        unit = match.group("unit").lower()
        linear.append({
            "valueMm": value * _unit_to_mm(unit),
            "rawValue": value,
            "unit": unit,
            "raw": match.group(0),
        })

    diameters = [
        {"raw": match.group(0), "value": float(match.group("value")), "unit": (match.group("unit") or "mm").lower()}
        for match in re.finditer(
            rf"(?:Ø|⌀|\b(?:DIA|DIAMETER)\s*)\s*(?P<value>{NUMBER_PATTERN})\s*(?P<unit>{UNIT_PATTERN})?",
            text,
            re.IGNORECASE,
        )
    ]
    radii = [
        {"raw": match.group(0), "value": float(match.group("value")), "unit": (match.group("unit") or "mm").lower()}
        for match in re.finditer(
            rf"\bR\s*(?P<value>{NUMBER_PATTERN})\s*(?P<unit>{UNIT_PATTERN})?",
            text,
            re.IGNORECASE,
        )
    ]
    tolerances = [{"raw": m.group(0)} for m in TOLERANCE_PATTERN.finditer(text)]
    fits = list(dict.fromkeys(re.sub(r"\s+", "", m.group(0)) for m in FIT_PATTERN.finditer(text)))
    threads = list(dict.fromkeys(re.sub(r"\s+", "", m.group(0)).upper() for m in THREAD_PATTERN.finditer(text)))
    surfaces = list(dict.fromkeys(re.sub(r"\s+", "", m.group(0)) for m in SURFACE_PATTERN.finditer(text)))
    materials = list(dict.fromkeys(m.group(1).strip() for m in MATERIAL_PATTERN.finditer(text)))
    views = list(dict.fromkeys(re.sub(r"\s+", " ", m.group(0)).strip() for m in VIEW_PATTERN.finditer(text)))

    annotations: list[dict[str, str]] = []
    for kind, values in (
        ("dimension_triplet", [item["raw"] for item in triplets]),
        ("linear_dimension", [item["raw"] for item in linear]),
        ("diameter", [item["raw"] for item in diameters]),
        ("radius", [item["raw"] for item in radii]),
        ("tolerance", [item["raw"] for item in tolerances]),
        ("fit", fits),
        ("thread", threads),
        ("surface_finish", surfaces),
        ("material", materials),
        ("view", views),
    ):
        annotations.extend({"type": kind, "text": value} for value in values)

    return {
        "dimensions": {
            "triplets": triplets,
            "linear": linear,
            "diameters": diameters,
            "radii": radii,
        },
        "tolerances": tolerances,
        "fits": fits,
        "material": materials[0] if materials else None,
        "surfaceFinish": surfaces[0] if surfaces else None,
        "threads": threads,
        "views": views,
        "annotations": annotations,
    }


def _run_tesseract(image: Any) -> tuple[str, float]:
    """Run OCR with a timeout and return recognized text plus normalized word confidence."""
    try:
        import pytesseract
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        raise OCRUnavailableError("Install pytesseract and Pillow to enable drawing OCR.") from exc
    executable = _tesseract_executable()
    if not executable:
        raise OCRUnavailableError("Tesseract OCR executable was not found. Install tesseract-ocr on the service host.")
    pytesseract.pytesseract.tesseract_cmd = executable
    try:
        data = pytesseract.image_to_data(
            image,
            config="--psm 11",
            output_type=pytesseract.Output.DICT,
            timeout=10,
        )
    except Exception as exc:
        raise OCRProcessingError(f"Tesseract could not read this drawing: {exc}") from exc
    words = [str(item).strip() for item in data.get("text", []) if str(item).strip()]
    confidences: list[float] = []
    for value in data.get("conf", []):
        try:
            numeric = float(value)
            if numeric >= 0 and math.isfinite(numeric):
                confidences.append(min(100.0, numeric))
        except (TypeError, ValueError):
            continue
    return " ".join(words), (sum(confidences) / len(confidences) / 100.0 if confidences else 0.0)


def extract_drawing_text(file_bytes: bytes, file_name: str, mime_type: str) -> dict[str, Any]:
    """Extract text from a bounded PDF or raster image and return explicit annotations."""
    if not file_bytes:
        raise OCRInputError("The uploaded drawing is empty.")
    if len(file_bytes) > MAX_DOCUMENT_BYTES:
        raise OCRInputError("Drawing exceeds the 5 MiB OCR input limit.")
    suffix = Path(file_name).suffix.lower()
    normalized_mime = (mime_type or "").split(";", 1)[0].strip().lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise OCRInputError("Unsupported drawing type. Upload a PDF, PNG, JPEG, BMP, TIFF, or WebP file.")
    if normalized_mime not in SUPPORTED_MIME_TYPES:
        raise OCRInputError("The uploaded content type is not supported for drawing OCR.")

    try:
        import fitz
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError as exc:
        raise OCRUnavailableError("Install PyMuPDF and Pillow to enable PDF/image drawing OCR.") from exc

    page_text: list[str] = []
    confidence_scores: list[float] = []
    pages_processed = 0
    try:
        if suffix == ".pdf":
            if not file_bytes.startswith(b"%PDF-"):
                raise OCRInputError("The file extension says PDF but the content is not a PDF document.")
            try:
                document = fitz.open(stream=file_bytes, filetype="pdf")
            except Exception as exc:
                raise OCRInputError(f"Could not open the PDF: {exc}") from exc
            with document:
                if document.page_count < 1:
                    raise OCRInputError("PDF has no pages.")
                if document.page_count > MAX_PDF_PAGES:
                    raise OCRInputError(f"PDF has {document.page_count} pages; the OCR limit is {MAX_PDF_PAGES}.")
                for page in document:
                    pages_processed += 1
                    page_width_px = page.rect.width * (200 / 72)
                    page_height_px = page.rect.height * (200 / 72)
                    if page_width_px * page_height_px > MAX_IMAGE_PIXELS:
                        raise OCRInputError("A rendered PDF page exceeds the 24-megapixel OCR safety limit.")
                    native_text = page.get_text("text").strip()
                    if len(native_text) >= 12:
                        page_text.append(native_text)
                        confidence_scores.append(1.0)
                        continue
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(200 / 72, 200 / 72), alpha=False)
                    image = Image.open(io.BytesIO(pixmap.tobytes("png")))
                    if image.width * image.height > MAX_IMAGE_PIXELS:
                        raise OCRInputError("A rendered PDF page exceeds the 24-megapixel OCR safety limit.")
                    page_result, confidence = _run_tesseract(ImageOps.exif_transpose(image).convert("RGB"))
                    if page_result.strip():
                        page_text.append(page_result)
                    confidence_scores.append(confidence)
        else:
            try:
                image = Image.open(io.BytesIO(file_bytes))
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise OCRInputError("Image exceeds the 24-megapixel OCR safety limit.")
                image.verify()
                image = Image.open(io.BytesIO(file_bytes))
            except OCRInputError:
                raise
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
                raise OCRInputError(f"Could not decode image file: {exc}") from exc
            if getattr(image, "n_frames", 1) > 1:
                raise OCRInputError("Animated/multi-frame images are not supported. Export the required frame as a single image.")
            pages_processed = 1
            text, confidence = _run_tesseract(ImageOps.exif_transpose(image).convert("RGB"))
            page_text.append(text)
            confidence_scores.append(confidence)
    except (OCRInputError, OCRUnavailableError, OCRProcessingError):
        raise
    except Exception as exc:
        raise OCRProcessingError(f"Drawing OCR failed: {exc}") from exc

    raw_text = "\n".join(part for part in page_text if part.strip()).strip()[:50_000]
    if not raw_text:
        raise OCRProcessingError("No drawing text was recognized. Try a clearer, higher-resolution scan or enter dimensions manually.")
    metadata = extract_drawing_annotations(raw_text)
    confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
    return {
        **metadata,
        "rawText": raw_text,
        "confidence": max(0.0, min(1.0, float(confidence))),
        "pageCount": pages_processed or 1,
        "needsReview": True,
        "limitations": [
            "OCR text and dimensions are machine-extracted and may contain recognition errors.",
            "OCR does not infer a complete 3D shape from drawing views or certify dimensions, fits, tolerances, or manufacturing readiness.",
            "Review all extracted values and model assumptions before CAD generation or manufacturing.",
        ],
    }
