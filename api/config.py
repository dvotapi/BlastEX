"""Настройки приложения из переменных окружения.

Одно место, где читаются переменные: иначе «а если не задано» расползается
по сервисам и появляется вторая ветка поведения без базы.
"""
from __future__ import annotations

import os


DATABASE_URL_ENV = "BLASTEX_DATABASE_URL"
INTELLIGENCE_ENABLED_ENV = "BLASTEX_INTELLIGENCE_ENABLED"
# Паспорт на бурение (TASK-015) — за флагом до PR 6 (интерфейс).
DRILL_PASSPORT_ENABLED_ENV = "BLASTEX_DRILL_PASSPORT_ENABLED"
# Выгрузка DWG скважин паспорта (TASK-015, PR 4) — выключена: LibreDWG 0.14
# пишет R2000, который AutoCAD 2022 не открывает (решение владельца 10.11.2026).
DWG_EXPORT_ENABLED_ENV = "BLASTEX_DWG_EXPORT_ENABLED"
# Проект массового взрыва по форме ВМ.09.03 (TASK-018) — за флагом до PR 6
# (интерфейс). В PR 1 флаг прячет только раздел справочника `blast_safety`.
MASS_BLAST_V2_ENABLED_ENV = "BLASTEX_MASS_BLAST_V2_ENABLED"
# Наряд-путёвка ↔ MagEX (TASK-018, PR 7) — по умолчанию выключена: включает
# владелец, когда ключ опубликован и MagEX его видит.
MAGEX_INTEGRATION_ENABLED_ENV = "BLASTEX_MAGEX_INTEGRATION_ENABLED"
MAGEX_API_URL_ENV = "MAGEX_API_URL"
MAGEX_ORGANIZATIONS_ENV = "MAGEX_ORGANIZATIONS"
SIGNING_KEY_ENV = "BLASTEX_SIGNING_KEY"
SIGNING_KID_ENV = "BLASTEX_SIGNING_KID"
JWKS_EXTRA_ENV = "BLASTEX_JWKS_EXTRA"
ALLOW_TEST_KEY_ENV = "BLASTEX_ALLOW_TEST_KEY"
MAGEX_JWS_MAX_LENGTH_ENV = "MAGEX_NARYAD_JWS_MAX_LENGTH"

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
_FALSE_VALUES = {"0", "false", "no", "off", "нет"}

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


def drill_passport_enabled() -> bool:
    """Включён ли паспорт на бурение (TASK-015).

    С PR 6 по умолчанию включён: выключает только явное «нет»
    (`0`, `false`, `no`, `off`, `нет`).
    """

    return os.getenv(DRILL_PASSPORT_ENABLED_ENV, "").strip().lower() not in _FALSE_VALUES


def dwg_export_enabled() -> bool:
    """Строить ли DWG скважин паспорта на бурение. По умолчанию нет — DXF."""

    return os.getenv(DWG_EXPORT_ENABLED_ENV, "").strip().lower() in _TRUE_VALUES


def mass_blast_v2_enabled() -> bool:
    """Включён ли проект МВ по форме ВМ.09.03 (TASK-018).

    С PR 6 по умолчанию включён: выключает только явное «нет»
    (`0`, `false`, `no`, `off`, `нет`).
    """

    return os.getenv(MASS_BLAST_V2_ENABLED_ENV, "").strip().lower() not in _FALSE_VALUES


def magex_integration_enabled() -> bool:
    """Включена ли интеграция наряд-путёвки с MagEX (TASK-018, PR 7). По умолчанию нет."""

    return os.getenv(MAGEX_INTEGRATION_ENABLED_ENV, "").strip().lower() in _TRUE_VALUES


def magex_api_url() -> str:
    """Адрес MagEX до `/api/v1` включительно, без «/» в конце; пусто — не задан."""

    return os.getenv(MAGEX_API_URL_ENV, "").strip().rstrip("/")


def magex_organizations_raw() -> str:
    """Соответствие организаций BlastEX → MagEX, JSON (разбирает `api/services/magex_settings.py`)."""

    return os.getenv(MAGEX_ORGANIZATIONS_ENV, "").strip()


def signing_key_pem() -> str:
    # В переменной окружения PEM часто пишут в одну строку с «\n».
    return os.getenv(SIGNING_KEY_ENV, "").strip().replace("\\n", "\n")


def signing_kid() -> str:
    return os.getenv(SIGNING_KID_ENV, "").strip()


def jwks_extra_raw() -> str:
    return os.getenv(JWKS_EXTRA_ENV, "").strip()


def allow_test_key() -> bool:
    """Разрешён ли тестовый ключ MagEX — только тесты и локальный стенд."""

    return os.getenv(ALLOW_TEST_KEY_ENV, "").strip().lower() in _TRUE_VALUES


def magex_jws_max_length() -> int:
    """Предел длины строки наряд-путёвки: как `VM_NARYAD_JWS_MAX_LENGTH` у MagEX (500…2 953, по умолчанию 2 000)."""

    raw = os.getenv(MAGEX_JWS_MAX_LENGTH_ENV, "").strip()
    if not raw:
        return 2000
    value = int(raw)
    if not 500 <= value <= 2953:
        raise RuntimeError(f"{MAGEX_JWS_MAX_LENGTH_ENV}: допустимо 500…2 953, задано {value}")
    return value


def features() -> dict[str, bool]:
    """Состав включённых модулей — фронт скрывает разделы по этому ответу."""

    return {
        "intelligence": intelligence_enabled(),
        "drill_passport": drill_passport_enabled(),
        "mass_blast_v2": mass_blast_v2_enabled(),
        "magex_integration": magex_integration_enabled(),
    }
