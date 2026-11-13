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
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import PurePath
from typing import Protocol, TypeVar

from design.spatial.cad.labels import parse_elevation
from design.spatial.cad.model import (
    ORIGIN_AUTO,
    ORIGIN_MANUAL,
    ORIGIN_TEMPLATE,
    ROLE_IGNORE,
    ROLE_SITUATION,
    SITUATION_KIND_BENCH,
    SITUATION_KIND_BOUNDARY,
    SITUATION_KIND_BUILDING,
    SITUATION_KIND_CODES,
    SITUATION_KIND_OTHER,
    SITUATION_KIND_PIT,
    SITUATION_KIND_POWER_LINE,
    SITUATION_KIND_ROAD,
    SITUATION_KIND_STOCKPILE,
    CadEntity,
)
from design.spatial.cad.roles import LayerRole, RoleAssignment, layer_key

# Порядок важен: «Карьерная автодорога» — дорога, «Склад карьера» — склад,
# «31.10.25 карьер» — съёмка борта (бровки), «Граница горного отвода» —
# граница; слово «карьер» проверяется последним.
_KIND_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (SITUATION_KIND_ROAD, re.compile(r"дорог|съезд|серпантин|проезд|автодор")),
    # «ВЛ» — только отдельным словом: «управление», «влажный» — не ЛЭП.
    (SITUATION_KIND_POWER_LINE, re.compile(r"(?<![а-яёa-z])(?:лэп|вл)(?![а-яёa-z])|электр|кабел")),
    (SITUATION_KIND_STOCKPILE, re.compile(r"склад|негабарит|штабел|отвал")),
    (
        SITUATION_KIND_BUILDING,
        re.compile(
            r"здан|сооруж|строен|бытов|вагон|(?<![а-яёa-z])(?:кпп|дск|азс)(?![а-яёa-z])"
            r"|дробил|конве[йе]|галере|весов|гараж|контор|мастерск"
        ),
    ),
    (SITUATION_KIND_BOUNDARY, re.compile(r"горного отвода|лицензи|аренд|(?<![а-яёa-z])зо(?![а-яёa-z])")),
    (
        SITUATION_KIND_BENCH,
        re.compile(r"горизонт(?!ал)\s*[+\-−]?\s*\d|откос|бровк|\d{1,2}[._]\d{1,2}[._]\d{2,4}[\s_]*карьер|карьер[\s_]*\d{1,2}[._]"),
    ),
    (SITUATION_KIND_PIT, re.compile(r"карьер")),
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



@dataclass(frozen=True)
class LayerKind:
    """Вид объектов ситуации слоя и его происхождение (вручную / шаблон / авто)."""

    name: str
    kind: str
    origin: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "kind": self.kind, "origin": self.origin}


def assign_kinds(
    entities: Iterable[CadEntity],
    template: Mapping[str, str],
    manual: Mapping[str, str] | None = None,
    *,
    all_layers: bool = False,
) -> list[LayerKind]:
    """Вид слоям, где есть объекты ситуации: вручную → шаблон объекта → по имени.

    `template` — вид по ключу слоя (только заданные человеком), `manual` — по
    имени слоя в этом файле. Вид — свойство слоя: все его объекты ситуации
    получают один вид.
    """

    manual = manual or {}
    # `all_layers` — план карьера: вид выбирают и у слоя, который пока не показан.
    names = sorted({item.layer for item in entities if all_layers or item.role == ROLE_SITUATION}, key=layer_key)
    result: list[LayerKind] = []
    for name in names:
        chosen = manual.get(name)
        stored = template.get(layer_key(name))
        if chosen in SITUATION_KIND_CODES:
            result.append(LayerKind(name, chosen, ORIGIN_MANUAL))
        elif stored in SITUATION_KIND_CODES:
            result.append(LayerKind(name, stored, ORIGIN_TEMPLATE))
        else:
            result.append(LayerKind(name, situation_kind_for_layer(name), ORIGIN_AUTO))
    return result


