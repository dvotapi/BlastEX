"""`POST /design/back-azimuth`: азимут тыла для шаблона «от тыла» (PR 2)."""
from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import design as design_router

PATH = "/api/v1/design/back-azimuth"


@pytest.fixture()
def client() -> TestClient:
    os.environ["BLASTEX_API_KEY"] = "test-api-key"
    os.environ["BLASTEX_SESSION_SECRET"] = "test-session-secret"
    app = FastAPI()
    app.include_router(design_router.router, prefix="/api/v1")
    return TestClient(app, headers={"X-API-Key": "test-api-key"})


def _contour(points, free):
    return {
        "vertices": [{"x": x, "y": y, "z": 0.0} for x, y in points],
        "free_faces": free,
        "bench": {"crest_z_m": 0.0, "toe_z_m": -10.0, "face_angle_deg": 75.0},
        "name": "Блок",
    }


RECT = [(0, 0), (40, 0), (40, 22), (0, 22)]


def test_rectangle_back_azimuth(client):
    response = client.post(PATH, json={"contour": _contour(RECT, [[0, 1]])})
    assert response.status_code == 200
    assert response.json()["azimuth_deg"] == pytest.approx(90.0)


def test_whole_contour_free_gives_null(client):
    response = client.post(PATH, json={"contour": _contour(RECT, [[0, 1], [1, 2], [2, 3], [3, 0]])})
    assert response.status_code == 200
    assert response.json() == {"azimuth_deg": None}


def test_less_than_three_vertices_is_422(client):
    response = client.post(PATH, json={"contour": _contour([(0, 0), (40, 0)], [])})
    assert response.status_code == 422
