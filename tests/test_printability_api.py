"""Integration tests for authenticated printability FastAPI routes."""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python-backend"))

import main as cad_service  # noqa: E402
from ai3d_designer.core.spec.models import (  # noqa: E402
    FeatureSpec,
    ParameterSpec,
    PartSpec,
    PrimitiveType,
    OperationType,
    UnitSystem,
)


def _box_spec() -> dict:
    spec = PartSpec(
        name="API test box",
        description="A fully dimensioned box used by API integration tests.",
        unit_system=UnitSystem.MM,
        features=[
            FeatureSpec(
                id="base",
                type=PrimitiveType.BOX,
                name="Base",
                parameters={
                    "width": ParameterSpec(name="width", value=40.0, unit=UnitSystem.MM),
                    "depth": ParameterSpec(name="depth", value=30.0, unit=UnitSystem.MM),
                    "height": ParameterSpec(name="height", value=10.0, unit=UnitSystem.MM),
                },
                position=[0.0, 0.0, 0.0],
                rotation=[0.0, 0.0, 0.0],
                operation=OperationType.UNION,
            )
        ],
    )
    return spec.model_dump(mode="json")


def _flange_blueprint() -> dict:
    return {
        "part_name": "API test flange",
        "primary_body_type": "rotational_flange",
        "base_sketch": {
            "profile": "circle",
            "outer_diameter": 40.0,
            "inner_bore_diameter": 6.0,
            "thickness": 8.0,
        },
        "features": [
            {
                "type": "through_hole",
                "count": 1,
                "diameter": 4.0,
                "x": 12.0,
                "y": 0.0,
            }
        ],
        "unsupported_geometry": [],
        "needs_review": False,
    }


def _request_cases():
    spec = _box_spec()
    return [
        ("POST", "/api/v1/printability/check", {"partSpec": spec}),
        ("POST", "/api/v1/printability/check-blueprint", {"blueprint": _flange_blueprint()}),
        (
            "POST",
            "/api/v1/printability/fix",
            {"partSpec": spec, "action": "add_support", "checkId": "overhang_angle"},
        ),
        ("GET", "/api/v1/printability/explanations/overhang_angle", None),
        ("GET", "/api/v1/printability/glossary", None),
        ("GET", "/api/v1/printability/fixes/overhang_angle", None),
    ]


