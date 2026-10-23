"""Conservative OCR extraction for engineering drawing images and PDFs.

OCR output is an editable set of text/dimension candidates, not a verified
engineering model. Never treat a detected dimension as authoritative without review.
"""
from __future__ import annotations

import base64
import binascii
import io
import re
import shutil
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
from PIL import Image, ImageOps

try:
    import pytesseract
except (ImportError, OSError):
    pytesseract = None

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 3
MAX_IMAGE_PIXELS = 40_000_000
MAX_OCR_EDGE = 3000
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/tiff",
    "image/bmp",
}

_DIMENSION_RE = re.compile(
    r'(?<![A-Za-z0-9])(?P<prefix>Ø|⌀|φ|Φ|R|DIA\.?|DIAM\.?)?\s*'
    r'(?P<value>\d{1,6}(?:[.,]\d{1,4})?)\s*'
    r'(?P<unit>mm\b|cm\b|in\b|inches?\b|["″])?\s*'
    r'(?P<tolerance>±\s*\d+(?:[.,]\d+)?|'
    r'\+\s*\d+(?:[.,]\d+)?\s*/\s*-\s*\d+(?:[.,]\d+)?)?',
    re.IGNORECASE,
)
_TRIPLE_RE = re.compile(
    r'(?<![A-Za-z])(?P<a>\d+(?:[.,]\d+)?)\s*'
    r'(?:mm\s*)?[x×]\s*(?P<b>\d+(?:[.,]\d+)?)\s*'
    r'(?:mm\s*)?[x×]\s*(?P<c>\d+(?:[.,]\d+)?)\s*'
    r'(?P<unit>mm\b|cm\b|in\b|inches?\b)?',
    re.IGNORECASE,
)
_TOLERANCE_RE = re.compile(
    r'±\s*\d+(?:[.,]\d+)?|'
    r'\+\s*\d+(?:[.,]\d+)?\s*/\s*-\s*\d+(?:[.,]\d+)?',
    re.IGNORECASE,
)
_FIT_RE = re.compile(
    r'\b[A-HJ-NP-Z]{1,2}\d{1,2}\s*/\s*[a-hj-np-z]{1,2}\d{1,2}\b|'
    r'\b(?:H|h|g|f|js|JS)\d{1,2}\b'
)
_THREAD_RE = re.compile(
    r'\bM\s*\d+(?:[.,]\d+)?(?:\s*[x×]\s*\d+(?:[.,]\d+)?)?'
    r'(?:\s*[- ]\s*(?:UNC|UNF|UNEF|NPT|BSW|BSP))?\b|'
    r'\b\d+/\d+\s*-\s*\d+\s*(?:UNC|UNF|NPT)\b',
    re.IGNORECASE,
)
_MATERIAL_RE = re.compile(
    r'\b(?:stainless steel|steel|aluminium|aluminum|brass|copper|titanium|'
    r'ABS|PLA|PETG|PA6|nylon|polycarbonate)\b',
    re.IGNORECASE,
)
_VIEW_RE = re.compile(
    r'\b(?:FRONT|TOP|SIDE|BOTTOM|LEFT|RIGHT|ISOMETRIC|ISOMETRICAL|'
    r'ELEVATION|SECTION|DETAIL)(?:\s+[A-Z](?:\s*[-–]\s*[A-Z])?)?\b',
    re.IGNORECASE,
)
_SURFACE_RE = re.compile(r'\bRa\s*[=]?\s*\d+(?:[.,]\d+)?\s*(?:µm|um)?', re.IGNORECASE)


class OcrRuntimeUnavailable(RuntimeError):
    """Raised when Tesseract OCR or a required OCR dependency is missing."""


class DrawingOcrError(ValueError):
    """Raised when a drawing cannot safely be decoded or processed."""


@dataclass
class OcrPageResult:
    text: str
    confidence: float
    word_count: int


