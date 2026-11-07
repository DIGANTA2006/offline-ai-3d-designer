"""Regression tests for grounded structured drawing blueprints and deterministic CAD."""

import asyncio
import base64
import io
from pathlib import Path
from typing import Any

from PIL import Image
import pymupdf
import pytest

from ai3d_designer.drawing_to_cad.blueprint import (
    BaseSketch,
    Blueprint,
    Feature,
    VisualMeasurement,
    apply_defaults,
    lint,
)
from ai3d_designer.drawing_to_cad.extraction import (
    DimensionToken,
    OpenAICompatibleVision,
    _dimension_inventory,
    _heuristic_blueprint,
    _prepare_vision_image,
    extract_blueprint,
    get_vision_backend,
    ground_blueprint,
    reconcile_visual_measurements,
)
from ai3d_designer.drawing_to_cad.generator import GeometryError, export_blueprint



def test_inventory_preserves_different_semantic_callouts_with_the_same_value():
    inventory = _dimension_inventory("OD 80 mm PCD 80 mm", {"dimensions": {}}, 1)

    assert any(token.kind == "diameter" and "outer diameter" in token.raw.lower() for token in inventory)
    assert any(token.kind == "diameter" and "pitch circle diameter" in token.raw.lower() for token in inventory)


def test_outer_diameter_cannot_be_grounded_from_an_unrelated_hole_diameter():
    blueprint = Blueprint(
        primary_body_type="rotational_flange",
        base_sketch=BaseSketch(profile="circle", outer_diameter=8, thickness=10),
    )
    inventory = [
        DimensionToken(id="D1", raw="HOLE DIA 8", value=8, kind="diameter", page=1),
        DimensionToken(id="D2", raw="THICKNESS 10", value=10, kind="linear", page=1),
    ]

    cleared = ground_blueprint(blueprint, inventory)

    assert blueprint.base_sketch.outer_diameter is None
    assert "base_sketch.outer_diameter=8" in cleared
    assert blueprint.base_sketch.thickness == 10


def test_pitch_radius_half_diameter_requires_pcd_or_bcd_evidence():
    blueprint = Blueprint(
        primary_body_type="rotational_flange",
        base_sketch=BaseSketch(profile="circle", outer_diameter=100, thickness=10),
        features=[Feature(type="hole_pattern", count=6, pitch_radius=4, diameter=8)],
    )
    inventory = [
        DimensionToken(id="D1", raw="HOLE DIA 8", value=8, kind="diameter", page=1),
        DimensionToken(id="D2", raw="OUTER DIAMETER 100", value=100, kind="diameter", page=1),
        DimensionToken(id="D3", raw="THICKNESS 10", value=10, kind="linear", page=1),
    ]

    cleared = ground_blueprint(blueprint, inventory)

    assert blueprint.features[0].diameter == 8
    assert blueprint.features[0].pitch_radius is None
    assert "features[0].pitch_radius=4" in cleared


def test_hole_diameter_cannot_be_grounded_from_a_pcd_callout():
    blueprint = Blueprint(
        primary_body_type="rotational_flange",
        base_sketch=BaseSketch(profile="circle", outer_diameter=120, thickness=10),
        features=[Feature(type="hole_pattern", count=6, pitch_radius=40, diameter=80)],
    )
    inventory = [
        DimensionToken(id="D1", raw="PCD 80", value=80, kind="diameter", page=1),
        DimensionToken(id="D2", raw="OUTER DIAMETER 120", value=120, kind="diameter", page=1),
        DimensionToken(id="D3", raw="THICKNESS 10", value=10, kind="linear", page=1),
    ]

    cleared = ground_blueprint(blueprint, inventory)

    assert blueprint.features[0].pitch_radius == 40
    assert blueprint.features[0].diameter is None
    assert "features[0].diameter=80" in cleared


def test_wall_thickness_cannot_be_reused_as_solid_height():
    blueprint = Blueprint(
        primary_body_type="sheet_enclosure",
        base_sketch=BaseSketch(
            profile="rectangle",
            length=100,
            width=80,
            thickness=2.5,
            wall_thickness=2.5,
        ),
    )
    inventory = [
        DimensionToken(id="D1", raw="WALL THICKNESS 2.5", value=2.5, kind="linear", page=1),
    ]

    cleared = ground_blueprint(blueprint, inventory)

    assert blueprint.base_sketch.thickness is None
    assert blueprint.base_sketch.wall_thickness == 2.5
    assert "base_sketch.thickness=2.5" in cleared


