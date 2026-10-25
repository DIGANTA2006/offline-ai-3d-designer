"""Regression tests for safe engineering drawing OCR extraction."""

import base64
import io

import pytest
from PIL import Image

from ai3d_designer.core.ocr.extractor import (
    DrawingOcrError,
    OcrPageResult,
    OcrRuntimeUnavailable,
    decode_base64_file,
    extract_candidates,
    extract_drawing_spec,
    is_ocr_runtime_available,
)


def test_extract_candidates_keeps_dimension_tuples_and_uncertainties_separate():
    output = extract_candidates(
        "PLATE 40 x 20 x 10 mm. HOLE Ø 5 mm. TOLERANCE ±0.1. "
        "FIT H7/g6. THREAD M6x1. MATERIAL stainless steel. SURFACE Ra 1.6 um."
    )
    assert output["dimensions"]["dimensionTriples"]
    triple = output["dimensions"]["dimensionTriples"][0]
    assert triple["values"] == [40.0, 20.0, 10.0]
    assert triple["unit"] == "mm"
    assert any(item["kind"] == "diameter" and item["value"] == 5 for item in output["dimensions"]["candidates"])
    assert "±0.1" in output["tolerances"]["numericCandidates"]
    assert "H7/g6" in output["fits"]
    assert any(item.replace(" ", "") == "M6X1" for item in output["threads"])
    assert output["materialCandidates"] == ["stainless steel"]
    assert any(value.lower().startswith("ra 1.6") for value in output["surfaceFinishCandidates"])


def test_image_ocr_pipeline_returns_reviewable_candidates_not_a_cad_claim():
    image_buffer = io.BytesIO()
    Image.new("RGB", (240, 120), "white").save(image_buffer, format="PNG")
    image_bytes = image_buffer.getvalue()

    def fake_ocr(image):
        assert image.size == (240, 120)
        return OcrPageResult(
            text="40 x 20 x 10 mm PLATE\nHOLE DIA 5 mm\nRa 1.6 um",
            confidence=0.92,
            word_count=10,
        )

    spec = extract_drawing_spec(
        image_bytes,
        "plate.png",
        "image/png",
        run_ocr=fake_ocr,
    )
    assert spec["rawText"].startswith("[Page 1]")
    assert spec["dimensions"]["pageCount"] == 1
    assert spec["dimensions"]["dimensionTriples"][0]["values"] == [40.0, 20.0, 10.0]
    assert spec["confidence"] == pytest.approx(0.92)
    assert any("provisional" in item.lower() for item in spec["annotations"])
    assert "partSpec" not in spec
    assert "CAD generation" in spec["annotations"][0]


def test_decode_base64_accepts_plain_payload_and_data_url():
    payload = b"private drawing fixture"
    encoded = base64.b64encode(payload).decode("ascii")
    assert decode_base64_file(encoded) == payload
    assert decode_base64_file(f"data:image/png;base64,{encoded}") == payload


@pytest.mark.parametrize("payload", ["", "not base64!", "data:image/png;base64"])
def test_decode_base64_rejects_invalid_payloads(payload):
    with pytest.raises(DrawingOcrError):
        decode_base64_file(payload)


def test_unsupported_mime_is_rejected_before_ocr():
    with pytest.raises(DrawingOcrError, match="supported raster image"):
        extract_drawing_spec(b"some bytes", "drawing.dwg", "application/acad", run_ocr=lambda image: OcrPageResult("", 0, 0))


def test_missing_tesseract_returns_a_clear_runtime_error(monkeypatch):
    image_buffer = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(image_buffer, format="PNG")
    monkeypatch.setattr("ai3d_designer.core.ocr.extractor.is_ocr_runtime_available", lambda: False)
    with pytest.raises(OcrRuntimeUnavailable, match="Tesseract OCR executable"):
        extract_drawing_spec(image_buffer.getvalue(), "drawing.png", "image/png")
