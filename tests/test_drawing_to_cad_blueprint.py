"""Regression tests for grounded structured drawing blueprints and deterministic CAD."""

import asyncio
import base64
from typing import Any

import pymupdf
import pytest

from ai3d_designer.drawing_to_cad.blueprint import (
    BaseSketch,
    Blueprint,
    Feature,
    apply_defaults,
    lint,
)
from ai3d_designer.drawing_to_cad.extraction import (
    DimensionToken,
    OpenAICompatibleVision,
    _dimension_inventory,
    _heuristic_blueprint,
    extract_blueprint,
    ground_blueprint,
)
from ai3d_designer.drawing_to_cad.generator import GeometryError, export_blueprint


def test_default_height_is_explicitly_flagged_for_review():
    blueprint = Blueprint(
        primary_body_type="rotational_flange",
        base_sketch=BaseSketch(profile="circle", outer_diameter=100),
    )

    notes = apply_defaults(blueprint)

    assert blueprint.base_sketch.thickness == 10
    assert blueprint.base_sketch.thickness_is_default is True
    assert blueprint.needs_review is True
    assert any("10 mm" in note for note in notes)


def test_grounding_clears_unlisted_dimensions_but_accepts_half_of_pcd():
    blueprint = Blueprint(
        primary_body_type="rotational_flange",
        base_sketch=BaseSketch(
            profile="circle",
            outer_diameter=100,
            inner_bore_diameter=20,
            thickness=10,
        ),
        features=[
            Feature(
                type="circular_pattern_cut",
                count=6,
                pitch_radius=40,
                diameter=8,
            )
        ],
    )
    inventory = [
        DimensionToken(id="D1", raw="OD 100", value=100, kind="diameter", page=1),
        DimensionToken(id="D2", raw="Bore 20", value=20, kind="diameter", page=1),
        DimensionToken(id="D3", raw="PCD 80", value=80, kind="diameter", page=1),
        DimensionToken(id="D4", raw="Hole 8", value=8, kind="diameter", page=1),
        DimensionToken(id="D5", raw="Thickness 10", value=10, kind="linear", page=1),
    ]

    cleared = ground_blueprint(blueprint, inventory)

    assert cleared == []
    assert blueprint.features[0].pitch_radius == 40


def test_grounding_clears_an_unrecognized_feature_size():
    blueprint = Blueprint(
        primary_body_type="rotational_flange",
        base_sketch=BaseSketch(profile="circle", outer_diameter=100, thickness=10),
        features=[Feature(type="through_hole", diameter=7.5)],
    )
    inventory = [
        DimensionToken(id="D1", raw="OD 100", value=100, kind="diameter", page=1),
        DimensionToken(id="D2", raw="THK 10", value=10, kind="linear", page=1),
    ]

    cleared = ground_blueprint(blueprint, inventory)

    assert blueprint.features[0].diameter is None
    assert any("features[0].diameter=7.5" in item for item in cleared)


def test_grounding_requires_a_dimension_of_the_correct_kind():
    blueprint = Blueprint(
        primary_body_type="rotational_flange",
        base_sketch=BaseSketch(profile="circle", outer_diameter=100, thickness=100),
    )
    inventory = [
        DimensionToken(id="D1", raw="OD 100", value=100, kind="diameter", page=1),
    ]

    cleared = ground_blueprint(blueprint, inventory)

    assert blueprint.base_sketch.outer_diameter == 100
    assert blueprint.base_sketch.thickness is None
    assert "base_sketch.thickness=100" in cleared


def test_dimension_inventory_recognizes_angle_and_labeled_pcd():
    inventory = _dimension_inventory(
        "PCD 80 mm, hole spacing 30 degrees (30°)",
        {"dimensions": {}},
        1,
    )

    assert any(token.kind == "diameter" and token.value == 80 for token in inventory)
    assert any(token.kind == "angle" and token.value == 30 for token in inventory)


