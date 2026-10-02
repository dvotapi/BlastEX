"""`POST /design/holes/recompute`: устья и длины по кровле и подошве паспорта
(TASK-013, PR 3, задача 8)."""
from __future__ import annotations

import math
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import design as design_router

PATH = "/api/v1/design/holes/recompute"


@pytest.fixture()
def client() -> TestClient:
    os.environ["BLASTEX_API_KEY"] = "test-api-key"
    os.environ["BLASTEX_SESSION_SECRET"] = "test-session-secret"
    app = FastAPI()
    app.include_router(design_router.router, prefix="/api/v1")
    return TestClient(app, headers={"X-API-Key": "test-api-key"})


def _point(x, y, z):
    return {"x": x, "y": y, "z": z}


CONTOUR = {
    "vertices": [_point(0, 0, 420), _point(40, 0, 420), _point(40, 20, 420), _point(0, 20, 420)],
    "free_faces": [],
    "bench": {"crest_z_m": 420.0, "toe_z_m": 410.0, "face_angle_deg": 90.0},
    "name": "Блок",
}
ROOF = {
    "top": {
        "kind": "top",
        "tin": {
            "vertices": [_point(-10, -10, 419.9), _point(30, -10, 420.3), _point(30, 40, 420.3), _point(-10, 40, 419.9)],
            "triangles": [[0, 1, 2], [0, 2, 3]],
        },
    }
}


def _hole(hole_id, x, y, *, length=12.0, manual=None, enabled=True):
    return {
        "id": hole_id,
        "row": 0,
        "col": 0,
        "collar": _point(x, y, 420.0),
        "toe": _point(x, y, 420.0 - length),
        "diameter_mm": 152.0,
        "subdrill_m": 1.0,
        "enabled": enabled,
        **({"manual": manual} if manual else {}),
    }


def test_recompute_returns_holes_flags_and_the_block_volume(client):
    holes = [_hole("1-01", 10, 5), _hole("1-02", 38, 5), _hole("1-03", 20, 5, length=7.0, manual=["length"])]

    response = client.post(PATH, json={"holes": holes, "contour": CONTOUR, "surfaces": ROOF, "params": {}})

    assert response.status_code == 200, response.text
    body = response.json()
    by_id = {item["id"]: item for item in body["holes"]}
    first = by_id["1-01"]
    assert first["collar"]["z"] == pytest.approx(420.1)
    assert first["collar"]["z"] - first["toe"]["z"] == pytest.approx(11.1)
    assert body["flags"] == {"1-02": ["outside_surface"]}
    assert by_id["1-02"]["collar"]["z"] == pytest.approx(420.3)
    third = by_id["1-03"]
    assert third["manual"] == ["length"]
    assert third["collar"]["z"] - third["toe"]["z"] == pytest.approx(7.0)
    assert body["block_volume_m3"] > 0
    lengths = [math.dist(*[[h[k]["x"], h[k]["y"], h[k]["z"]] for k in ("collar", "toe")]) for h in body["holes"]]
    assert body["drilling_m"] == pytest.approx(sum(lengths))


def test_disabled_holes_are_recomputed_but_left_out_of_the_footage(client):
    holes = [_hole("1-01", 10, 5), _hole("1-02", 20, 5, enabled=False)]

    body = client.post(PATH, json={"holes": holes, "contour": CONTOUR, "surfaces": ROOF}).json()

    by_id = {item["id"]: item for item in body["holes"]}
    assert by_id["1-02"]["collar"]["z"] == pytest.approx(420.2)
    assert body["drilling_m"] == pytest.approx(11.1)


def test_unknown_manual_flag_is_rejected(client):
    hole = _hole("1-01", 10, 5)
    hole["manual"] = ["depth"]

    assert client.post(PATH, json={"holes": [hole], "contour": CONTOUR}).status_code == 422


def test_mean_bench_height_comes_with_the_volume(client):
    body = client.post(PATH, json={"holes": [], "contour": CONTOUR, "surfaces": ROOF}).json()

    # Кровля z = 420 + 0,01·x покрывает контур до x = 30 (в среднем 10,15),
    # остальные 200 м² — по отметке бровки, как в объёме: 10.
    assert body["mean_height_m"] == pytest.approx((600 * 10.15 + 200 * 10.0) / 800, abs=1e-3)
