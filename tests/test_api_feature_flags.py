"""ML-слой включается переменной окружения, а не правкой кода.

Код `intelligence/` и `design/optimization` остаётся в репозитории: при
выключенном флаге его маршруты отвечают 501, остальное приложение работает
как раньше.
"""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from api import config

DISABLED_CALLS: tuple[tuple[str, str], ...] = (
    ("POST", "/api/v1/datasets"),
    ("POST", "/api/v1/calibration/train"),
    ("POST", "/api/v1/outcomes/train"),
    ("POST", "/api/v1/learning/prior"),
    ("GET", "/api/v1/registry/models"),
    ("POST", "/api/v1/drift/report"),
    ("POST", "/api/v1/spatial/train"),
    ("POST", "/api/v1/design/recommend"),
    ("POST", "/api/v1/design/optimize"),
)


def _client(monkeypatch, *, intelligence: bool) -> TestClient:
    monkeypatch.setenv(config.DATABASE_URL_ENV, "postgresql+psycopg://user@host/project1")
    monkeypatch.setenv("BLASTEX_API_KEY", "test-api-key")
    monkeypatch.setenv(config.INTELLIGENCE_ENABLED_ENV, "true" if intelligence else "false")
    module = importlib.reload(importlib.import_module("api.main"))
    return TestClient(module.app, headers={"X-API-Key": "test-api-key"})


@pytest.fixture(autouse=True)
def _restore_main():
    """Модуль приложения перечитывается на каждый флаг — вернуть исходный."""

    yield
    importlib.reload(importlib.import_module("api.main"))


@pytest.mark.parametrize(("method", "path"), DISABLED_CALLS)
def test_disabled_module_answers_501(monkeypatch, method: str, path: str) -> None:
    client = _client(monkeypatch, intelligence=False)

    response = client.request(method, path, json={})

    assert response.status_code == 501
    body = response.json()
    assert body["error_type"] == "module_disabled"
    assert config.INTELLIGENCE_ENABLED_ENV in body["detail"]


def test_features_endpoint_reports_the_flag(monkeypatch) -> None:
    assert _client(monkeypatch, intelligence=False).get("/api/v1/features").json() == {
        "intelligence": False
    }
    assert _client(monkeypatch, intelligence=True).get("/api/v1/features").json() == {
        "intelligence": True
    }


def test_enabled_flag_restores_routes(monkeypatch) -> None:
    client = _client(monkeypatch, intelligence=True)

    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/datasets" in paths
    assert "/api/v1/design/optimize" in paths


def test_other_routes_keep_working_while_module_is_disabled(monkeypatch) -> None:
    client = _client(monkeypatch, intelligence=False)

    assert client.get("/api/v1/design/passport/roles").status_code == 200
    assert client.get("/health").status_code == 200