def is_ocr_runtime_available() -> bool:
    """Return true only when both the Python wrapper and Tesseract executable work."""
    if pytesseract is None or shutil.which("tesseract") is None:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def decode_base64_file(payload: str) -> bytes:
    """Decode a plain base64 payload or a data URL with a strict size limit."""
    if not isinstance(payload, str) or not payload.strip():
        raise DrawingOcrError("No file content was supplied.")
    encoded = payload.strip()
    if encoded.startswith("data:"):
        separator = encoded.find(",")
        if separator < 0:
            raise DrawingOcrError("Malformed file data URL.")
        encoded = encoded[separator + 1:]
    # Base64 expands binary data by about one third. Refuse oversized payloads
    # before allocating the decoded byte buffer.
    if len(encoded) > ((MAX_FILE_BYTES + 2) // 3) * 4 + 8:
        raise DrawingOcrError("File exceeds the 10 MiB OCR upload limit.")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DrawingOcrError("File content is not valid base64.") from exc
    if not data:
        raise DrawingOcrError("Uploaded file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise DrawingOcrError("File exceeds the 10 MiB OCR upload limit.")
    return data


def _resize_for_ocr(image: Image.Image) -> Image.Image:
    """Orient, bound pixel count, and cap very large images for predictable memory."""
    image = ImageOps.exif_transpose(image).convert("RGB")
    width, height = image.size
    if width < 2 or height < 2:
        raise DrawingOcrError("Image dimensions are too small for OCR.")
    if width * height > MAX_IMAGE_PIXELS:
        raise DrawingOcrError("Image exceeds the 40-megapixel OCR processing limit.")
    if max(width, height) > MAX_OCR_EDGE:
        ratio = MAX_OCR_EDGE / max(width, height)
        image = image.resize(
            (max(2, int(width * ratio)), max(2, int(height * ratio))),
            Image.Resampling.LANCZOS,
        )
    return image


def _render_pages(file_bytes: bytes, mime_type: str) -> list[Image.Image]:
    """Decode supported raster images or rasterize up to five PDF pages."""
    if mime_type not in ALLOWED_MIME_TYPES:
        allowed = ", ".join(sorted(ALLOWED_MIME_TYPES))
        raise DrawingOcrError(f"Unsupported MIME type. Supported types: {allowed}.")

    if mime_type == "application/pdf":
        try:
            import fitz
        except (ImportError, OSError) as exc:
            raise OcrRuntimeUnavailable("PDF OCR requires the PyMuPDF package.") from exc
        try:
            document = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as exc:
            raise DrawingOcrError(f"Could not read PDF drawing: {exc}") from exc
        try:
            if document.page_count < 1:
                raise DrawingOcrError("PDF contains no pages.")
            if document.page_count > MAX_PDF_PAGES:
                raise DrawingOcrError(f"PDF has {document.page_count} pages; OCR is limited to {MAX_PDF_PAGES} pages per request.")
            images: list[Image.Image] = []
            for page in document:
                page_width, page_height = float(page.rect.width), float(page.rect.height)
                if not np.isfinite(page_width) or not np.isfinite(page_height) or min(page_width, page_height) <= 0:
                    raise DrawingOcrError("PDF contains a page with invalid dimensions.")
                scale = min(2.5, MAX_OCR_EDGE / max(page_width, page_height))
                matrix = fitz.Matrix(scale, scale)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False, colorspace=fitz.csRGB)
                image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                images.append(_resize_for_ocr(image))
            return images
        finally:
            document.close()

    try:
        with Image.open(io.BytesIO(file_bytes)) as source:
            source.verify()
        with Image.open(io.BytesIO(file_bytes)) as source:
            return [_resize_for_ocr(source)]
    except DrawingOcrError:
        raise
    except Exception as exc:
        raise DrawingOcrError(f"Could not decode input image: {exc}") from exc


def _run_tesseract(image: Image.Image) -> OcrPageResult:
    """Run OCR once per page and reconstruct readable lines with word confidence."""
    if pytesseract is None:
        raise OcrRuntimeUnavailable("OCR Python dependency pytesseract is not installed.")
    try:
        data = pytesseract.image_to_data(
            ImageOps.autocontrast(ImageOps.grayscale(image)),
            lang="eng",
            config="--oem 1 --psm 11",
            output_type=pytesseract.Output.DICT,
            timeout=10,
        )
    except Exception as exc:
        if isinstance(exc, getattr(pytesseract, "TesseractNotFoundError", type(None))):
            raise OcrRuntimeUnavailable("Tesseract executable is not installed on the CAD service.") from exc
        raise DrawingOcrError(f"Tesseract OCR failed: {exc}") from exc

    lines: dict[tuple[int, int, int], list[str]] = {}
    confidences: list[float] = []
    for index, value in enumerate(data.get("text", [])):
        token = str(value).strip()
        if not token:
            continue
        try:
            confidence = float(data.get("conf", [])[index])
        except (ValueError, TypeError, IndexError):
            confidence = -1
        if confidence >= 0:
            confidences.append(max(0.0, min(confidence, 100.0)))
        def number(name: str) -> int:
            try:
                return int(data.get(name, [0] * (index + 1))[index])
            except (ValueError, TypeError, IndexError):
                return 0
        key = (number("block_num"), number("par_num"), number("line_num"))
        lines.setdefault(key, []).append(token)

    text = "\n".join(" ".join(words) for words in lines.values()).strip()
    confidence = (sum(confidences) / (100.0 * len(confidences))) if confidences else 0.0
    return OcrPageResult(text=text, confidence=confidence, word_count=sum(len(words) for words in lines.values()))


def _number(value: str) -> Optional[float]:
    normalized = value.replace(",", ".")
    try:
        result = float(normalized)
    except ValueError:
        return None
    return result if np.isfinite(result) else None


def _unit(value: Optional[str]) -> str:
    normalized = (value or "").strip().lower()
    if normalized == "mm":
        return "mm"
    if normalized == "cm":
        return "cm"
    if normalized in {"in", "inch", "inches", '"', "″"}:
        return "in"
    return "unspecified"


def extract_candidates(raw_text: str) -> dict:
    """Extract reviewable dimension/tolerance/thread candidates without guessing geometry."""
    dimension_candidates: list[dict] = []
    seen = set()
    for match in _DIMENSION_RE.finditer(raw_text):
        value = _number(match.group("value"))
        if value is None:
            continue
        raw = match.group(0).strip()
        prefix = (match.group("prefix") or "").strip().upper()
        kind = "diameter" if prefix in {"Ø", "⌀", "Φ", "DIA", "DIA.", "DIAM", "DIAM."} else (
            "radius" if prefix == "R" else "dimension"
        )
        entry = {
            "value": value,
            "unit": _unit(match.group("unit")),
            "kind": kind,
            "raw": raw,
            "tolerance": (match.group("tolerance") or "").strip() or None,
        }
        key = (entry["value"], entry["unit"], entry["kind"], entry["raw"])
        if key not in seen:
            seen.add(key)
            dimension_candidates.append(entry)

    triples: list[dict] = []
    for match in _TRIPLE_RE.finditer(raw_text):
        values = [_number(match.group(key)) for key in ("a", "b", "c")]
        if any(value is None for value in values):
            continue
        triples.append({
            "values": values,
            "unit": _unit(match.group("unit")),
            "raw": match.group(0).strip(),
            "interpretation": "three-number dimension tuple; confirm axis order and drawing context",
        })

    numeric_tolerances = list(dict.fromkeys(match.group(0).strip() for match in _TOLERANCE_RE.finditer(raw_text)))
    fits = list(dict.fromkeys(match.group(0).replace(" ", "") for match in _FIT_RE.finditer(raw_text)))
    threads = list(dict.fromkeys(re.sub(r"\s+", "", match.group(0)).upper() for match in _THREAD_RE.finditer(raw_text)))
    materials = list(dict.fromkeys(match.group(0).strip() for match in _MATERIAL_RE.finditer(raw_text)))
    views = [
        {"label": match.group(0).strip().upper()}
        for match in _VIEW_RE.finditer(raw_text)
    ]
    surface_finishes = list(dict.fromkeys(match.group(0).strip() for match in _SURFACE_RE.finditer(raw_text)))

    return {
        "dimensions": {"candidates": dimension_candidates, "dimensionTriples": triples},
        "tolerances": {"numericCandidates": numeric_tolerances, "fitCandidates": fits},
        "fits": fits,
        "threads": threads,
        "materialCandidates": materials,
        "views": views,
        "surfaceFinishCandidates": surface_finishes,
    }


def extract_drawing_spec(
    file_bytes: bytes,
    file_name: str,
    mime_type: str,
    run_ocr: Optional[Callable[[Image.Image], OcrPageResult]] = None,
) -> dict:
    """OCR images/PDFs into candidate text and dimensions; outputs always require review."""
    if not isinstance(file_bytes, bytes) or not file_bytes:
        raise DrawingOcrError("File content is empty.")
    if len(file_bytes) > MAX_FILE_BYTES:
        raise DrawingOcrError("File exceeds the 10 MiB OCR upload limit.")
    if not file_name or not file_name.strip():
        raise DrawingOcrError("File name is required.")
    normalized_mime = (mime_type or "").split(";", 1)[0].strip().lower()
    if normalized_mime not in ALLOWED_MIME_TYPES:
        raise DrawingOcrError("Upload a PDF or supported raster image (PNG, JPEG, WEBP, TIFF, BMP).")
    if run_ocr is None and not is_ocr_runtime_available():
        raise OcrRuntimeUnavailable(
            "OCR is not configured: install pytesseract and the Tesseract OCR executable on the CAD service."
        )

    pages = _render_pages(file_bytes, normalized_mime)
    page_results = [(index + 1, (run_ocr or _run_tesseract)(image)) for index, image in enumerate(pages)]
    raw_text = "\n\n".join(
        f"[Page {number}]\n{result.text}".strip()
        for number, result in page_results
        if result.text.strip()
    ).strip()
    word_count = sum(result.word_count for _, result in page_results)
    total_confidence_words = sum(result.confidence * result.word_count for _, result in page_results)
    confidence = total_confidence_words / word_count if word_count else 0.0
    candidates = extract_candidates(raw_text)

    annotations = [
        "OCR output is provisional: verify all values, units, tolerances, fits, datums and view associations against the original drawing before CAD generation or manufacturing."
    ]
    if not raw_text:
        annotations.append("No readable text was detected. Try a higher-resolution scan, better contrast, or a different page segmentation.")
    if not candidates["dimensions"]["candidates"]:
        annotations.append("No numeric dimension candidates were detected; the drawing is not ready for dimension-driven CAD generation.")

    return {
        "dimensions": {
            **candidates["dimensions"],
            "pageCount": len(pages),
            "sourceFileName": file_name[:240],
        },
        "tolerances": candidates["tolerances"],
        "fits": candidates["fits"],
        "material": candidates["materialCandidates"][0] if len(candidates["materialCandidates"]) == 1 else None,
        "surfaceFinish": ", ".join(candidates["surfaceFinishCandidates"]) or None,
        "threads": candidates["threads"],
        "views": [
            {"page": number, "text": result.text, "confidence": result.confidence}
            for number, result in page_results
        ],
        "annotations": annotations + [
            f"Material candidates: {', '.join(candidates['materialCandidates'])}."
        ] if candidates["materialCandidates"] else annotations,
        "confidence": max(0.0, min(float(confidence), 1.0)),
        "rawText": raw_text,
    }
