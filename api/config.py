"""Настройки приложения из переменных окружения.

Одно место, где читаются переменные: иначе «а если не задано» расползается
по сервисам и появляется вторая ветка поведения без базы.
"""
from __future__ import annotations

import os


DATABASE_URL_ENV = "BLASTEX_DATABASE_URL"
INTELLIGENCE_ENABLED_ENV = "BLASTEX_INTELLIGENCE_ENABLED"

# Префиксы ML-слоя: роутеры регистрируются только при включённом флаге.
INTELLIGENCE_PREFIXES: tuple[str, ...] = (
    "datasets",
    "calibration",
    "outcomes",
    "learning",
    "registry",
    "drift",
    "spatial",
    "recommendation",
    "optimization",
)

_TRUE_VALUES = {"1", "true", "yes", "on", "да"}

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


def intelligence_enabled() -> bool:
    """Включён ли ML-слой.

    По умолчанию выключен: код `intelligence/` и `design/optimization`
    остаётся на месте, но в ближайший релиз не входит.
    """

    return os.getenv(INTELLIGENCE_ENABLED_ENV, "").strip().lower() in _TRUE_VALUES


def features() -> dict[str, bool]:
    """Состав включённых модулей — фронт скрывает разделы по этому ответу."""

    return {"intelligence": intelligence_enabled()}