def test_root_radius_cannot_be_grounded_from_outer_radius():
    blueprint = Blueprint(
        primary_body_type="rotational_flange",
        base_sketch=BaseSketch(profile="circle", outer_diameter=134, thickness=10),
        features=[Feature(type="radial_cutout_pattern", count=10, radius=15.5, root_radius=63.4)],
    )
    inventory = [
        DimensionToken(id="D1", raw="OUTER RADIUS R63.4", value=63.4, kind="radius", page=1),
        DimensionToken(id="D2", raw="GULLET RADIUS R15.5", value=15.5, kind="radius", page=1),
        DimensionToken(id="D3", raw="OUTER DIAMETER 134", value=134, kind="diameter", page=1),
        DimensionToken(id="D4", raw="THICKNESS 10", value=10, kind="linear", page=1),
    ]

    cleared = ground_blueprint(blueprint, inventory)

    assert blueprint.features[0].root_radius is None
    assert blueprint.features[0].radius == 15.5
    assert "features[0].root_radius=63.4" in cleared


def test_ring_step_dimensions_are_not_reused_as_base_body_diameters():
    inventory = _dimension_inventory(
        "RING OUTER DIAMETER 90 mm RING INNER DIAMETER 70 mm RECESS DEPTH 5 mm",
        {"dimensions": {}},
        1,
    )
    blueprint = Blueprint(
        primary_body_type="rotational_flange",
        base_sketch=BaseSketch(
            profile="circle",
            outer_diameter=90,
            inner_bore_diameter=70,
            thickness=10,
        ),
        features=[
            Feature(type="ring_step", diameter=90, inner_diameter=70, depth=5),
        ],
    )

    cleared = ground_blueprint(blueprint, inventory)

    assert blueprint.base_sketch.outer_diameter is None
    assert blueprint.base_sketch.inner_bore_diameter is None
    assert blueprint.features[0].diameter == 90
    assert blueprint.features[0].inner_diameter == 70
    assert blueprint.features[0].depth == 5
    assert "base_sketch.outer_diameter=90" in cleared
    assert "base_sketch.inner_bore_diameter=70" in cleared


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


def test_pitch_radius_cannot_match_a_hole_diameter_directly():
    blueprint = Blueprint(
        primary_body_type="rotational_flange",
        base_sketch=BaseSketch(profile="circle", outer_diameter=100, thickness=10),
        features=[
            Feature(type="circular_pattern_cut", count=6, pitch_radius=8, diameter=8),
        ],
    )
    inventory = [
        DimensionToken(id="D1", raw="OD 100", value=100, kind="diameter", page=1),
        DimensionToken(id="D2", raw="hole Ø8", value=8, kind="diameter", page=1),
        DimensionToken(id="D3", raw="THK 10", value=10, kind="linear", page=1),
    ]

    cleared = ground_blueprint(blueprint, inventory)

    assert blueprint.features[0].diameter == 8
    assert blueprint.features[0].pitch_radius is None
    assert any("features[0].pitch_radius=8" in value for value in cleared)


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


def test_grounding_clears_model_invented_profile_coordinates():
    blueprint = Blueprint(
        primary_body_type="revolved_profile",
        base_sketch=BaseSketch(
            profile="polygon",
            points=[[10, 0], [20, 0], [20, 40], [10, 40]],
        ),
    )
    inventory = [
        DimensionToken(id="D1", raw="Ø100", value=100, kind="diameter", page=1),
    ]

    cleared = ground_blueprint(blueprint, inventory)

    assert blueprint.base_sketch.points is None
    assert any("profile coordinates were not grounded" in value for value in cleared)


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


