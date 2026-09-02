"""Настройки приложения из переменных окружения.

Одно место, где читаются переменные: иначе «а если не задано» расползается
по сервисам и появляется вторая ветка поведения без базы.
"""
from __future__ import annotations

import os


DATABASE_URL_ENV = "BLASTEX_DATABASE_URL"

MISSING_DATABASE_URL = (
    f"{DATABASE_URL_ENV} не задан: BlastEX хранит справочники, паспорта и "
    "расчёты только в PostgreSQL. Укажите строку подключения к базе project1."
)


def database_url() -> str:
    """Строка подключения к PostgreSQL. Без неё приложение не работает."""

    value = os.getenv(DATABASE_URL_ENV, "").strip()
    if not value:
        raise RuntimeError(MISSING_DATABASE_URL)
    return value
