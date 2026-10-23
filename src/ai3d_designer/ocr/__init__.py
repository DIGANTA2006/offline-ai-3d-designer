"""Engineering drawing OCR package (optional system-level Tesseract dependency)."""
from .pipeline import (
    OCRInputError,
    OCRProcessingError,
    OCRUnavailableError,
    extract_drawing_annotations,
    extract_drawing_text,
    is_ocr_available,
)

__all__ = [
    "OCRInputError",
    "OCRProcessingError",
    "OCRUnavailableError",
    "extract_drawing_annotations",
    "extract_drawing_text",
    "is_ocr_available",
]