def test_every_printability_route_requires_the_cad_service_token(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CAD_SERVICE_TOKEN", "printability-test-token")
    client = TestClient(cad_service.app)

    for method, path, payload in _request_cases():
        response = client.request(method, path, json=payload)
        assert response.status_code == 401, f"{method} {path}: {response.text}"


def test_authenticated_printability_routes_and_fix_response(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CAD_SERVICE_TOKEN", "printability-test-token")
    client = TestClient(cad_service.app)
    headers = {"Authorization": "Bearer printability-test-token"}

    check = client.post(
        "/api/v1/printability/check",
        json={"partSpec": _box_spec()},
        headers=headers,
    )
    assert check.status_code == 200, check.text
    assert check.json()["success"] is True
    assert check.json()["summary"]["total"] >= 8
    assert {"pass", "fail", "warning", "skipped"} <= set(check.json()["summary"])

    explanations = client.get(
        "/api/v1/printability/explanations/overhang_angle",
        headers=headers,
    )
    assert explanations.status_code == 200, explanations.text
    assert explanations.json()["checkId"] == "overhang_angle"

    glossary = client.get("/api/v1/printability/glossary", headers=headers)
    assert glossary.status_code == 200, glossary.text
    assert isinstance(glossary.json()["glossary"], dict)

    fixes = client.get(
        "/api/v1/printability/fixes/overhang_angle",
        headers=headers,
    )
    assert fixes.status_code == 200, fixes.text
    assert "not generated" in fixes.json()["descriptions"]["add_support"].lower()

    fix = client.post(
        "/api/v1/printability/fix",
        json={
            "partSpec": _box_spec(),
            "action": "add_support",
            "checkId": "overhang_angle",
            "parameters": {"support_angle": 45.0},
        },
        headers=headers,
    )
    assert fix.status_code == 200, fix.text
    assert fix.json()["success"] is True
    assert fix.json()["result"]["action"] == "add_support"
    assert fix.json()["result"]["modified_spec"]["features"][0]["metadata"]["needs_support"] is True
    assert any("does not generate support geometry" in notice for notice in fix.json()["notices"])


def test_authenticated_printability_check_rejects_malformed_partspec(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CAD_SERVICE_TOKEN", "printability-test-token")
    client = TestClient(cad_service.app)

    response = client.post(
        "/api/v1/printability/check",
        json={"partSpec": {"name": "invalid feature", "features": [{"type": "not-a-primitive"}]}},
        headers={"Authorization": "Bearer printability-test-token"},
    )
    assert response.status_code == 422


def test_drawing_blueprint_printability_checks_the_generated_solid_without_faking_a_partspec(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CAD_SERVICE_TOKEN", "printability-test-token")
    client = TestClient(cad_service.app)

    response = client.post(
        "/api/v1/printability/check-blueprint",
        json={"blueprint": _flange_blueprint()},
        headers={"Authorization": "Bearer printability-test-token"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    assert payload["summary"]["total"] >= 8
    assert payload["notices"]
    assert all(check["available_fixes"] == [] for check in payload["checks"])


def test_blueprint_printability_skips_hole_checks_when_no_holes_are_declared():
    from ai3d_designer.drawing_to_cad.blueprint import Blueprint, BaseSketch
    from ai3d_designer.drawing_to_cad.generator import build_part
    from ai3d_designer.printability.checks import PrintabilityChecker, CheckStatus

    blueprint = Blueprint(
        part_name="Solid round blank",
        primary_body_type="rotational_flange",
        base_sketch=BaseSketch(profile="circle", outer_diameter=40, thickness=8),
        features=[],
        needs_review=False,
    )
    solid, _ = build_part(blueprint)
    checker = PrintabilityChecker()
    results = checker.check_all(
        PartSpec(name=blueprint.part_name),
        part_override=solid,
        blueprint_override=blueprint,
    )
    by_id = {result.check_id: result for result in results}

    # The outside cylindrical wall is not a hole and must not be reported as one.
    assert by_id["hole_size"].status == CheckStatus.SKIPPED
    assert by_id["hole_edge_distance"].status == CheckStatus.SKIPPED


def test_blueprint_hole_to_edge_uses_saved_feature_position_and_outer_diameter():
    from ai3d_designer.drawing_to_cad.blueprint import Blueprint, BaseSketch, Feature
    from ai3d_designer.drawing_to_cad.generator import build_part
    from ai3d_designer.printability.checks import PrintabilityChecker, CheckStatus

    blueprint = Blueprint(
        part_name="Edge clearance test flange",
        primary_body_type="rotational_flange",
        base_sketch=BaseSketch(profile="circle", outer_diameter=40, thickness=8),
        features=[Feature(type="through_hole", diameter=4, x=17.5, y=0)],
        needs_review=False,
    )
    solid, _ = build_part(blueprint)
    checker = PrintabilityChecker()
    results = checker.check_all(
        PartSpec(name=blueprint.part_name),
        part_override=solid,
        blueprint_override=blueprint,
    )
    by_id = {result.check_id: result for result in results}

    assert by_id["hole_size"].status == CheckStatus.PASS
    assert by_id["hole_size"].value == 4
    assert by_id["hole_edge_distance"].status == CheckStatus.FAIL
    assert by_id["hole_edge_distance"].value == 0.5


def test_drawing_blueprint_printability_rejects_unresolved_body(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CAD_SERVICE_TOKEN", "printability-test-token")
    client = TestClient(cad_service.app)

    blueprint = _flange_blueprint()
    blueprint["primary_body_type"] = None
    response = client.post(
        "/api/v1/printability/check-blueprint",
        json={"blueprint": blueprint},
        headers={"Authorization": "Bearer printability-test-token"},
    )
    assert response.status_code == 422, response.text