def test_labeled_sprocket_dimensions_build_supported_radial_cutout_blueprint():
    text = (
        "Sprocket outer radius R67 root radius R63.4 gullet radius R15.5 "
        "10 teeth bore diameter Ø80 thickness 10 mm"
    )
    inventory = _dimension_inventory(text, {"dimensions": {}}, 1)
    blueprint = _heuristic_blueprint(text, inventory)

    errors, _warnings = lint(blueprint)

    assert blueprint.primary_body_type == "rotational_flange"
    assert blueprint.base_sketch.outer_diameter == 134
    radial = next(feature for feature in blueprint.features if feature.type == "radial_cutout_pattern")
    assert radial.count == 10
    assert radial.radius == 15.5
    assert radial.root_radius == 63.4
    assert radial.pitch_radius is None
    assert not blueprint.unsupported_geometry
    assert not errors


def test_sprocket_without_explicit_gullet_geometry_stays_blocked():
    blueprint = _heuristic_blueprint("Sprocket, 10 teeth, OD 134 mm", [])

    errors, _warnings = lint(blueprint)

    assert blueprint.primary_body_type == "rotational_flange"
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


def test_selected_vision_provider_does_not_reuse_another_providers_url(monkeypatch):
    monkeypatch.setenv("DRAWING_VISION_PROVIDER", "openai_compatible")
    monkeypatch.setenv("DRAWING_VISION_ALLOW_HOSTED", "true")  # explicit opt-in: hosted is blocked by default
    monkeypatch.delenv("DRAWING_VISION_URL", raising=False)
    monkeypatch.setenv("OLLAMA_URL", "http://ollama.internal:11434")

    assert get_vision_backend() is None

    monkeypatch.setenv("DRAWING_VISION_URL", "https://vision.example/v1")
    monkeypatch.setenv("DRAWING_VISION_MODEL", "vision-model")
    monkeypatch.setenv("DRAWING_VISION_API_KEY", "unit-test-secret")
    provider = get_vision_backend()

    assert isinstance(provider, OpenAICompatibleVision)
    assert provider.base_url == "https://vision.example/v1"
    assert provider.api_key == "unit-test-secret"


def test_hosted_vision_is_blocked_by_default(monkeypatch):
    """Drawings are client data: a hosted model receives them only after an explicit opt-in."""
    monkeypatch.setenv("DRAWING_VISION_PROVIDER", "openai_compatible")
    monkeypatch.setenv("DRAWING_VISION_URL", "https://vision.example/v1")
    monkeypatch.setenv("DRAWING_VISION_MODEL", "vision-model")
    monkeypatch.delenv("DRAWING_VISION_ALLOW_HOSTED", raising=False)
    assert get_vision_backend() is None

    monkeypatch.setenv("DRAWING_VISION_ALLOW_HOSTED", "true")
    assert isinstance(get_vision_backend(), OpenAICompatibleVision)


def test_vision_timeout_is_configurable_and_bounded(monkeypatch):
    monkeypatch.setenv("DRAWING_VISION_PROVIDER", "openai_compatible")
    monkeypatch.setenv("DRAWING_VISION_ALLOW_HOSTED", "true")  # explicit opt-in: hosted is blocked by default
    monkeypatch.setenv("DRAWING_VISION_URL", "https://vision.example/v1")
    monkeypatch.setenv("DRAWING_VISION_MODEL", "vision-model")
    monkeypatch.setenv("DRAWING_VISION_TIMEOUT_SECONDS", "120")

    provider = get_vision_backend()
    assert isinstance(provider, OpenAICompatibleVision)
    assert provider.timeout == 30.0

    monkeypatch.setenv("DRAWING_VISION_TIMEOUT_SECONDS", "9999")
    with pytest.raises(ValueError, match="between 1 and 600"):
        get_vision_backend()


def test_vision_image_preparation_is_compressed_jpeg_and_keeps_bounded_resolution():
    original = Image.new("RGB", (3200, 2400), "white")
    source = io.BytesIO()
    original.save(source, format="PNG")
    prepared = _prepare_vision_image(source.getvalue())

    with Image.open(io.BytesIO(prepared)) as result:
        assert result.format == "JPEG"
        assert max(result.size) == 2048


