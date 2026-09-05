"""Настройки обмена справочников blastex со схемой ``public``.

Переключатель обмена и список включённых зеркал разделов хранятся в одной и
той же таблице (``blastex.public_mirror_sections``), через уже существующие
методы репозитория ``list_mirror_sections`` / ``set_mirror_section``: обмен —
служебная запись с ключом ``EXCHANGE_KEY``, зеркало раздела — запись с ключом
самого раздела. Модуль переводит эти плоские флаги в типизированные
настройки и обратно, чтобы логика не дублировалась между
``InMemoryEconomicsRepository`` и ``PostgresEconomicsRepository``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from cost.v2.public_sync.mapping import SECTION_TABLES
from cost.v2.references import REFERENCE_SECTION_DEFINITIONS
from cost.v2.schemas import SECTION_SCHEMAS

__all__ = [
    "EXCHANGE_KEY",
    "MAPPED_SECTIONS",
    "PublicSyncSettings",
    "flags_from_settings",
    "mirrorable_sections",
    "settings_from_flags",
]

# Ключ переключателя обмена в таблице `public_mirror_sections` — рядом с
# ключами разделов-зеркал, но не раздел справочника.
EXCHANGE_KEY = "_exchange"

# Разделы, обмен которых со схемой `public` устроен прямым сопоставлением
# таблиц, а не зеркалированием раздела целиком: ровно те, у которых есть
# таблица журнала (`SECTION_TABLES` — единственный источник правды об этом).
# Отдельного флага-зеркала у них нет: они не входят в
# `mirrorable_sections()`. Цены материалов приходят из журнала
# (`explosive_material_prices`) и обратно не выгружаются — зеркалить их
# незачем и вредно: в журнале появилась бы вторая копия своих же цен.
MAPPED_SECTIONS: tuple[str, ...] = tuple(SECTION_TABLES)


@dataclass(frozen=True)
class PublicSyncSettings:
    """Настройки обмена организации со схемой ``public``."""

    exchange_enabled: bool
    mirror_sections: frozenset[str]  # включённые зеркала, без EXCHANGE_KEY


def mirrorable_sections() -> tuple[str, ...]:
    """Разделы, которые можно включить как зеркало целиком.

    Раздел годится, если у него есть схема (`SECTION_SCHEMAS`), он не входит
    в `MAPPED_SECTIONS` и не помечен устаревшим (`deprecated`). Порядок —
    как в `REFERENCE_SECTION_DEFINITIONS`.
    """
    return tuple(
        section
        for section, definition in REFERENCE_SECTION_DEFINITIONS.items()
        if section in SECTION_SCHEMAS
        and section not in MAPPED_SECTIONS
        and not definition.get("deprecated")
    )


def settings_from_flags(flags: Mapping[str, bool]) -> PublicSyncSettings:
    """Плоские флаги `public_mirror_sections` → типизированные настройки.

    Флаги вне `mirrorable_sections()` (например, устаревший или неизвестный
    раздел, случайно оставшийся в таблице) молча игнорируются — настройки
    показывают только то, чем сейчас можно управлять.
    """
    exchange_enabled = bool(flags.get(EXCHANGE_KEY, False))
    mirror_sections = frozenset(section for section in mirrorable_sections() if flags.get(section, False))
    return PublicSyncSettings(exchange_enabled=exchange_enabled, mirror_sections=mirror_sections)


def flags_from_settings(settings: PublicSyncSettings) -> dict[str, bool]:
    """Настройки → полный набор флагов для записи через `set_mirror_section`.

    Раздел из `settings.mirror_sections`, которого нет среди
    `mirrorable_sections()` (например, раздел из `MAPPED_SECTIONS` или вовсе
    неизвестный), — ошибка, а не молчаливо забытая запись.
    """
    # Локальный импорт: `cost.v2.repository` тянет за собой пакет
    # `cost.v2.public_sync` (через `delta.py`), поэтому импорт на уровне
    # модуля создал бы цикл при загрузке `cost.v2.repository`.
    from cost.v2.repository import EconomicsRepositoryError

    known = mirrorable_sections()
    unknown = sorted(set(settings.mirror_sections) - set(known))
    if unknown:
        raise EconomicsRepositoryError(
            f"Неизвестный раздел зеркала обмена: {', '.join(unknown)}."
        )

    flags: dict[str, bool] = {EXCHANGE_KEY: settings.exchange_enabled}
    flags.update({section: section in settings.mirror_sections for section in known})
    return flags