# --- ситуация объекта: отбор слоёв плана карьера --------------------------

# Виды, которые на плане нужны всегда (решение владельца 13.11.2026): дороги
# вокруг карьера и объекты на поверхности (КПП, ДСК…), ЛЭП — даже если слой
# скрыт в чертеже. Старые склады и отвалы, скрытые маркшейдером, — нет.
ALWAYS_SHOWN_KINDS = frozenset({SITUATION_KIND_ROAD, SITUATION_KIND_BUILDING, SITUATION_KIND_POWER_LINE})
# Слои, которым на плане ситуации не место: другие блоки, сетки и рамки
# печати, подписи и имена точек.
_JUNK_LAYER = re.compile(
    r"(?<![а-яёa-z])(?:блок[а-я]{0,2}|блк)(?![а-яёa-z])|сетк|grid|рамк|штамп|надпис|подпис|имена точек|point_desc"
    r"|(?<![а-яёa-z])dim(?![а-яёa-z])|^0$|^defpoints$"
)


def situation_layer_shown(name: str, members: Iterable[CadEntity], hidden: bool) -> bool:
    """Показывать ли слой плана карьера по умолчанию.

    Слой из одних точек и подписей (отметки) — нет; дороги, объекты на
    поверхности, ЛЭП — да, даже скрытые в чертеже; прочий слой, скрытый в
    чертеже, — нет; другие блоки, сетки, рамки, подписи — нет.
    """

    # Слой без линий и знаков (одни отметки и подписи) на плане пуст.
    if not any(item.geometry_type == "line" or item.kind == "INSERT" for item in members):
        return False
    if situation_kind_for_layer(name) in ALWAYS_SHOWN_KINDS:
        return True
    return not hidden and not _JUNK_LAYER.search(layer_key(name))


def _situation_entity_role(item: CadEntity, shown: bool) -> str:
    """Роль объекта показанного слоя: отметки (числа и точки с высотой) на плане не нужны."""

    if not shown:
        return ROLE_IGNORE
    if item.geometry_type == "text":
        return ROLE_IGNORE if parse_elevation(item.text) is not None or not item.text.strip() else ROLE_SITUATION
    if item.geometry_type == "point" and item.kind != "INSERT":
        return ROLE_IGNORE
    return ROLE_SITUATION


def assign_situation_roles(
    entities: list[CadEntity],
    template: Mapping[str, bool],
    hidden_layers: Iterable[str] = (),
    manual_layers: Mapping[str, str] | None = None,
) -> RoleAssignment:
    """Роли плана карьера: слой — «Ситуация» или «Не использовать».

    Порядок для слоя: выбор в этом файле (`manual_layers`, роль) → выбор,
    запомненный на объекте (`template`: ключ слоя → показывать) → умолчание
    (`situation_layer_shown`). Ручной выбор и шаблон — подтверждены человеком.
    """

    manual_layers = manual_layers or {}
    hidden = set(hidden_layers)
    by_layer: dict[str, list[CadEntity]] = {}
    for item in entities:
        by_layer.setdefault(item.layer, []).append(item)
    result = RoleAssignment()
    for name in sorted(by_layer, key=layer_key):
        members = by_layer[name]
        manual = manual_layers.get(name)
        stored = template.get(layer_key(name))
        if manual in (ROLE_SITUATION, ROLE_IGNORE):
            shown, origin, confirmed = manual == ROLE_SITUATION, ORIGIN_MANUAL, True
        elif stored is not None:
            shown, origin, confirmed = bool(stored), ORIGIN_TEMPLATE, True
        else:
            shown, origin, confirmed = situation_layer_shown(name, members, name in hidden), ORIGIN_AUTO, False
        role = ROLE_SITUATION if shown else ROLE_IGNORE
        result.layers.append(LayerRole(name=name, role=role, origin=origin, confirmed=confirmed))
        for item in members:
            item.role, item.role_origin = _situation_entity_role(item, shown), origin
    return result