def test_dimension_inventory_does_not_convert_mm_values_twice():
    inventory = _dimension_inventory(
        "",
        {"dimensions": {"diameters": [{"valueMm": 25.4, "value": 1, "unit": "in"}]}},
        1,
    )

    assert len(inventory) == 1
    assert inventory[0].value == 25.4
    assert inventory[0].kind == "diameter"


def test_partial_angular_pattern_is_blocked_instead_of_moved_to_full_circle():
    blueprint = Blueprint(
        primary_body_type="rotational_flange",
        base_sketch=BaseSketch(profile="circle", outer_diameter=100, thickness=10),
        features=[
            Feature(
                type="circular_pattern_cut",
                count=6,
                pitch_radius=35,
                diameter=8,
                angular_pitch=30,
            )
        ],
    )

    errors, _warnings = lint(blueprint)

    assert any("partial/uneven angular patterns are not supported" in error for error in errors)


def test_revolved_profile_rejects_unsupported_separate_features():
    blueprint = Blueprint(
        primary_body_type="revolved_profile",
        base_sketch=BaseSketch(
            profile="polygon",
            points=[[10, 0], [20, 0], [20, 40], [10, 40]],
        ),
        features=[Feature(type="through_hole", diameter=5)],
    )

    errors, _warnings = lint(blueprint)

    assert any("Features on revolved_profile bodies are not supported" in error for error in errors)


def test_sprocket_is_not_silently_replaced_by_a_smooth_flange():
    blueprint = _heuristic_blueprint("Sprocket, 8 teeth, OD 100 mm", [])

    errors, _warnings = lint(blueprint)

    assert blueprint.primary_body_type is None
    assert blueprint.unsupported_geometry
    assert any("Unsupported geometry" in message for message in errors)


def test_text_only_fallback_uses_explicit_labels_for_flange_parameters():
    text = "Flange OD 150 mm BORE DIA 30 mm PCD 100 mm 6 holes equally spaced HOLE DIA 8 mm THICKNESS 10 mm"
    blueprint = _heuristic_blueprint(text, [])
    notes = apply_defaults(blueprint)

    assert blueprint.primary_body_type == "rotational_flange"
    assert blueprint.base_sketch.outer_diameter == 150
    assert blueprint.base_sketch.inner_bore_diameter == 30
    assert blueprint.base_sketch.thickness == 10
    assert blueprint.features[0].count == 6
    assert blueprint.features[0].pitch_radius == 50
    assert blueprint.features[0].diameter == 8
    assert not notes


def test_openai_compatible_vision_sends_image_and_strict_schema(monkeypatch):
    captured: dict[str, Any] = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": Blueprint(
                part_name="response",
                primary_body_type="rotational_flange",
                base_sketch=BaseSketch(profile="circle", outer_diameter=50, thickness=10),
            ).model_dump_json()}}]}

    class FakeAsyncClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["body"] = json
            return FakeResponse()

    import ai3d_designer.drawing_to_cad.extraction as extraction

    monkeypatch.setattr(extraction.httpx, "AsyncClient", FakeAsyncClient)

    adapter = OpenAICompatibleVision(
        "https://vision.example/v1",
        "vision-model",
        "test-secret",
    )
    import asyncio

    result = asyncio.run(adapter.chat_json(
        [b"fake-png"],
        "system",
        "inspect the drawing",
        Blueprint.model_json_schema(),
    ))

    assert result["part_name"] == "response"
    assert captured["url"] == "https://vision.example/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-secret"
    body = captured["body"]
    assert body["temperature"] == 0
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    schema = body["response_format"]["json_schema"]["schema"]
    assert schema["required"] == list(schema["properties"].keys())
    assert schema["additionalProperties"] is False

    def assert_no_unsupported_defaults(node):
        if isinstance(node, dict):
            assert "default" not in node
            assert "exclusiveMinimum" not in node
            assert "exclusiveMaximum" not in node
            for value in node.values():
                assert_no_unsupported_defaults(value)
        elif isinstance(node, list):
            for value in node:
                assert_no_unsupported_defaults(value)

    assert_no_unsupported_defaults(schema)


