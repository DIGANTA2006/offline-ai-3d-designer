"""Timeout defaults and overall vision deadlines preserve conservative fallback behavior."""

import asyncio
import io

from PIL import Image

from ai3d_designer.drawing_to_cad import extraction


def test_drawing_vision_default_timeout_fits_inside_web_ocr_deadline(monkeypatch):
    monkeypatch.delenv("DRAWING_VISION_TIMEOUT_SECONDS", raising=False)
    assert extraction.VISION_DEFAULT_TIMEOUT_SECONDS == 25.0
    assert extraction._vision_timeout_seconds() == 25.0
    assert extraction.VISION_MAX_RESPONSE_TOKENS == 2048


def test_drawing_vision_timeout_environment_override_is_honored(monkeypatch):
    monkeypatch.setenv("DRAWING_VISION_TIMEOUT_SECONDS", "30")
    assert extraction._vision_timeout_seconds() == 30.0



def test_total_vision_deadline_includes_schema_retries_and_returns_fallback():
    class SlowVision:
        timeout = 0.05
        model = "test-slow"

        async def chat_json(self, *_args, **_kwargs):
            await asyncio.sleep(1.0)
            return {}

    image = Image.new("RGB", (20, 20), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    result = asyncio.run(
        extraction.extract_blueprint(
            file_bytes=buffer.getvalue(),
            file_name="test.png",
            mime_type="image/png",
            raw_text="OD 100 mm",
            dimension_data={"dimensions": {}},
            vision=SlowVision(),
        )
    )

    assert result.blueprint.needs_review is True
    assert any("TimeoutError" in warning for warning in result.blueprint.warnings)
