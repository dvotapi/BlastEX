"""План выгрузки справочников blastex в схему ``public`` (журнал project1).

Модуль чистый: он получает опубликованные разделы, связи ``public_links`` и
снимок журнала, а возвращает план вставок и обновлений. SQL здесь нет —
транзакцию выполняет ``writer``. Это обратная сторона ``mapping``: там строки
журнала превращаются в записи blastex, здесь — записи blastex в колонки
журнала, и обе стороны перечисляют одни и те же «общие поля» §4.1.

Что выгружается: контрагенты, объекты, типы и единицы техники, материалы
видов «СИ» (``initiating_device_types``) и «Буровой инструмент»
(``tool_types``). Замедление СИ (``delay_ms``) не выгружается: в журнале оно
живёт в дочерней таблице ``delay_series`` и только читается; общие поля СИ —
``name`` и ``comment → description``. Статусом единицы техники распоряжается
журнал: ``equipment_units.status`` ставится только при вставке.

Ссылки между таблицами план не разрешает — их разрешает ``writer``:
``PublicInsert.depends_on`` перечисляет родителей ``(таблица, код)``, а
``PublicInsert.foreign_keys`` говорит, в какую колонку положить полученный
``id`` — из ``RETURNING`` вставки этого же плана или из сохранённой связи.
Поэтому внешних ключей (``machine_type_id``, ``model_id``) в ``values`` нет.
``PublicUpdate`` ссылок не меняет: тип машины у модели ставится один раз при
вставке и дальше остаётся за журналом.

Порядок вставок топологический, а не по таблицам: родитель всегда стоит
раньше своего потребителя, поэтому строка ``machine_types`` идёт
непосредственно перед моделью, которой она понадобилась, и вставки двух
разделов могут чередоваться. Единственная гарантия для ``writer`` — читать
план подряд.

Неактивная запись без связи в журнал не заводится, поэтому вставленная строка
``equipment_units`` всегда получает статус «В работе»: «Списано» при вставке
недостижимо. Обновление обязательной колонки журнала пустым значением
пропускается с предупреждением (``_REQUIRED_COLUMNS``) — иначе на ``NOT NULL``
упала бы вся транзакция; вставку от того же прикрывает
``public_constraint_issues``, которая проверяет и связанные записи, ведь их
план обновляет независимо от активности. Там же проверяются длины колонок
``varchar`` журнала (``_COLUMN_LIMITS``): в blastex эти поля не ограничены.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping, Sequence

from cost.v2.models import ReferenceItem, decimal_value
from cost.v2.public_sync.delta import comparable
from cost.v2.public_sync.mapping import MACHINE_KINDS, PublicRow, PublicSnapshot
from cost.v2.references import ValidationIssue
from cost.v2.repository import PublicLink

__all__ = [
    "PublicInsert",
    "PublicUpdate",
    "PublicWritePlan",
    "plan_public_writes",
    "public_constraint_issues",
]

# Статус новой единицы техники: дальше им распоряжается журнал.
_IN_WORK = "В работе"
_WRITTEN_OFF = "Списано"

# Вид техники без названия типа машины в журнале: подпись берётся обратным
# ходом по словарю `MACHINE_KINDS`, а `OTHER` в нём не встречается — для него
# подпись задана здесь.
_OTHER_MACHINE_TYPE = "Прочая техника"

# Обязательные (`NOT NULL`) колонки журнала: пустое значение в них не пишется.
_REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
    "counterparties": frozenset({"full_name", "inn"}),
    "sites": frozenset({"full_name", "client_legal_name"}),
    "machine_types": frozenset({"name"}),
    "equipment_models": frozenset({"brand", "model_name"}),
    "equipment_units": frozenset({"model_id", "internal_id"}),
    "initiating_device_types": frozenset({"name"}),
    "tool_types": frozenset({"name"}),
}

# Материалы, у которых есть таблица в журнале: остальные виды (ВВ, СВ, ТМЦ) в
# журнале не хранятся и не выгружаются.
_MATERIAL_TABLES: dict[str, str] = {
    "СИ": "initiating_device_types",
    "Буровой инструмент": "tool_types",
}

# ИНН журнала: 10 цифр у организации, 12 у предпринимателя (CHECK таблицы).
_INN_RE = re.compile(r"^[0-9]{10}([0-9]{2})?$")

# Длины колонок `varchar` журнала (Docs/public_schema.sql): значение длиннее
# журнал не примет, а в blastex такие поля не ограничены. Проверяется до
# транзакции — иначе публикация упала бы целиком на чужом ограничении.
_COLUMN_LIMITS: dict[str, dict[str, int]] = {
    "sites": {"short_name": 5},
    "equipment_models": {"model_name": 128, "brand": 128},
    "equipment_units": {"internal_id": 64, "serial_number": 128},
}


@dataclass(frozen=True)
class _LengthCheck:
    """Колонка журнала с ограниченной длиной и поле BlastEX за ней.

    ``field`` — имя поля записи blastex (его показывает форма), ``label`` —
    начало сообщения. ``fallback_to_code`` стоит там, где в журнал уходит код
    записи, если поле не заполнено (``equipment_units.internal_id``).
    """

    section: str
    table: str
    column: str
    field: str
    label: str
    fallback_to_code: bool = False


# Что и куда пишет план (см. `_plan_*`): длину проверяем ровно у тех значений,
# которые уйдут в колонки из `_COLUMN_LIMITS`.
_LENGTH_CHECKS: tuple[_LengthCheck, ...] = (
    _LengthCheck("sites", "sites", "short_name", "short_name", "Краткое имя объекта"),
    _LengthCheck(
        "equipment_types",
        "equipment_models",
        "model_name",
        "name",
        "Наименование типа техники",
    ),
    _LengthCheck("equipment_types", "equipment_models", "brand", "brand", "Марка техники"),
    _LengthCheck(
        "equipment_assets",
        "equipment_units",
        "internal_id",
        "inventory_number",
        "Инвентарный номер",
        fallback_to_code=True,
    ),
    _LengthCheck(
        "equipment_assets", "equipment_units", "serial_number", "serial_number", "Заводской номер"
    ),
)

_LINK_HINT = "свяжите записи через плашку «Из project1»"


@dataclass(frozen=True)
class PublicInsert:
    """Строка, которую нужно вставить в журнал.

    ``section`` и ``code`` — запись blastex, для которой ``writer`` сохранит
    связь по ``RETURNING id``. У вспомогательной строки ``machine_types``
    записи blastex нет: её ``section`` пуст, а ``code`` — само название типа
    машины, по которому на неё ссылаются модели.
    """

    table: str
    values: dict[str, Any]
    section: str
    code: str
    # Родители, чьи id нужны этой строке: (таблица, код) вставки того же
    # плана или сохранённой связи.
    depends_on: tuple[tuple[str, str], ...] = ()
    # Куда положить id родителя: (колонка, таблица, код).
    foreign_keys: tuple[tuple[str, str, str], ...] = ()


@dataclass(frozen=True)
class PublicUpdate:
    """Изменившиеся колонки строки журнала."""

    table: str
    public_id: int
    values: dict[str, Any]


@dataclass(frozen=True)
class PublicWritePlan:
    """Что нужно записать в журнал и о чём предупредить сметчика."""

    inserts: tuple[PublicInsert, ...] = ()
    updates: tuple[PublicUpdate, ...] = ()
    warnings: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return not self.inserts and not self.updates


@dataclass
class _Plan:
    """Копилка плана: собирается по разделам в порядке зависимостей."""

    inserts: list[PublicInsert] = field(default_factory=list)
    updates: list[PublicUpdate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def frozen(self) -> PublicWritePlan:
        return PublicWritePlan(
            inserts=tuple(self.inserts),
            updates=tuple(self.updates),
            warnings=tuple(self.warnings),
        )


def plan_public_writes(
    sections: Mapping[str, Sequence[ReferenceItem]],
    links: Sequence[PublicLink],
    snapshot: PublicSnapshot,
) -> PublicWritePlan:
    """Строит план выгрузки разделов в журнал.

    Запись со связью сравнивается со строкой журнала, и в план попадают
    только изменившиеся колонки; запись без связи вставляется, если она
    активна (неактивную незачем заводить в журнале). Порядок вставок — от
    родителей к детям, чтобы ``writer`` всегда знал id родителя.
    """

    plan = _Plan()
    index = _Index(sections, links, snapshot)

    _plan_counterparties(plan, index)
    _plan_sites(plan, index)
    # Модели, которые будут в журнале, нужны единицам техники: без родителя
    # писателю неоткуда взять `model_id`.
    model_codes = _plan_equipment_types(plan, index)
    _plan_equipment_assets(plan, index, model_codes)
    _plan_materials(plan, index)
    return plan.frozen()


class _Index:
    """Разделы, связи и снимок журнала в удобном для плана виде."""

    def __init__(
        self,
        sections: Mapping[str, Sequence[ReferenceItem]],
        links: Sequence[PublicLink],
        snapshot: PublicSnapshot,
    ) -> None:
        self.sections = sections
        self.snapshot = snapshot
        self.links = {(item.section, item.code): item for item in links}
        self.rows = {table: snapshot.by_id(table) for table in snapshot.rows}

    def items(self, section: str) -> tuple[ReferenceItem, ...]:
        return tuple(self.sections.get(section) or ())

    def row(self, table: str, public_id: int) -> PublicRow | None:
        return self.rows.get(table, {}).get(public_id)

    def link(self, section: str, code: str) -> PublicLink | None:
        return self.links.get((section, code))


# --- Разделы ---------------------------------------------------------------


def _plan_counterparties(plan: _Plan, index: _Index) -> None:
    for item in index.items("counterparties"):
        is_client, is_supplier = _role_flags(item)
        values = {
            "full_name": item.name,
            "short_name": _text(item.payload.get("short_name")),
            "inn": _text(item.payload.get("inn")),
            "is_active": item.is_active,
        }
        link = index.link("counterparties", item.code)
        if link is not None:
            row = _journal_row(plan, index, item, link, "counterparties")
            if row is None:
                continue
            changed = _changed(values, row)
            # Роли журнала только поднимаются: контрагент мог быть и клиентом,
            # и поставщиком, а в blastex роль одна — чужой флаг не сбрасываем.
            for column, wanted in (("is_client", is_client), ("is_supplier", is_supplier)):
                if wanted and not row.get(column):
                    changed[column] = True
            _add_update(plan, "counterparties", row, changed, "counterparties", item.code)
            continue
        if item.is_active:
            plan.inserts.append(
                _insert(
                    "counterparties",
                    "counterparties",
                    {**values, "is_client": is_client, "is_supplier": is_supplier},
                    item,
                )
            )


def _plan_sites(plan: _Plan, index: _Index) -> None:
    customers = {item.code: item for item in index.items("counterparties")}
    for item in index.items("sites"):
        values = {
            "full_name": item.name,
            "short_name": _text(item.payload.get("short_name")),
            "mineral_type": _text(item.payload.get("mineral_type")),
            "client_legal_name": _client_legal_name(item, customers),
            "is_active": item.is_active,
        }
        link = index.link("sites", item.code)
        if link is not None:
            row = _journal_row(plan, index, item, link, "sites")
            if row is not None:
                _add_update(plan, "sites", row, _changed(values, row), "sites", item.code)
            continue
        if item.is_active:
            plan.inserts.append(_insert("sites", "sites", values, item))


def _client_legal_name(item: ReferenceItem, customers: Mapping[str, ReferenceItem]) -> str:
    """Заказчик объекта текстом: колонка журнала ``NOT NULL`` и ссылок не знает.

    Берётся краткое имя контрагента (в журнале объекты подписаны им), затем
    полное, а если контрагента нет — текст заказчика из записи объекта.
    """

    customer = customers.get(str(item.payload.get("customer_code") or ""))
    if customer is not None:
        return _text(customer.payload.get("short_name")) or customer.name
    return _text(item.payload.get("customer_legal_name")) or ""


def _plan_equipment_types(plan: _Plan, index: _Index) -> set[str]:
    """Планирует модели журнала и возвращает коды типов, которые в нём будут."""

    # Написание типа машины журналу принадлежит: сравниваем без регистра и
    # лишних пробелов, а в план кладём то написание, которое в журнале уже
    # есть, — по нему писатель и найдёт строку.
    machine_types = {
        _machine_type_key(row.get("name")): _key(row.get("name"))
        for row in index.snapshot.table("machine_types")
    }
    model_codes: set[str] = set()

    for item in index.items("equipment_types"):
        values = {
            "model_name": item.name,
            # Колонка `brand` — NOT NULL, а марка в blastex необязательна.
            "brand": _text(item.payload.get("brand")) or "",
        }
        link = index.link("equipment_types", item.code)
        if link is not None:
            row = _journal_row(plan, index, item, link, "equipment_models")
            if row is not None:
                model_codes.add(item.code)
                _add_update(
                    plan,
                    "equipment_models",
                    row,
                    _changed(values, row),
                    "equipment_types",
                    item.code,
                )
            continue
        if not item.is_active:
            continue

        machine_type = _machine_type_name(item)
        known = machine_types.get(_machine_type_key(machine_type))
        if known is not None:
            machine_type = known
        else:
            machine_types[_machine_type_key(machine_type)] = machine_type
            plan.inserts.append(
                PublicInsert(
                    table="machine_types",
                    values={"name": machine_type},
                    section="",
                    code=machine_type,
                )
            )
        model_codes.add(item.code)
        plan.inserts.append(
            _insert(
                "equipment_models",
                "equipment_types",
                values,
                item,
                parent=("machine_type_id", "machine_types", machine_type),
            )
        )
    return model_codes


def _machine_type_name(item: ReferenceItem) -> str:
    """Название типа машины для журнала: из записи или по виду техники."""

    name = _text(item.payload.get("machine_type_name"))
    if name:
        return name
    kind = str(item.payload.get("kind") or "OTHER")
    return _KIND_MACHINE_TYPES.get(kind, _OTHER_MACHINE_TYPE)


def _unambiguous_kind_labels() -> dict[str, str]:
    """Вид техники → подпись типа машины, когда подпись у вида одна.

    У `TRACTOR` в журнале три подписи (бульдозер, экскаватор, погрузчик):
    угадывать нечего, такой вид уходит в «Прочую технику», а точное название
    сметчик задаёт полем ``machine_type_name``.
    """

    labels: dict[str, str | None] = {}
    for machine_type, kind in MACHINE_KINDS.items():
        labels[kind] = machine_type if kind not in labels else None
    return {kind: name for kind, name in labels.items() if name is not None}


_KIND_MACHINE_TYPES: dict[str, str] = _unambiguous_kind_labels()


def _plan_equipment_assets(plan: _Plan, index: _Index, model_codes: set[str]) -> None:
    for item in index.items("equipment_assets"):
        values = {
            "internal_id": _text(item.payload.get("inventory_number")) or item.code,
            "serial_number": _text(item.payload.get("serial_number")),
        }
        link = index.link("equipment_assets", item.code)
        if link is not None:
            row = _journal_row(plan, index, item, link, "equipment_units")
            if row is None:
                continue
            # Статус — за журналом: списывать технику приложение не вправе.
            # Расхождение видно сметчику, пока журнал не спишет единицу сам.
            if not item.is_active and _text(row.get("status")) != _WRITTEN_OFF:
                plan.warnings.append(
                    f"Единица {item.code} неактивна в BlastEX, "
                    "статус в журнале не изменён."
                )
            _add_update(
                plan,
                "equipment_units",
                row,
                _changed(values, row),
                "equipment_assets",
                item.code,
            )
            continue
        if not item.is_active:
            continue

        type_code = str(item.payload.get("equipment_type_code") or "")
        if type_code not in model_codes:
            # Тип техники в журнал не попадёт (отключён или его нет в
            # разделе) — подставить `model_id` будет неоткуда.
            plan.warnings.append(
                f"Единица {item.code}: тип техники не выгружается в журнал, "
                "выгрузка единицы пропущена."
            )
            continue
        plan.inserts.append(
            _insert(
                "equipment_units",
                "equipment_assets",
                {**values, "status": _IN_WORK},
                item,
                parent=("model_id", "equipment_models", type_code),
            )
        )


def _plan_materials(plan: _Plan, index: _Index) -> None:
    items = index.items("materials")
    _warn_about_unexported_materials(plan, index, items)
    for table in ("initiating_device_types", "tool_types"):
        for item in items:
            if _MATERIAL_TABLES.get(str(item.payload.get("material_kind") or "")) != table:
                continue
            values = _material_values(table, item)
            link = index.link("materials", item.code)
            if link is not None:
                row = _journal_row(plan, index, item, link, table)
                if row is not None:
                    _add_update(
                        plan, table, row, _changed(values, row), "materials", item.code
                    )
                continue
            if item.is_active:
                plan.inserts.append(_insert(table, "materials", values, item))


def _warn_about_unexported_materials(
    plan: _Plan, index: _Index, items: Sequence[ReferenceItem]
) -> None:
    """Связанный материал, которому сменили вид на невыгружаемый.

    ВВ, СВ и ТМЦ своей таблицы в журнале не имеют, но строка, с которой
    материал был связан, никуда не делась и обновляться перестала — молчать
    об этом нельзя, как и о смене таблицы.
    """

    for item in items:
        kind = str(item.payload.get("material_kind") or "")
        if kind in _MATERIAL_TABLES:
            continue
        link = index.link("materials", item.code)
        if link is None:
            continue
        plan.warnings.append(
            f"Запись materials/{item.code}: вид «{kind}» в журнал не выгружается, "
            f"строка {link.public_table}#{link.public_id} не обновляется."
        )


def _material_values(table: str, item: ReferenceItem) -> dict[str, Any]:
    values: dict[str, Any] = {"name": item.name, "description": _text(item.comment)}
    if table == "tool_types":
        values.update(
            {
                "expected_lifetime_meters": _decimal(item.payload.get("lifetime_m")),
                "diameter": _decimal(item.payload.get("diameter_mm")),
                "thread_type": _text(item.payload.get("thread_type")),
            }
        )
    return values


# --- Сборка плана -----------------------------------------------------------


def _insert(
    table: str,
    section: str,
    values: dict[str, Any],
    item: ReferenceItem,
    *,
    parent: tuple[str, str, str] | None = None,
) -> PublicInsert:
    if parent is None:
        return PublicInsert(table=table, values=values, section=section, code=item.code)
    column, parent_table, parent_code = parent
    return PublicInsert(
        table=table,
        values=values,
        section=section,
        code=item.code,
        depends_on=((parent_table, parent_code),),
        foreign_keys=((column, parent_table, parent_code),),
    )


def _journal_row(
    plan: _Plan, index: _Index, item: ReferenceItem, link: PublicLink, table: str
) -> PublicRow | None:
    """Строка журнала по связи записи; ``None`` — писать некуда.

    Связь без строки в снимке (строку удалили в журнале) — предупреждение:
    писать по такому id нечего, а вставка создала бы дубль. Связь на другую
    таблицу остаётся у материала, которому сменили вид: выгружать его нужно
    уже в другую таблицу, и запись пропускается до перепривязки.
    """

    if link.public_table != table:
        plan.warnings.append(
            f"Запись {link.section}/{item.code}: связь ведёт на {link.public_table}, "
            f"а выгрузка идёт в {table}; запись пропущена."
        )
        return None
    row = index.row(table, link.public_id)
    if row is None:
        plan.warnings.append(
            f"Запись {link.section}/{item.code}: строка журнала "
            f"{link.public_table}#{link.public_id} не найдена, выгрузка пропущена."
        )
    return row


def _add_update(
    plan: _Plan,
    table: str,
    row: PublicRow,
    values: Mapping[str, Any],
    section: str,
    code: str,
) -> None:
    """Кладёт в план обновление, отбросив пустые значения обязательных колонок.

    Поле в blastex необязательно, а колонка журнала — ``NOT NULL``: очищенный
    ИНН уронил бы всю транзакцию. Такую колонку план не трогает и говорит об
    этом сметчику; ошибку он увидит и в ``public_constraint_issues``.
    """

    required = _REQUIRED_COLUMNS.get(table, frozenset())
    allowed: dict[str, Any] = {}
    for column, value in values.items():
        if value is None and column in required:
            plan.warnings.append(
                f"Запись {section}/{code}: колонка {column} в журнале обязательна, "
                "пустое значение не записано."
            )
            continue
        allowed[column] = value
    if allowed:
        plan.updates.append(PublicUpdate(table=table, public_id=row.id, values=allowed))


def _changed(values: Mapping[str, Any], row: PublicRow) -> dict[str, Any]:
    """Колонки, значение которых в журнале отличается от записи blastex."""

    return {
        column: value
        for column, value in values.items()
        if comparable(row.get(column)) != comparable(value)
    }


# --- Ограничения журнала ----------------------------------------------------


def public_constraint_issues(
    sections: Mapping[str, Sequence[ReferenceItem]],
    links: Sequence[PublicLink],
    snapshot: PublicSnapshot | None = None,
) -> list[ValidationIssue]:
    """Ошибки, из-за которых журнал не примет выгрузку (проверка до записи).

    Проверяются записи, которые план пишет: активные и связанные — связанную
    запись план обновляет независимо от активности, и очищенное поле уронит
    транзакцию так же, как у активной. Неактивная запись без связи в журнал не
    попадает и не проверяется. Со снимком журнала дополнительно ищутся
    конфликты уникальных ключей с записями без связи: такую запись нужно не
    вставлять, а связать с существующей строкой.
    """

    issues: list[ValidationIssue] = []
    linked = {(item.section, item.code) for item in links}

    issues.extend(_counterparty_issues(sections, linked, snapshot))
    issues.extend(_site_issues(sections, linked))
    issues.extend(_equipment_type_issues(sections, linked, snapshot))
    issues.extend(_equipment_asset_issues(sections, linked, snapshot))
    issues.extend(_length_issues(sections, linked))
    return issues


def _length_issues(
    sections: Mapping[str, Sequence[ReferenceItem]], linked: set[tuple[str, str]]
) -> list[ValidationIssue]:
    """Значения, которые не влезут в колонку журнала (``_COLUMN_LIMITS``)."""

    issues: list[ValidationIssue] = []
    for check in _LENGTH_CHECKS:
        limit = _COLUMN_LIMITS[check.table][check.column]
        for item in _planned(sections, check.section, linked):
            value = _length_value(check, item)
            if len(value) <= limit:
                continue
            if check.fallback_to_code and value == item.code:
                message = (
                    f"{check.label} не заполнен, в журнал уходит код записи, "
                    f"а он длиннее {limit} символов — журнал его не примет."
                )
            else:
                message = f"{check.label} длиннее {limit} символов — журнал его не примет."
            issues.append(_error(check.section, item.code, check.field, message))
    return issues


def _length_value(check: _LengthCheck, item: ReferenceItem) -> str:
    """Значение, которое план положит в колонку журнала.

    Наименование записи (``name``) живёт не в payload, а в самой записи; для
    ``internal_id`` пустое поле заменяется кодом записи — как в
    ``_plan_equipment_assets``.
    """

    value = item.name.strip() if check.field == "name" else _text(item.payload.get(check.field))
    if not value and check.fallback_to_code:
        return item.code
    return value or ""


def _taken(snapshot: PublicSnapshot | None, table: str, column: str) -> set[str]:
    """Занятые в журнале значения уникального ключа; без снимка — пусто."""

    if snapshot is None:
        return set()
    return {_key(row.get(column)) for row in snapshot.table(table)}


def _counterparty_issues(
    sections: Mapping[str, Sequence[ReferenceItem]],
    linked: set[tuple[str, str]],
    snapshot: PublicSnapshot | None,
) -> list[ValidationIssue]:
    taken = _taken(snapshot, "counterparties", "inn")
    issues: list[ValidationIssue] = []
    for item in _planned(sections, "counterparties", linked):
        inn = _text(item.payload.get("inn")) or ""
        if not inn:
            issues.append(
                _error(
                    "counterparties",
                    item.code,
                    "inn",
                    "Не заполнен ИНН: журнал требует ИНН у каждого контрагента.",
                )
            )
            continue
        if not _INN_RE.fullmatch(inn):
            issues.append(
                _error(
                    "counterparties",
                    item.code,
                    "inn",
                    "ИНН должен состоять из 10 или 12 цифр.",
                )
            )
            continue
        if inn in taken and ("counterparties", item.code) not in linked:
            issues.append(
                _error(
                    "counterparties",
                    item.code,
                    "inn",
                    f"Контрагент с таким ИНН уже есть в журнале, {_LINK_HINT}.",
                )
            )
    return issues


def _site_issues(
    sections: Mapping[str, Sequence[ReferenceItem]], linked: set[tuple[str, str]]
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for item in _planned(sections, "sites", linked):
        if not item.payload.get("customer_code") and not _text(
            item.payload.get("customer_legal_name")
        ):
            issues.append(
                _error(
                    "sites",
                    item.code,
                    "customer_code",
                    "Не указан заказчик: журнал требует наименование заказчика объекта.",
                )
            )
    return issues


def _equipment_type_issues(
    sections: Mapping[str, Sequence[ReferenceItem]],
    linked: set[tuple[str, str]],
    snapshot: PublicSnapshot | None,
) -> list[ValidationIssue]:
    taken = _taken(snapshot, "equipment_models", "model_name")
    issues: list[ValidationIssue] = []
    seen: set[str] = set()
    for item in _active(sections, "equipment_types"):
        name = _key(item.name)
        if name in seen:
            # Повтор внутри раздела не отменяет конфликта с журналом: сметчику
            # нужны обе ошибки сразу, а не по одной за проход.
            issues.append(
                _error(
                    "equipment_types",
                    item.code,
                    "name",
                    "Наименование типа техники повторяется: "
                    "в журнале оно должно быть уникальным.",
                )
            )
        seen.add(name)
        if name in taken and ("equipment_types", item.code) not in linked:
            issues.append(
                _error(
                    "equipment_types",
                    item.code,
                    "name",
                    f"Тип техники с таким наименованием уже есть в журнале, {_LINK_HINT}.",
                )
            )
    return issues


def _equipment_asset_issues(
    sections: Mapping[str, Sequence[ReferenceItem]],
    linked: set[tuple[str, str]],
    snapshot: PublicSnapshot | None,
) -> list[ValidationIssue]:
    types = {item.code for item in sections.get("equipment_types") or ()}
    taken = _taken(snapshot, "equipment_units", "internal_id")
    issues: list[ValidationIssue] = []
    for item in _active(sections, "equipment_assets"):
        type_code = str(item.payload.get("equipment_type_code") or "")
        if not type_code:
            issues.append(
                _error(
                    "equipment_assets",
                    item.code,
                    "equipment_type_code",
                    "Не указан тип техники: в журнале единица не существует без модели.",
                )
            )
        elif type_code not in types:
            issues.append(
                _error(
                    "equipment_assets",
                    item.code,
                    "equipment_type_code",
                    f"Тип техники {type_code} отсутствует в разделе.",
                )
            )
        internal_id = _text(item.payload.get("inventory_number")) or item.code
        if internal_id in taken and ("equipment_assets", item.code) not in linked:
            issues.append(
                _error(
                    "equipment_assets",
                    item.code,
                    "inventory_number",
                    "Единица техники с таким инвентарным номером уже есть "
                    f"в журнале, {_LINK_HINT}.",
                )
            )
    return issues


def _active(
    sections: Mapping[str, Sequence[ReferenceItem]], section: str
) -> list[ReferenceItem]:
    return [item for item in (sections.get(section) or ()) if item.is_active]


def _planned(
    sections: Mapping[str, Sequence[ReferenceItem]],
    section: str,
    linked: set[tuple[str, str]],
) -> list[ReferenceItem]:
    """Записи, которые план пишет в журнал: активные и связанные."""

    return [
        item
        for item in (sections.get(section) or ())
        if item.is_active or (section, item.code) in linked
    ]


def _error(section: str, code: str, field_name: str, message: str) -> ValidationIssue:
    return ValidationIssue("error", section, code, message, field_name)


# --- Преобразование значений ------------------------------------------------


def _role_flags(item: ReferenceItem) -> tuple[bool, bool]:
    """Флаги журнала по роли контрагента: заказчик — клиент, прочие — поставщики."""

    is_client = str(item.payload.get("role") or "CUSTOMER") == "CUSTOMER"
    return is_client, not is_client


def _text(value: Any) -> str | None:
    """Текст без крайних пробелов; пустое значение — ``None`` (в журнале NULL)."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return decimal_value(value)


def _key(value: Any) -> str:
    """Значение уникального ключа журнала для сравнения: без крайних пробелов."""

    return _text(value) or ""


def _machine_type_key(value: Any) -> str:
    """Название типа машины для сравнения: без регистра и лишних пробелов.

    Тип машины журнал заводит руками, поэтому «Буровая установка» и «буровая
    установка» — одна и та же строка; сравнение как у ``normalize_legal_name``.
    """

    return " ".join(_key(value).casefold().split())