def test_openai_compatible_falls_back_to_json_mode_when_schema_format_is_rejected(monkeypatch, caplog):
    captured: list[dict[str, Any]] = []

    class FakeResponse:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self.text = body

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": Blueprint(
                part_name="json-mode-response",
                primary_body_type="rotational_flange",
                base_sketch=BaseSketch(profile="circle", outer_diameter=50, thickness=10),
            ).model_dump_json()}}]}

    class FakeAsyncClient:
        def __init__(self, timeout):
            captured.append({"timeout": timeout, "requests": []})

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, headers, json):
            import copy
            captured[-1]["requests"].append({"url": url, "payload": copy.deepcopy(json)})
            if len(captured[-1]["requests"]) == 1:
                return FakeResponse(400, '{"error":"response_format json_schema is not supported by this model"}')
            return FakeResponse(200, "")

    import ai3d_designer.drawing_to_cad.extraction as extraction
    monkeypatch.setattr(extraction.httpx, "AsyncClient", FakeAsyncClient)
    adapter = OpenAICompatibleVision("https://vision.example/v1", "vision-model", None, timeout=120)
    result = asyncio.run(adapter.chat_json([b"jpeg"], "return JSON", "inspect", Blueprint.model_json_schema()))

    requests = captured[0]["requests"]
    assert result["part_name"] == "json-mode-response"
    assert len(requests) == 2
    assert requests[0]["payload"]["response_format"]["type"] == "json_schema"
    assert requests[1]["payload"]["response_format"] == {"type": "json_object"}
    assert "Compatibility fallback" in requests[1]["payload"]["messages"][0]["content"]
    assert captured[0]["timeout"] == 120
    assert "not supported by this model" in caplog.text


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
    assert body["max_tokens"] == 2048
    assert captured["timeout"] == 25.0
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
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


def test_cad_export_scratch_directory_is_removed_when_export_fails(monkeypatch):
    import ai3d_designer.drawing_to_cad.generator as generator_module

    scratch_paths: list[Path] = []
    original_temporary_directory = generator_module.tempfile.TemporaryDirectory

    class TrackingTemporaryDirectory(original_temporary_directory):
        def __enter__(self):
            path = super().__enter__()
            scratch_paths.append(Path(path))
            return path

    def fail_step_export(*_args, **_kwargs):
        raise RuntimeError("synthetic STEP export failure")

    monkeypatch.setattr(generator_module.tempfile, "TemporaryDirectory", TrackingTemporaryDirectory)
    monkeypatch.setattr(generator_module, "export_step", fail_step_export)
    blueprint = Blueprint(
        primary_body_type="rotational_flange",
        base_sketch=BaseSketch(profile="circle", outer_diameter=50, thickness=10),
    )

    with pytest.raises(RuntimeError, match="synthetic STEP export failure"):
        generator_module.export_blueprint(blueprint)

    assert len(scratch_paths) == 1
    assert not scratch_paths[0].exists()


def test_deterministic_generator_exports_scalloped_flange_with_pcd_holes():
    blueprint = Blueprint(
        part_name="10-gullet flange",
        primary_body_type="rotational_flange",
        base_sketch=BaseSketch(
            profile="circle",
            outer_diameter=134,
            inner_bore_diameter=80,
            thickness=10,
        ),
        features=[
            Feature(type="radial_cutout_pattern", count=10, radius=15.5, root_radius=63.4),
            Feature(type="hole_pattern", count=6, pitch_radius=50, diameter=8),
        ],
    )

    errors, _warnings = lint(blueprint)
    assert not errors
    result = export_blueprint(blueprint)

    assert len(base64.b64decode(result["stepBase64"])) > 100
    assert len(base64.b64decode(result["stlBase64"])) > 100
    assert result["metrics"]["solid_count"] == 1
    assert result["metrics"]["stl_watertight"] is True
    assert result["metrics"]["bbox_mm"][0] <= 134
    assert result["metrics"]["bbox_mm"][1] <= 134


def test_deterministic_generator_exports_a_concentric_ring_recess():
    blueprint = Blueprint(
        part_name="ring step flange",
        primary_body_type="rotational_flange",
        base_sketch=BaseSketch(profile="circle", outer_diameter=120, inner_bore_diameter=30, thickness=10),
        features=[Feature(type="ring_step", diameter=90, inner_diameter=70, depth=2, ring_mode="cut")],
    )
    result = export_blueprint(blueprint)
    assert result["metrics"]["solid_count"] == 1
    assert result["metrics"]["stl_watertight"] is True


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


