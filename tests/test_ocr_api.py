"""FastAPI OCR/generation endpoint checks using the production CAD engine."""

import asyncio

import pytest
from fastapi import HTTPException

import main as cad_service


@pytest.mark.parametrize("ocr_available", [True, False])
def test_health_reports_real_ocr_runtime_availability(monkeypatch, ocr_available):
    monkeypatch.setattr(cad_service, "cad_runtime_is_available", lambda: True)
    monkeypatch.setattr(cad_service, "is_ocr_available", lambda: ocr_available)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CAD_SERVICE_TOKEN", "unit-test-only-token")

    result = asyncio.run(cad_service.health())

    assert result.cadAvailable is True
    assert result.ocrAvailable is ocr_available


def test_generation_requires_user_review_before_model_creation():
    request = cad_service.GenerationRequest(
        spec=cad_service.ExtractedSpec(rawText="A 40 x 20 x 10 mm box"),
        jobId="ocr-review-check",
        userId="test-user",
        reviewed=False,
    )

    with pytest.raises(HTTPException) as exc:
        cad_service.generate_cad(request)

    assert exc.value.status_code == 409
    assert "Review the extracted text" in exc.value.detail


def test_reviewed_dimensions_generate_real_step_and_stl_exports():
    request = cad_service.GenerationRequest(
        spec=cad_service.ExtractedSpec(
            rawText="BOX 40 x 20 x 10 mm",
            confidence=0.92,
            needsReview=True,
        ),
        jobId="ocr-generation-smoke",
        userId="test-user",
        reviewed=True,
        reviewedDescription="A 40 x 20 x 10 mm box",
    )

    result = cad_service.generate_cad(request)

    assert result.success is True, result.error
    assert result.isApproximation is True
    assert result.partSpec is not None
    assert result.stepBase64 and len(result.stepBase64) > 100
    assert result.stlBase64 and len(result.stlBase64) > 100
    assert "does not certify" in (result.fitReport or "")


def test_generation_refuses_to_guess_missing_dimensions():
    request = cad_service.GenerationRequest(
        spec=cad_service.ExtractedSpec(rawText="Make a cylinder"),
        jobId="ocr-underspecified",
        userId="test-user",
        reviewed=True,
    )

    result = cad_service.generate_cad(request)

    assert result.success is False
    assert "explicit" in (result.error or "").lower()


def test_ocr_generation_does_not_infer_a_shape_from_dimensions_alone():
    request = cad_service.GenerationRequest(
        spec=cad_service.ExtractedSpec(rawText="40 x 20 x 10 mm"),
        jobId="ocr-shape-required",
        userId="test-user",
        reviewed=True,
        reviewedDescription="40 x 20 x 10 mm",
    )

    result = cad_service.generate_cad(request)

    assert result.success is False
    assert "shape explicitly" in (result.error or "").lower()
    assert "will not infer a shape" in " ".join(result.validationErrors).lower()
