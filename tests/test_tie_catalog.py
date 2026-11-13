"""`GET /design/tie/catalog`: номиналы ступеней систем инициирования (TASK-017, PR 4).

Палитра правки коммутации на плане берёт номиналы отсюда, а не из копии во
фронте: источник один — константы `design/timing.py`.
"""
from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import design as design_router

PATH = "/api/v1/design/tie/catalog"


@pytest.fixture()
def client() -> TestClient:
    os.environ["BLASTEX_API_KEY"] = "test-api-key"
    os.environ["BLASTEX_SESSION_SECRET"] = "test-session-secret"
    app = FastAPI()
    app.include_router(design_router.router, prefix="/api/v1")
    return TestClient(app, headers={"X-API-Key": "test-api-key"})


def test_catalog_nominals(client):
    response = client.get(PATH)
    assert response.status_code == 200
    body = response.json()
    systems = body["systems"]
    assert systems["nonel"]["surface_ms"] == [17, 25, 42, 67, 109]
    assert systems["nonel"]["downhole_ms"] == list(range(450, 1001, 50))
    assert systems["nonel"]["downhole_default_ms"] == 500
    assert systems["nonel"]["custom_surface"] is False
    assert systems["detcord"]["surface_ms"] == [10, 20, 25, 35, 42]
    assert systems["detcord"]["downhole_ms"] == []
    assert systems["electronic"]["surface_ms"] == [17, 25, 42, 67, 109]
    assert systems["electronic"]["custom_surface"] is True
    assert systems["electronic"]["downhole_default_ms"] == 0
    assert body["detcord_velocity_m_s"] == 7000
