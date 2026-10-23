"""FastAPI OCR/generation endpoint checks using the production CAD engine."""

import pytest
from fastapi import HTTPException

import main as cad_service


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
