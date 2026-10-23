"""Tests for bounded engineering-drawing OCR and annotation extraction."""

import io

import pytest
from PIL import Image, ImageDraw, ImageFont

from ai3d_designer.ocr.pipeline import (
    MAX_DOCUMENT_BYTES,
    OCRInputError,
    extract_drawing_annotations,
    extract_drawing_text,
)


def test_extracts_explicit_dimensions_tolerances_fits_threads_and_finish():
    text = "BOX 50 x 30 x 10 mm; hole DIA 8 mm; shaft H7/g6; M8x1.25; Ra 3.2 um; +/-0.1 mm; stainless steel; Front view"
    result = extract_drawing_annotations(text)

    assert result["dimensions"]["triplets"][0]["valuesMm"] == [50, 30, 10]
    assert result["dimensions"]["diameters"][0]["value"] == 8
    assert result["fits"] == ["H7/g6"]
    assert result["threads"] == ["M8X1.25"]
    assert result["surfaceFinish"] == "Ra3.2um"
    assert result["material"].lower() == "stainless steel"
    assert any("0.1" in item["raw"] for item in result["tolerances"])
    assert any(item["type"] == "view" for item in result["annotations"])


def test_triplet_uses_explicit_common_cm_unit():
    result = extract_drawing_annotations("Part dimensions: 2 x 3 x 1 cm")
    assert result["dimensions"]["triplets"][0]["valuesMm"] == [20, 30, 10]


def test_annotation_parser_does_not_invent_dimensions():
    result = extract_drawing_annotations("Aluminium, surface finish Ra 1.6, Front view")
    assert result["dimensions"]["triplets"] == []
    assert result["dimensions"]["linear"] == []
    assert result["dimensions"]["diameters"] == []
    assert result["material"].lower() == "aluminium"


def test_rejects_unsupported_extension_before_ocr_dependency_use():
    with pytest.raises(OCRInputError, match="Unsupported drawing type"):
        extract_drawing_text(b"anything", "drawing.exe", "application/octet-stream")


def test_rejects_content_type_mismatch():
    with pytest.raises(OCRInputError, match="content type"):
        extract_drawing_text(b"%PDF-1.7", "drawing.pdf", "image/jpeg")


def test_rejects_empty_and_oversize_files():
    with pytest.raises(OCRInputError, match="empty"):
        extract_drawing_text(b"", "drawing.png", "image/png")
    with pytest.raises(OCRInputError, match="5 MiB"):
        extract_drawing_text(b"x" * (MAX_DOCUMENT_BYTES + 1), "drawing.png", "image/png")


def test_image_path_returns_text_annotations_and_review_warning(monkeypatch):
    import ai3d_designer.ocr.pipeline as pipeline

    image = Image.new("RGB", (900, 220), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 44)
    except OSError:
        font = ImageFont.load_default()
    draw.text((20, 45), "BOX 50 x 30 x 10 mm", fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    monkeypatch.setattr(pipeline, "_run_tesseract", lambda _image: ("BOX 50 x 30 x 10 mm", 0.93))
    result = pipeline.extract_drawing_text(buffer.getvalue(), "part.png", "image/png")

    assert result["rawText"] == "BOX 50 x 30 x 10 mm"
    assert result["confidence"] == pytest.approx(0.93)
    assert result["dimensions"]["triplets"][0]["valuesMm"] == [50, 30, 10]
    assert result["needsReview"] is True
    assert result["limitations"]
