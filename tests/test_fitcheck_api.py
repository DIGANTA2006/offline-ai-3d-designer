"""Authenticated API tests for the hardware fit-check workflow."""

import pytest
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python-backend"))

import main as cad_service  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("CAD_SERVICE_TOKEN", raising=False)
    with TestClient(cad_service.app) as test_client:
        yield test_client


def enclosure_payload(*, confirmed: bool = True) -> dict:
    return {
        "name": "ESP32 test enclosure",
        "interior_width": 31.0,
        "interior_depth": 58.0,
        "interior_height": 22.0,
        "wall_thickness": 2.0,
        "confirmed": confirmed,
    }


def test_fit_check_preset_catalog_is_available(client):
    response = client.get("/api/v1/fit-check/presets")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["presets"]) == 6
    assert payload["notice"]
    assert any(item["id"] == "esp32_devkit" for item in payload["presets"])
    # Catalog data is not silently treated as user-confirmed.
    assert all(item["confirmed"] is False for item in payload["presets"])


def test_fit_check_requires_explicit_component_confirmation(client):
    response = client.post(
        "/api/v1/fit-check",
        json={
            "presetId": "esp32_devkit",
            "componentConfirmed": False,
            "enclosure": enclosure_payload(),
        },
    )

    assert response.status_code == 422
    assert "exact hardware revision" in response.json()["detail"]


def test_fit_check_requires_explicit_enclosure_confirmation(client):
    response = client.post(
        "/api/v1/fit-check",
        json={
            "presetId": "esp32_devkit",
            "componentConfirmed": True,
            "enclosure": enclosure_payload(confirmed=False),
        },
    )

    assert response.status_code == 422
    assert "Confirm the enclosure's interior dimensions" in response.json()["detail"]


def test_fit_check_returns_clearance_report_for_confirmed_dimensions(client):
    response = client.post(
        "/api/v1/fit-check",
        json={
            "presetId": "esp32_devkit",
            "componentConfirmed": True,
            "clearanceMm": 1.5,
            "enclosure": enclosure_payload(),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["component"]["confirmed"] is True
    assert payload["report"]["overall_fit"] is True
    assert len(payload["report"]["results"]) == 1
    result = payload["report"]["results"][0]
    assert result["fits"] is True
    assert result["shortfall_mm"] == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert any("Mounting-hole alignment was not checked" in warning for warning in result["warnings"])
    assert payload["limitations"]


def test_fit_check_unknown_preset_returns_not_found(client):
    response = client.post(
        "/api/v1/fit-check",
        json={
            "presetId": "not-a-hardware-preset",
            "componentConfirmed": True,
            "enclosure": enclosure_payload(),
        },
    )

    assert response.status_code == 404
    assert "Unknown preset" in response.json()["detail"]


def test_fit_check_rejects_ambiguous_component_source(client):
    response = client.post(
        "/api/v1/fit-check",
        json={
            "presetId": "esp32_devkit",
            "componentConfirmed": True,
            "component": {
                "name": "Custom",
                "width": 28,
                "depth": 55,
                "height": 13,
                "confirmed": True,
            },
            "enclosure": enclosure_payload(),
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any("exactly one" in item.get("msg", "") for item in detail)
