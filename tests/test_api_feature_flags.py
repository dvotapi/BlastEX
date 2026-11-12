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


def _client(monkeypatch, *, intelligence: bool, drill_passport: bool = False) -> TestClient:
    monkeypatch.setenv(config.DATABASE_URL_ENV, "postgresql+psycopg://user@host/project1")
    monkeypatch.setenv("BLASTEX_API_KEY", "test-api-key")
    monkeypatch.setenv(config.INTELLIGENCE_ENABLED_ENV, "true" if intelligence else "false")
    monkeypatch.setenv(config.DRILL_PASSPORT_ENABLED_ENV, "true" if drill_passport else "false")
    monkeypatch.delenv(config.MASS_BLAST_V2_ENABLED_ENV, raising=False)
    monkeypatch.delenv(config.MAGEX_INTEGRATION_ENABLED_ENV, raising=False)
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
        "intelligence": False,
        "drill_passport": False,
        "mass_blast_v2": True,
        "magex_integration": False,
    }
    assert _client(monkeypatch, intelligence=True).get("/api/v1/features").json() == {
        "intelligence": True,
        "drill_passport": False,
        "mass_blast_v2": True,
        "magex_integration": False,
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


def test_drill_passport_routes_follow_the_flag(monkeypatch) -> None:
    """Паспорт на бурение (TASK-015) за флагом: выключен — маршрутов нет, 404."""

    disabled = _client(monkeypatch, intelligence=False)
    assert disabled.post("/api/v1/design/drilling-passports", json={"design_id": "x"}).status_code == 404
    assert "/api/v1/design/drilling-passports" not in disabled.get("/openapi.json").json()["paths"]
    assert disabled.get("/api/v1/design/drilling-passports/revisions/x/passport.pdf").status_code == 404
    assert disabled.get("/api/v1/design/drilling-passports/revisions/x/holes.dxf").status_code == 404
    assert disabled.get("/api/v1/design/drilling-passports/revisions/x/holes.dwg").status_code == 404

    enabled = _client(monkeypatch, intelligence=False, drill_passport=True)
    paths = enabled.get("/openapi.json").json()["paths"]
    assert "/api/v1/design/drilling-passports" in paths
    assert "/api/v1/design/drilling-passports/{passport_id}/revisions" in paths
    assert "/api/v1/design/drilling-passports/revisions/{revision_id}/passport.pdf" in paths
    assert "/api/v1/design/drilling-passports/revisions/{revision_id}/holes.dxf" in paths
    assert "/api/v1/design/drilling-passports/revisions/{revision_id}/holes.dwg" in paths
    assert enabled.get("/api/v1/features").json()["drill_passport"] is True


def test_drill_passport_enabled_by_default(monkeypatch) -> None:
    """С PR 6 паспорт на бурение включён: без переменной маршруты есть."""

    _client(monkeypatch, intelligence=False)
    monkeypatch.delenv(config.DRILL_PASSPORT_ENABLED_ENV, raising=False)
    module = importlib.reload(importlib.import_module("api.main"))
    client = TestClient(module.app, headers={"X-API-Key": "test-api-key"})
    assert client.get("/api/v1/features").json()["drill_passport"] is True
    assert "/api/v1/design/drilling-passports/{passport_id}/preview.pdf" in client.get("/openapi.json").json()["paths"]


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "нет", " False "])
def test_drill_passport_can_be_switched_off(monkeypatch, value: str) -> None:
    monkeypatch.setenv(config.DRILL_PASSPORT_ENABLED_ENV, value)
    assert config.drill_passport_enabled() is False


@pytest.mark.parametrize("value", ["", "1", "true", "да", "что-то"])
def test_drill_passport_other_values_keep_it_on(monkeypatch, value: str) -> None:
    monkeypatch.setenv(config.DRILL_PASSPORT_ENABLED_ENV, value)
    assert config.drill_passport_enabled() is True


@pytest.mark.parametrize(
    ("value", "enabled"), [(None, True), ("", True), ("1", True), ("да", True), ("0", False), ("false", False), ("нет", False)]
)
def test_mass_blast_v2_flag_is_on_by_default(monkeypatch, value, enabled) -> None:
    """Проект МВ по форме ВМ.09.03 (TASK-018): с PR 6 включён, выключает только явное «нет»."""

    if value is None:
        monkeypatch.delenv(config.MASS_BLAST_V2_ENABLED_ENV, raising=False)
    else:
        monkeypatch.setenv(config.MASS_BLAST_V2_ENABLED_ENV, value)
    assert config.mass_blast_v2_enabled() is enabled
    assert config.features()["mass_blast_v2"] is enabled

