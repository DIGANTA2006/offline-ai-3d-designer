"""Timeout defaults leave time for the extractor's conservative fallback."""

from ai3d_designer.drawing_to_cad import extraction


def test_drawing_vision_default_timeout_fits_inside_web_ocr_deadline(monkeypatch):
    monkeypatch.delenv("DRAWING_VISION_TIMEOUT_SECONDS", raising=False)
    assert extraction.VISION_DEFAULT_TIMEOUT_SECONDS == 25.0
    assert extraction._vision_timeout_seconds() == 25.0
    assert extraction.VISION_MAX_RESPONSE_TOKENS == 2048


def test_drawing_vision_timeout_environment_override_is_honored(monkeypatch):
    monkeypatch.setenv("DRAWING_VISION_TIMEOUT_SECONDS", "30")
    assert extraction._vision_timeout_seconds() == 30.0
