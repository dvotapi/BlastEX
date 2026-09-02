"""Без строки подключения приложение не стартует.

Ветка «работаем без базы» удалена: при пустом BLASTEX_DATABASE_URL половина
маршрутов отдавала 503, а данные расходились по файлам и схеме.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import config
from api.main import app
from api.services.economics_service import get_economics_repository


def test_application_refuses_to_start_without_database_url(monkeypatch) -> None:
    monkeypatch.delenv(config.DATABASE_URL_ENV, raising=False)

    with pytest.raises(RuntimeError) as error:
        with TestClient(app):
            pass

    assert config.DATABASE_URL_ENV in str(error.value)


def test_repository_dependency_reports_the_same_reason(monkeypatch) -> None:
    monkeypatch.setenv(config.DATABASE_URL_ENV, "   ")

    with pytest.raises(RuntimeError) as error:
        get_economics_repository()

    assert config.DATABASE_URL_ENV in str(error.value)


def test_database_url_is_read_from_environment(monkeypatch) -> None:
    monkeypatch.setenv(config.DATABASE_URL_ENV, " postgresql+psycopg://user@host/db ")

    assert config.database_url() == "postgresql+psycopg://user@host/db"
