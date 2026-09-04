"""Разница между журналом ``public`` и черновиком справочников (§4.4).

Модуль чистый: он получает уже прочитанный снимок журнала, сохранённые связи
и черновик разделов, а возвращает список предложений. Ничего не пишется — ни
в ``public``, ни в черновик: применение остаётся за пользователем.

Что считается «общим полем», решает ``Proposal.shared_fields`` из
``mapping``: список полей журнала живёт одним местом, а разница только
сравнивает по нему. Поэтому вид техники (``kind``) сюда не попадает — он
ставится при создании записи и не перетирает выбор пользователя.

Сравнение значений намеренно мягкое: ``"220"``, ``"220.0"`` и ``220`` — одно
число, пустая строка равна отсутствию ключа. Иначе черновик, прошедший через
JSON и формы интерфейса, каждый раз показывал бы ложные изменения.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterator, Literal, Mapping, Sequence

from cost.v2.models import ReferenceItem
from cost.v2.public_sync.mapping import Proposal, PublicSnapshot, build_proposals
from cost.v2.repository import PublicLink

__all__ = [
    "DeltaEntry",
    "FieldChange",
    "PublicDelta",
    "compute_delta",
]

# Источник записи, созданной из журнала: видно в справочнике и в выгрузке.
SOURCE = "project1.public"

# Поля ``ReferenceItem`` верхнего уровня: остальные имена ``shared_fields``
# относятся к ``payload``.
_TOP_LEVEL_FIELDS = frozenset({"name", "comment", "is_active", "valid_from", "valid_to"})

_PAYLOAD_PREFIX = "payload."

# Текстовые поля верхнего уровня: в ``ReferenceItem`` они всегда строки, и
# пустое значение журнала кладётся как "", а не как None.
_TEXT_FIELDS = frozenset({"name", "comment"})

# Ссылки в payload и разделы, на которые они указывают: при связывании
# записи её код меняется, и ссылки соседних предложений должны идти за ним.
_REFERENCE_FIELDS: dict[str, str] = {
    "customer_code": "counterparties",
    "supplier_code": "counterparties",
    "equipment_type_code": "equipment_types",
    "material_code": "materials",
}

# Таблицы public, коды которых нужны ``build_proposals`` до сборки ссылок.
_COUNTERPARTY_TABLE = "counterparties"
_EQUIPMENT_MODEL_TABLE = "equipment_models"

# Число в строке. Ведущий ноль в целой части запрещён нарочно: ИНН
# «0608002092» — это текст, а не число, и от «608002092» он отличается.
_NUMBER = re.compile(r"^[+-]?((0|[1-9]\d*)(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class FieldChange:
    """Одно расхождение общего поля: ``payload.short_name``, ``ЛОМ`` → ``ЛМ``."""

    key: str
    old: Any
    new: Any


@dataclass(frozen=True)
class DeltaEntry:
    """Предложение изменить черновик по строке журнала."""

    kind: Literal["new", "changed", "deactivated"]
    section: str
    public_table: str
    public_id: int
    code: str
    name: str
    # Готовая запись раздела: для «новой» — собранная из журнала, для
    # остальных — запись черновика с применёнными общими полями.
    item: dict[str, Any]
    changes: tuple[FieldChange, ...] = ()


@dataclass(frozen=True)
class PublicDelta:
    entries: tuple[DeltaEntry, ...]
    counts: dict[str, int]


def compute_delta(
    snapshot: PublicSnapshot,
    links: Sequence[PublicLink],
    draft: Mapping[str, Sequence[ReferenceItem]],
) -> PublicDelta:
    """Считает разницу журнала с черновиком справочников (§4.4).

    Строка без связи даёт предложение «новая» с кодом ``PUB_*``; если такой
    код уже есть в черновике (пользователь применил предложение, а связь ещё
    не сохранил), запись считается связанной и сравнивается. Связь без записи
    в черновике пропускается: запись удалили осознанно.
    """

    link_codes = {
        (str(item.public_table), int(item.public_id)): item.code for item in links
    }
    proposals = build_proposals(
        snapshot,
        _codes_for_table(link_codes, _COUNTERPARTY_TABLE),
        _codes_for_table(link_codes, _EQUIPMENT_MODEL_TABLE),
    )
    proposals = _apply_links(proposals, link_codes)

    index = {
        section: {item.code: item for item in items} for section, items in draft.items()
    }
    entries: list[DeltaEntry] = []
    for proposal in proposals:
        record = index.get(proposal.section, {}).get(proposal.code)
        if record is None:
            if (proposal.public_table, proposal.public_id) in link_codes:
                continue  # связь есть, а запись удалили из черновика
            entries.append(_new_entry(proposal))
            continue
        entry = _changed_entry(proposal, record)
        if entry is not None:
            entries.append(entry)

    counts = {"new": 0, "changed": 0, "deactivated": 0}
    for entry in entries:
        counts[entry.kind] += 1
    return PublicDelta(entries=tuple(entries), counts=counts)


# --- Связи ------------------------------------------------------------------


def _codes_for_table(
    link_codes: Mapping[tuple[str, int], str], table: str
) -> dict[int, str]:
    return {
        public_id: code
        for (link_table, public_id), code in link_codes.items()
        if link_table == table
    }


def _apply_links(
    proposals: Sequence[Proposal], link_codes: Mapping[tuple[str, int], str]
) -> list[Proposal]:
    """Переносит коды связей на предложения и на ссылки в их payload.

    ``build_proposals`` знает связи только контрагентов и типов техники;
    объекты, единицы техники и материалы получают код здесь. Вместе с кодом
    записи переписываются ссылки на неё у соседей — иначе цена связанного
    материала сослалась бы на несуществующий ``PUB_*``.
    """

    renames: dict[str, dict[str, str]] = {}
    for proposal in proposals:
        linked = link_codes.get((proposal.public_table, proposal.public_id))
        if linked and linked != proposal.code:
            renames.setdefault(proposal.section, {})[proposal.code] = linked
    if not renames:
        return list(proposals)

    updated: list[Proposal] = []
    for proposal in proposals:
        code = renames.get(proposal.section, {}).get(proposal.code, proposal.code)
        payload = dict(proposal.payload)
        for field_name, section in _REFERENCE_FIELDS.items():
            value = payload.get(field_name)
            if value is not None:
                payload[field_name] = renames.get(section, {}).get(value, value)
        updated.append(replace(proposal, code=code, payload=payload))
    return updated


# --- Предложения ------------------------------------------------------------


def _new_entry(proposal: Proposal) -> DeltaEntry:
    item = ReferenceItem(
        code=proposal.code,
        name=proposal.name,
        payload=dict(proposal.payload),
        is_active=proposal.is_active,
        valid_from=proposal.valid_from,
        valid_to=proposal.valid_to,
        source=SOURCE,
        comment=proposal.comment,
    )
    return DeltaEntry(
        kind="new",
        section=proposal.section,
        public_table=proposal.public_table,
        public_id=proposal.public_id,
        code=proposal.code,
        name=proposal.name,
        item=item.to_dict(),
    )


def _changed_entry(proposal: Proposal, record: ReferenceItem) -> DeltaEntry | None:
    changes = tuple(_changes(proposal, record))
    if not changes:
        return None
    item = _applied(record, changes)
    return DeltaEntry(
        kind="deactivated" if _is_deactivation(changes) else "changed",
        section=proposal.section,
        public_table=proposal.public_table,
        public_id=proposal.public_id,
        code=record.code,
        name=str(item["name"]),
        item=item,
        changes=changes,
    )


def _changes(proposal: Proposal, record: ReferenceItem) -> Iterator[FieldChange]:
    """Расхождения общих полей: старое значение — из черновика."""

    for name in proposal.shared_fields:
        if name in _TOP_LEVEL_FIELDS:
            key, old, new = name, getattr(record, name), getattr(proposal, name)
        else:
            key = f"{_PAYLOAD_PREFIX}{name}"
            old, new = record.payload.get(name), proposal.payload.get(name)
        if _comparable(old) == _comparable(new):
            continue
        yield FieldChange(key=key, old=_display(old), new=_display(new))


def _is_deactivation(changes: tuple[FieldChange, ...]) -> bool:
    """Деактивация — единственное расхождение: запись выключили в журнале."""

    return len(changes) == 1 and changes[0].key == "is_active" and changes[0].new is False


def _applied(record: ReferenceItem, changes: tuple[FieldChange, ...]) -> dict[str, Any]:
    """Запись черновика с применёнными общими полями журнала."""

    item = record.to_dict()
    payload = dict(record.payload)
    for change in changes:
        if change.key.startswith(_PAYLOAD_PREFIX):
            key = change.key[len(_PAYLOAD_PREFIX) :]
            if change.new is None:
                # Пустое поле журнала убирает ключ, а не кладёт в него None:
                # так payload остаётся таким же, как у новой записи.
                payload.pop(key, None)
            else:
                payload[key] = change.new
        elif change.key in _TEXT_FIELDS and change.new is None:
            item[change.key] = ""
        else:
            item[change.key] = change.new
    item["payload"] = payload
    return item


# --- Сравнение значений -----------------------------------------------------


def _comparable(value: Any) -> Any:
    """Значение в виде, пригодном для сравнения черновика с журналом.

    Пустая строка и отсутствующий ключ — одно и то же (``None``); число в
    любой записи (``Decimal``, ``int``, строка ``"220.0"``) — ``Decimal``;
    дата строкой ISO — ``date``. Остальное сравнивается как текст без
    крайних пробелов.
    """

    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip()
    if not text:
        return None
    if _NUMBER.match(text):
        return Decimal(text)
    if _ISO_DATE.match(text):
        return date.fromisoformat(text)
    return text


def _display(value: Any) -> Any:
    """Значение для показа и для записи в черновик: даты — строкой ISO."""

    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and not value.strip():
        return None
    return value
