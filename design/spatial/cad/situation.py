"""Ситуация карьера (TASK-013, PR 4): виды объектов, источники и их серии.

Ситуация — сущности роли «Ситуация» (дороги, ЛЭП, склады, контур карьера,
развалы соседних блоков). Она хранится на объекте работ, а не в паспорте.
Источник (загруженный файл) получает название и дату съёмки; источники
объекта с одинаковым названием — версии одной серии («Положение горных
работ» на 01.09 и на 01.10). Название и дата предзаполняются из имени
файла, инженер их правит.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import PurePath
from typing import Protocol, TypeVar

from design.spatial.cad.model import (
    SITUATION_KIND_BUILDING,
    SITUATION_KIND_OTHER,
    SITUATION_KIND_PIT,
    SITUATION_KIND_POWER_LINE,
    SITUATION_KIND_ROAD,
    SITUATION_KIND_STOCKPILE,
)
from design.spatial.cad.roles import layer_key

# Порядок важен: «Карьерная автодорога» — дорога, «Склад карьера» — склад;
# слово «карьер» проверяется последним.
_KIND_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (SITUATION_KIND_ROAD, re.compile(r"дорог|съезд|серпантин|проезд")),
    # «ВЛ» — только отдельным словом: «управление», «влажный» — не ЛЭП.
    (SITUATION_KIND_POWER_LINE, re.compile(r"(?<![а-яёa-z])(?:лэп|вл)(?![а-яёa-z])|электр|кабел")),
    (SITUATION_KIND_STOCKPILE, re.compile(r"склад|негабарит|штабел|отвал")),
    (SITUATION_KIND_BUILDING, re.compile(r"здан|сооруж|строен|бытов|вагон")),
    (SITUATION_KIND_PIT, re.compile(r"карьер|горного отвода")),
)

_DMY = re.compile(
    r"(?<!\d)(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})(?!\d)(?:\s*г(?![а-яё])\.?)?", re.IGNORECASE
)
_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
# Слова перед датой, которые без неё повисают: «… на», «… от», «по состоянию на».
_DANGLING = re.compile(r"(?:\s|^)(?:по\s+состоянию\s+на|на|от)\s*$", re.IGNORECASE)
_EDGE = " \t_-–—.,;:"


def situation_kind_for_layer(name: str) -> str:
    """Вид объекта ситуации по имени слоя; без совпадений — «Прочее»."""

    key = layer_key(name)
    for kind, pattern in _KIND_RULES:
        if pattern.search(key):
            return kind
    return SITUATION_KIND_OTHER


def _find_date(stem: str) -> tuple[date, int, int] | None:
    for pattern, order in ((_DMY, (2, 1, 0)), (_ISO, (0, 1, 2))):
        for match in pattern.finditer(stem):
            parts = match.groups()
            year, month, day = (int(parts[index]) for index in order)
            try:
                return date(year, month, day), match.start(), match.end()
            except ValueError:
                continue
    return None


def _clean(text: str) -> str:
    return " ".join(text.replace("_", " ").split()).strip(_EDGE)


def title_and_date_from_file_name(name: str) -> tuple[str, date | None]:
    """Название и дата съёмки из имени файла маркшейдера.

    «28.09.2026г граница блока 66.dwg» → («граница блока 66», 28.09.2026);
    «Положение горных работ на 01.09.2026.dxf» → («Положение горных работ»,
    01.09.2026). Невозможная дата (31.02) датой не считается.
    """

    stem = PurePath(name).stem.strip() if name else ""
    found = _find_date(stem)
    if found is None:
        return _clean(stem) or stem, None
    survey_date, start, end = found
    before = _DANGLING.sub("", stem[:start].replace("_", " ").rstrip(_EDGE))
    title = _clean(f"{before} {stem[end:]}")
    return title or stem, survey_date


def series_key(title: str) -> str:
    """Ключ серии: название без учёта регистра и лишних пробелов."""

    return layer_key(title)


class _Versioned(Protocol):
    survey_date: date | None
    uploaded_at: datetime


V = TypeVar("V", bound=_Versioned)


def order_versions(versions: Iterable[V]) -> list[V]:
    """Версии серии, свежие первыми: по дате съёмки, без неё — по дате загрузки."""

    def key(item: V) -> tuple[date, datetime]:
        return (item.survey_date or item.uploaded_at.date(), item.uploaded_at)

    return sorted(versions, key=key, reverse=True)

