"""API карты «ЛСП»: /design/maps отдаёт floor_burden."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import design
from api.security import require_internal_access
from tests.test_toe_line import face_design


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(design.router, prefix="/api/v1")
    app.dependency_overrides[require_internal_access] = lambda: {
        "sub": "a@example.ru", "role": "admin", "org": "org-a"
    }
    return TestClient(app)


def test_maps_endpoint_returns_floor_burden():
    response = _client().post("/api/v1/design/maps", json={"design": face_design().to_dict()})
    assert response.status_code == 200, response.text
    body = response.json()
    assert "floor_burden" in body["metrics"]
    assert any(h["floor_burden"] is not None for h in body["holes"])
    assert {h["floor_burden_source"] for h in body["holes"] if h["floor_burden"] is not None} == {"angle"}
