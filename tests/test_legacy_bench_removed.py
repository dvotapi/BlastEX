"""Режим «полоса между двумя бровками» удалён (TASK-013, PR 2).

Блок строится контуром из чертежа (`/design/cad/sources/{id}/contour`), а не
сшивкой двух линий «верх» и «низ»: на реальных файлах маркшейдера она давала
самопересекающийся контур или уступ высотой 0,6 м.
"""
from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import design.spatial.io as spatial_io
from api.routers import design as design_router


@pytest.fixture()
def client() -> TestClient:
    os.environ["BLASTEX_API_KEY"] = "test-api-key"
    os.environ["BLASTEX_SESSION_SECRET"] = "test-session-secret"
    app = FastAPI()
    app.include_router(design_router.router, prefix="/api/v1")
    return TestClient(app, headers={"X-API-Key": "test-api-key"})


@pytest.mark.parametrize(
    "path",
    ["/api/v1/design/contour/from-polylines", "/api/v1/design/contour/import-dxf", "/api/v1/design/drawing/polylines"],
)
def test_strip_between_crests_routes_are_gone(client, path):
    assert client.post(path, json={}).status_code in (404, 405)


def test_strip_builders_are_gone_from_survey_import():
    for name in ("build_bench_from_polylines", "import_bench_dxf", "BenchDxfImport"):
        assert not hasattr(spatial_io, name), name