def test_visual_only_measurement_is_preserved_but_not_promoted_to_geometry():
    blueprint = Blueprint(
        primary_body_type="rotational_flange",
        base_sketch=BaseSketch(profile="circle", outer_diameter=60, thickness=8),
        visual_measurements=[
            VisualMeasurement(
                dimension_name="Outer diameter",
                raw_callout="Ø60",
                value=60,
                unit="mm",
                kind="diameter",
                source_page=1,
                source_view="top",
                confidence=0.9,
            )
        ],
    )

    cleared = ground_blueprint(blueprint, [])

    assert blueprint.base_sketch.outer_diameter is None
    assert blueprint.base_sketch.thickness is None
    assert blueprint.visual_measurements[0].value == 60
    assert blueprint.visual_measurements[0].verification_status == "vision_only"
    assert "base_sketch.outer_diameter=60" in cleared


def test_visual_measurement_ocr_value_match_requires_kind_unit_and_page():
    blueprint = Blueprint(
        source_pages=[1],
        visual_measurements=[
            VisualMeasurement(
                dimension_name="Hole diameter",
                raw_callout="4 × Ø8",
                value=8,
                unit="mm",
                kind="diameter",
                source_page=1,
                source_view="top",
                confidence=0.8,
                verification_status="ocr_value_match",
                ocr_inventory_id="fake-id",
            ),
            VisualMeasurement(
                dimension_name="Slot length",
                raw_callout="L 20",
                value=20,
                unit="unknown",
                kind="linear",
                source_page=1,
                source_view="top",
                confidence=0.7,
            ),
        ],
    )
    inventory = [
        DimensionToken(id="D1", raw="Ø8", value=8, kind="diameter", page=1),
        DimensionToken(id="D2", raw="20 mm", value=20, kind="linear", page=2),
    ]

    reconcile_visual_measurements(blueprint, inventory)

    assert blueprint.visual_measurements[0].verification_status == "ocr_value_match"
    assert blueprint.visual_measurements[0].ocr_inventory_id == "D1"
    assert blueprint.visual_measurements[1].verification_status == "vision_only"
    assert blueprint.visual_measurements[1].ocr_inventory_id is None


def test_vision_schema_reads_image_callouts_even_when_ocr_inventory_is_empty():
    class FakeVision:
        model = "test-vision"
        timeout = 2.0

        async def chat_json(self, images, system, user, schema):
            assert images
            assert "IMAGE PIXELS directly" in system
            assert "not a whitelist for visual_measurements" in system.lower()
            assert "visual_measurements" in schema.get("properties", {})
            return {
                "part_name": "test flange",
                "primary_body_type": "rotational_flange",
                "base_sketch": {
                    "profile": "circle",
                    "outer_diameter": 60,
                    "inner_bore_diameter": None,
                    "width": None,
                    "length": None,
                    "thickness": 8,
                    "wall_thickness": None,
                    "thickness_is_default": False,
                    "wall_thickness_is_default": False,
                    "points": None,
                },
                "features": [],
                "visual_measurements": [{
                    "dimension_name": "Outer diameter",
                    "raw_callout": "Ø60",
                    "value": 60,
                    "unit": "mm",
                    "kind": "diameter",
                    "feature": "outer profile",
                    "source_page": 1,
                    "source_view": "top",
                    "confidence": 0.85,
                    "region": {"x": 0.2, "y": 0.3, "width": 0.1, "height": 0.1},
                    "verification_status": "ocr_value_match",
                    "ocr_inventory_id": "fake-id",
                }],
                "warnings": [],
                "unsupported_geometry": [],
                "source_pages": [1],
                "needs_review": True,
            }

    image = Image.new("RGB", (320, 240), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    result = asyncio.run(
        extract_blueprint(
            file_bytes=buffer.getvalue(),
            file_name="test-drawing.png",
            mime_type="image/png",
            raw_text="",
            dimension_data={"dimensions": {}},
            vision=FakeVision(),
        )
    )

    candidate = result.blueprint.visual_measurements[0]
    assert result.dimension_inventory == []
    assert result.vision_model == "test-vision"
    assert result.blueprint.base_sketch.outer_diameter is None
    assert result.blueprint.base_sketch.thickness == 10
    assert result.blueprint.base_sketch.thickness_is_default is True
    assert candidate.value == 60
    assert candidate.verification_status == "vision_only"
    assert candidate.ocr_inventory_id is None