def test_deterministic_generator_exports_a_watertight_flange():
    blueprint = Blueprint(
        part_name="test flange",
        primary_body_type="rotational_flange",
        base_sketch=BaseSketch(
            profile="circle",
            outer_diameter=100,
            inner_bore_diameter=20,
            thickness=10,
        ),
        features=[
            Feature(type="circular_pattern_cut", count=6, pitch_radius=38, diameter=8)
        ],
    )

    result = export_blueprint(blueprint)

    assert len(base64.b64decode(result["stepBase64"])) > 100
    assert len(base64.b64decode(result["stlBase64"])) > 100
    assert result["metrics"]["solid_count"] == 1
    assert result["metrics"]["stl_watertight"] is True


def test_generator_blocks_missing_dimensions_and_unsupported_geometry():
    missing = Blueprint(
        primary_body_type="rotational_flange",
        base_sketch=BaseSketch(profile="circle"),
    )
    with pytest.raises(GeometryError, match="outer_diameter"):
        export_blueprint(missing)

    unsupported = Blueprint(
        primary_body_type="rotational_flange",
        base_sketch=BaseSketch(profile="circle", outer_diameter=100, thickness=10),
        unsupported_geometry=["sprocket tooth profile"],
    )
    with pytest.raises(GeometryError, match="Unsupported geometry"):
        export_blueprint(unsupported)


class FakeVision:
    model = "test-vision"

    async def chat_json(
        self, images_png: list[bytes], system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        assert images_png and schema["title"] == "Blueprint"
        return Blueprint(
            part_name="grounded flange",
            primary_body_type="rotational_flange",
            base_sketch=BaseSketch(
                profile="circle",
                outer_diameter=100,
                inner_bore_diameter=20,
                thickness=10,
            ),
            features=[
                Feature(type="circular_pattern_cut", count=6, pitch_radius=40, diameter=8)
            ],
            needs_review=True,
        ).model_dump(mode="json")


def test_extract_blueprint_renders_pdf_and_returns_grounded_structured_fields():
    document = pymupdf.open()
    page = document.new_page(width=600, height=400)
    page.insert_text((50, 50), "FLANGE OD 100 mm BORE DIA 20 mm THICKNESS 10 mm PCD 80 mm HOLE DIA 8 mm")
    pdf_bytes = document.tobytes()
    document.close()
    text = "FLANGE OD 100 mm BORE DIA 20 mm THICKNESS 10 mm PCD 80 mm HOLE DIA 8 mm"
    dimensions = {
        "dimensions": {
            "triplets": [],
            "linear": [{"raw": "THICKNESS 10 mm", "valueMm": 10, "unit": "mm"}],
            "diameters": [
                {"raw": "OD 100 mm", "value": 100, "unit": "mm"},
                {"raw": "BORE DIA 20 mm", "value": 20, "unit": "mm"},
                {"raw": "PCD 80 mm", "value": 80, "unit": "mm"},
                {"raw": "HOLE DIA 8 mm", "value": 8, "unit": "mm"},
            ],
            "radii": [],
        }
    }

    result = asyncio.run(
        extract_blueprint(
            file_bytes=pdf_bytes,
            file_name="flange.pdf",
            mime_type="application/pdf",
            raw_text=text,
            dimension_data=dimensions,
            vision=FakeVision(),
        )
    )

    assert result.source == "vector_pdf"
    assert result.source_pages == 1
    assert result.vision_model == "test-vision"
    assert result.blueprint.base_sketch.outer_diameter == 100
    assert result.blueprint.features[0].pitch_radius == 40
    assert result.cleared_fields == []
