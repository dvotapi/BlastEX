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
``depends_on`` перечисляет родителей ``(таблица, код)``, а ``foreign_keys``
говорит, в какую колонку положить полученный ``id`` — из ``RETURNING``
вставки этого же плана или из сохранённой связи. Поэтому внешних ключей
(``machine_type_id``, ``model_id``) в ``values`` нет. Обновление устроено так
же, как вставка: тип машины у модели и модель у единицы техники — общие поля,
и если запись переехала на другой тип, ссылка строки журнала должна переехать
вместе с ней, иначе читатель показывал бы ту же разницу после каждой
публикации.

Связь записи со строкой журнала бывает не только сохранённой: код вида
``PUB_COUNTERPARTY_1`` сам называет строку, из которой запись создана плашкой
«Из project1». Такие связи достраивает ``implicit_links`` — по тому же
правилу, что и ``compute_delta``, иначе плашка считала бы запись связанной, а
выгрузка заводила бы ей дубль.

Порядок вставок топологический, а не по таблицам: родитель всегда стоит
раньше своего потребителя, поэтому строка ``machine_types`` идёт
непосредственно перед моделью, которой она понадобилась, и вставки двух
разделов могут чередоваться. Единственная гарантия для ``writer`` — читать
план подряд.

План идёт не только по записям ревизии: связь записи, исчезнувшей из
опубликованных разделов (импорт заменил раздел целиком), тоже просматривается.
Строка журнала с признаком активности гасится (``is_active = false``), у
остальных таблиц об этом остаётся предупреждение — статусом единицы техники
распоряжается журнал. Строк журнала выгрузка не удаляет никогда, и связь
остаётся на месте: запись может вернуться следующей ревизией под тем же кодом.

Связь, потерявшая свою строку журнала (строку удалили), считается отсутствующей:
запись выгружается заново, а новая связь заменяет устаревшую. Так же её видит
``public_constraint_issues`` — иначе уникальный ключ проверялся бы у записи,
которой в журнале уже нет.

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
from cost.v2.public_sync.mapping import (
    MACHINE_KINDS,
    PublicRow,
    PublicSnapshot,
    public_code,
)
from cost.v2.references import ValidationIssue
from cost.v2.repository import PublicLink

__all__ = [
    "PublicInsert",
    "PublicUpdate",
    "PublicWritePlan",
    "WRITTEN_TABLES",
    "implicit_links",
    "plan_public_writes",
    "public_constraint_issues",
    "split_stale_links",
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

# Разделы и таблицы журнала, сопоставленные напрямую. Материалы стоят
# особняком: их таблицу выбирает вид записи (`_MATERIAL_TABLES`).
_SECTION_TABLES: dict[str, str] = {
    "counterparties": "counterparties",
    "sites": "sites",
    "equipment_types": "equipment_models",
    "equipment_assets": "equipment_units",
}

_MATERIALS_SECTION = "materials"

# Разделы, у записей которых бывает строка журнала: только их связи и
# просматриваются, когда запись исчезла из ревизии.
_MAPPED_SECTIONS: frozenset[str] = frozenset((*_SECTION_TABLES, _MATERIALS_SECTION))

# Таблицы журнала с признаком активности (`Docs/public_schema.sql`): только их
# строку и можно погасить. У моделей, типов СИ и бурового инструмента такой
# колонки нет, а активность единицы техники — это её статус, которым
# распоряжается журнал (§3), поэтому `equipment_units` сюда не входит.
_DEACTIVATABLE_TABLES: frozenset[str] = frozenset({"counterparties", "sites"})

# Таблицы журнала, строки которых план заводит и меняет: разделы, материалы и
# вспомогательные `machine_types`. Остальные таблицы `mapping.TABLES` только
# читаются, поэтому права на запись проверяются ровно по этому списку.
WRITTEN_TABLES: tuple[str, ...] = tuple(
    dict.fromkeys((*_SECTION_TABLES.values(), "machine_types", *_MATERIAL_TABLES.values()))
)

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
    """Изменившиеся колонки строки журнала.

    Ссылки описаны так же, как у ``PublicInsert``: ``values`` их не содержит,
    а ``foreign_keys`` говорит писателю, в какую колонку положить id родителя.
    Обновление без ``values``, но со ссылкой — обычное дело: у записи мог
    измениться только тип техники.
    """

    table: str
    public_id: int
    values: dict[str, Any]
    depends_on: tuple[tuple[str, str], ...] = ()
    foreign_keys: tuple[tuple[str, str, str], ...] = ()


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
    активна (неактивную незачем заводить в журнале). Связью считается и
    сохранённая, и видная по коду записи (``implicit_links``). Порядок
    вставок — от родителей к детям, чтобы ``writer`` всегда знал id родителя.

    Последними просматриваются связи записей, которых в разделах уже нет:
    их строки журнала гасятся или дают предупреждение
    (``_plan_vanished_records``).
    """

    plan = _Plan()
    # Связи по коду достраиваются здесь, а не у вызывающего: план, валидация
    # и плашка обязаны считать связи одинаково.
    index = _Index(sections, [*links, *implicit_links(sections, links, snapshot)], snapshot)

    _plan_counterparties(plan, index)
    _plan_sites(plan, index)
    # Модели, которые будут в журнале, нужны единицам техники: без родителя
    # писателю неоткуда взять `model_id`.
    model_codes = _plan_equipment_types(plan, index)
    _plan_equipment_assets(plan, index, model_codes)
    _plan_materials(plan, index)
    # Разделы пройдены по записям ревизии; связи исчезнувших записей после
    # этого остаются непросмотренными — их строки журнала гасятся отдельно.
    _plan_vanished_records(plan, index, links)
    return plan.frozen()


class _Index:
    """Разделы, связи и снимок журнала в удобном для плана виде.

    Связи разложены на живые и устаревшие: строку журнала могли удалить, и
    такая связь не должна выдавать себя за место записи в журнале.
    """

    def __init__(
        self,
        sections: Mapping[str, Sequence[ReferenceItem]],
        links: Sequence[PublicLink],
        snapshot: PublicSnapshot,
    ) -> None:
        self.sections = sections
        self.snapshot = snapshot
        self.rows = {table: snapshot.by_id(table) for table in snapshot.rows}
        live, stale = split_stale_links(links, snapshot)
        self.links = {(link.section, link.code): link for link in live}
        self.stale = stale

    def items(self, section: str) -> tuple[ReferenceItem, ...]:
        return tuple(self.sections.get(section) or ())

    def row(self, table: str, public_id: int | None) -> PublicRow | None:
        if public_id is None:
            return None
        return self.rows.get(table, {}).get(public_id)

    def link(self, section: str, code: str) -> PublicLink | None:
        return self.links.get((section, code))

    def stale_link(self, section: str, code: str) -> PublicLink | None:
        return self.stale.get((section, code))


def split_stale_links(
    links: Sequence[PublicLink], snapshot: PublicSnapshot
) -> tuple[list[PublicLink], dict[tuple[str, str], PublicLink]]:
    """Делит связи на живые и потерявшие строку журнала.

    Строку журнала могли удалить: обновлять по такому id нечего, а считать
    запись связанной — значит навсегда оставить её вне журнала. Поэтому и
    план, и проверка ограничений смотрят на неё как на несвязанную.
    """

    rows = {table: snapshot.by_id(table) for table in snapshot.rows}
    live: list[PublicLink] = []
    stale: dict[tuple[str, str], PublicLink] = {}
    for link in links:
        if int(link.public_id) in rows.get(link.public_table, {}):
            live.append(link)
        else:
            stale[(link.section, link.code)] = link
    return live, stale


# --- Неявные связи ----------------------------------------------------------


def implicit_links(
    sections: Mapping[str, Sequence[ReferenceItem]],
    links: Sequence[PublicLink],
    snapshot: PublicSnapshot,
) -> list[PublicLink]:
    """Связи, которые видно по коду записи, но которых нет в ``public_links``.

    Плашка «Из project1» даёт новой записи код ``public_code`` — имя строки
    журнала (``PUB_COUNTERPARTY_1``). Пользователь мог применить предложение
    задолго до того, как связь стала сохраняться, и такая запись выглядит
    несвязанной, хотя строка журнала у неё своя. То же правило записано в
    docstring ``compute_delta``: код черновика, совпавший с кодом строки,
    делает запись связанной. Здесь оно повторено намеренно — общий помощник
    не выделен, потому что разница считает связи по уже собранным
    предложениям, а выгрузке нужны сами ``PublicLink``.

    Строка журнала, занятая явной связью, не угадывается: у неё уже есть
    хозяин, а конфликт уникального ключа должен остаться ошибкой валидации.
    Активность записи роли не играет — связанную запись план обновляет и
    выключенной. Материал связывается только с таблицей своего вида: код
    ``PUB_TOOL_3`` у записи вида «СИ» ведёт в чужую таблицу.
    """

    explicit = {(link.section, link.code) for link in links}
    taken = {(link.public_table, int(link.public_id)) for link in links}
    codes = {
        table: {public_code(table, row.id): row.id for row in snapshot.table(table)}
        for table in (*_SECTION_TABLES.values(), *_MATERIAL_TABLES.values())
    }

    found: list[PublicLink] = []
    for section in (*_SECTION_TABLES, _MATERIALS_SECTION):
        for item in sections.get(section) or ():
            if (section, item.code) in explicit:
                continue
            table = _implicit_table(section, item)
            if table is None:
                continue
            public_id = codes[table].get(item.code)
            if public_id is None or (table, public_id) in taken:
                continue
            taken.add((table, public_id))
            found.append(
                PublicLink(
                    section=section,
                    code=item.code,
                    public_table=table,
                    public_id=public_id,
                )
            )
    return found


def _implicit_table(section: str, item: ReferenceItem) -> str | None:
    """Таблица журнала, с которой запись раздела может быть связана."""

    if section == _MATERIALS_SECTION:
        return _MATERIAL_TABLES.get(str(item.payload.get("material_kind") or ""))
    return _SECTION_TABLES.get(section)


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
        target = _target(plan, index, item, "counterparties", "counterparties")
        if target.row is not None:
            row = target.row
            changed = _changed(values, row)
            # Роли журнала только поднимаются: контрагент мог быть и клиентом,
            # и поставщиком, а в blastex роль одна — чужой флаг не сбрасываем.
            for column, wanted in (("is_client", is_client), ("is_supplier", is_supplier)):
                if wanted and not row.get(column):
                    changed[column] = True
            _add_update(plan, "counterparties", row, changed, "counterparties", item.code)
            continue
        if not target.skipped and item.is_active:
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
        target = _target(plan, index, item, "sites", "sites")
        if target.row is not None:
            _add_update(
                plan, "sites", target.row, _changed(values, target.row), "sites", item.code
            )
            continue
        if not target.skipped and item.is_active:
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
        target = _target(plan, index, item, "equipment_types", "equipment_models")
        if target.row is not None:
            model_codes.add(item.code)
            _add_update(
                plan,
                "equipment_models",
                target.row,
                _changed(values, target.row),
                "equipment_types",
                item.code,
                foreign_keys=_machine_type_change(plan, index, machine_types, item, target.row),
            )
            continue
        if target.skipped or not item.is_active:
            continue

        machine_type = _machine_type(plan, machine_types, item)
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


def _machine_type(plan: _Plan, machine_types: dict[str, str], item: ReferenceItem) -> str:
    """Название типа машины, на которое сошлётся модель.

    Написание принадлежит журналу: если такой тип там уже есть, возвращается
    его написание — по нему писатель и найдёт строку. Незнакомый тип
    заводится вставкой этого же плана и запоминается, чтобы вторая модель с
    тем же типом не завела его повторно.
    """

    name = _machine_type_name(item)
    known = machine_types.get(_machine_type_key(name))
    if known is not None:
        return known
    machine_types[_machine_type_key(name)] = name
    plan.inserts.append(
        PublicInsert(table="machine_types", values={"name": name}, section="", code=name)
    )
    return name


def _machine_type_change(
    plan: _Plan,
    index: _Index,
    machine_types: dict[str, str],
    item: ReferenceItem,
    row: PublicRow,
) -> tuple[tuple[str, str, str], ...]:
    """Ссылка на тип машины, если у связанной модели он сменился.

    ``machine_type_name`` — общее поле (``mapping``), поэтому пока строка
    журнала ссылается на прежний тип, читатель показывает ту же разницу после
    каждой публикации. Сравниваются названия, а не id: id типа в записи
    blastex нет, а название журнал пишет руками.
    """

    current = index.row("machine_types", _int(row.get("machine_type_id")))
    wanted = _machine_type_name(item)
    if _machine_type_key(current.get("name") if current else None) == _machine_type_key(wanted):
        return ()
    return (("machine_type_id", "machine_types", _machine_type(plan, machine_types, item)),)


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
    draft_types = {type_item.code for type_item in index.items("equipment_types")}
    for item in index.items("equipment_assets"):
        values = {
            "internal_id": _text(item.payload.get("inventory_number")) or item.code,
            "serial_number": _text(item.payload.get("serial_number")),
        }
        target = _target(plan, index, item, "equipment_assets", "equipment_units")
        if target.row is not None:
            row = target.row
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
                foreign_keys=_model_change(plan, index, item, row, model_codes, draft_types),
            )
            continue
        if target.skipped or not item.is_active:
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


def _model_change(
    plan: _Plan,
    index: _Index,
    item: ReferenceItem,
    row: PublicRow,
    model_codes: set[str],
    draft_types: set[str],
) -> tuple[tuple[str, str, str], ...]:
    """Ссылка на модель, если у связанной единицы сменился тип техники.

    ``equipment_type_code`` — общее поле (``mapping``), поэтому строка журнала
    обязана переехать вслед за записью. Тип, которого в разделе нет, — забота
    журнала и валидации, а не плана: судить о его модели не по чему. Тип,
    который в разделе есть, но в журнал не поедет (отключён и не связан), —
    предупреждение: ссылку переставить некуда.
    """

    type_code = str(item.payload.get("equipment_type_code") or "")
    if not type_code or type_code not in draft_types:
        return ()
    if type_code not in model_codes:
        plan.warnings.append(
            f"Единица {item.code}: тип техники не выгружается в журнал, "
            "модель в журнале не изменена."
        )
        return ()
    link = index.link("equipment_types", type_code)
    # Тип, который заводится этой же публикацией, связи ещё не имеет: id
    # модели знает только писатель, и ссылку он поставит по коду.
    if link is not None and link.public_id == _int(row.get("model_id")):
        return ()
    return (("model_id", "equipment_models", type_code),)


def _plan_materials(plan: _Plan, index: _Index) -> None:
    items = index.items("materials")
    _warn_about_unexported_materials(plan, index, items)
    for table in ("initiating_device_types", "tool_types"):
        for item in items:
            if _MATERIAL_TABLES.get(str(item.payload.get("material_kind") or "")) != table:
                continue
            values = _material_values(table, item)
            target = _target(plan, index, item, "materials", table)
            if target.row is not None:
                _add_update(
                    plan,
                    table,
                    target.row,
                    _changed(values, target.row),
                    "materials",
                    item.code,
                )
                continue
            if not target.skipped and item.is_active:
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


# --- Записи, исчезнувшие из справочника --------------------------------------


def _plan_vanished_records(
    plan: _Plan, index: _Index, links: Sequence[PublicLink]
) -> None:
    """Гасит строки журнала записей, пропавших из опубликованной ревизии.

    Импорт файлом заменяет раздел целиком, и связанная запись могла из него
    исчезнуть. Разделы планируются по записям ревизии, поэтому такую строку
    журнала никто бы не тронул: связь на месте, а ``compute_delta`` прячет
    связанные строки из предложений — вернуть строку пользователю нечем, и
    она осталась бы активной навсегда.

    Строка журнала не удаляется никогда: журнал ведёт другая система, наше
    дело — снять признак активности. У таблицы без такого признака
    (``equipment_models``, ``initiating_device_types``, ``tool_types``) и у
    единиц техники, чьим статусом распоряжается журнал (§3), остаётся одно
    предупреждение. Связи не трогаются: запись могла вернуться в следующей
    ревизии под тем же кодом. Раздела, которого в ревизии нет вовсе, это не
    касается — пустой раздел приходит как ``()``, а не отсутствующим ключом
    (``normalize_sections``).
    """

    present = {section: {item.code for item in items} for section, items in index.sections.items()}
    for link in links:
        codes = present.get(link.section)
        if link.section not in _MAPPED_SECTIONS or codes is None or link.code in codes:
            continue
        row = index.row(link.public_table, link.public_id)
        if row is None:
            # Строку журнала уже удалили: гасить нечего (см. `split_stale_links`).
            continue
        place = f"{link.public_table}#{link.public_id}"
        gone = f"Запись {link.section}/{link.code} исчезла из справочника, строка журнала"
        if link.public_table not in _DEACTIVATABLE_TABLES:
            plan.warnings.append(
                f"{gone} {place} не деактивирована: у таблицы нет признака активности."
            )
            continue
        if not _changed({"is_active": False}, row):
            # Строка уже неактивна: тревожить журнал и сметчика нечем.
            continue
        plan.updates.append(
            PublicUpdate(table=link.public_table, public_id=row.id, values={"is_active": False})
        )
        plan.warnings.append(f"{gone} {place} деактивирована.")


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


@dataclass(frozen=True)
class _Target:
    """Куда идёт запись: в свою строку журнала, во вставку или никуда.

    ``row`` — строка для обновления; пустой ``row`` при ``skipped = False``
    означает вставку (связи нет или она устарела).
    """

    row: PublicRow | None = None
    skipped: bool = False


def _target(
    plan: _Plan, index: _Index, item: ReferenceItem, section: str, table: str
) -> _Target:
    """Строка журнала записи с учётом устаревших связей и смены таблицы.

    Связь на другую таблицу остаётся у материала, которому сменили вид:
    выгружать его нужно уже в другую таблицу, и запись пропускается до
    перепривязки. Связь, потерявшая строку журнала, равна её отсутствию:
    активная запись заводится заново (новая связь заменит устаревшую),
    неактивная в журнал не попадает — и о том, и о другом сметчик узнаёт из
    предупреждения.
    """

    link = index.link(section, item.code)
    if link is not None and link.public_table != table:
        plan.warnings.append(
            f"Запись {section}/{item.code}: связь ведёт на {link.public_table}, "
            f"а выгрузка идёт в {table}; запись пропущена."
        )
        return _Target(skipped=True)
    if link is not None:
        return _Target(row=index.row(table, link.public_id))
    stale = index.stale_link(section, item.code)
    if stale is not None:
        outcome = (
            "запись создана заново."
            if item.is_active
            else "неактивная запись в журнал не заводится."
        )
        plan.warnings.append(
            f"Запись {section}/{item.code}: связь на строку "
            f"{stale.public_table}#{stale.public_id} устарела, {outcome}"
        )
    return _Target()


def _add_update(
    plan: _Plan,
    table: str,
    row: PublicRow,
    values: Mapping[str, Any],
    section: str,
    code: str,
    *,
    foreign_keys: tuple[tuple[str, str, str], ...] = (),
) -> None:
    """Кладёт в план обновление, отбросив пустые значения обязательных колонок.

    Поле в blastex необязательно, а колонка журнала — ``NOT NULL``: очищенный
    ИНН уронил бы всю транзакцию. Такую колонку план не трогает и говорит об
    этом сметчику; ошибку он увидит и в ``public_constraint_issues``.

    Обновление попадает в план и без изменившихся колонок, если у записи
    переехала ссылка: значение внешнего ключа подставит писатель.
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
    if allowed or foreign_keys:
        plan.updates.append(
            PublicUpdate(
                table=table,
                public_id=row.id,
                values=allowed,
                depends_on=tuple(
                    (parent_table, parent_code)
                    for _column, parent_table, parent_code in foreign_keys
                ),
                foreign_keys=foreign_keys,
            )
        )


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
    попадает и не проверяется. Уникальные ключи журнала (ИНН контрагента,
    наименование типа техники, инвентарный номер единицы) проверяются трижды:
    значение не должно повторяться внутри черновика, запись без связи не может
    занять значение существующей строки (её нужно не вставлять, а связать), а
    связанная — значение чужой строки; своя строка конфликтом не считается.
    Связи, видные по коду записи (``implicit_links``), учитываются наравне с
    сохранёнными — иначе запись, созданную плашкой «Из project1», нельзя было
    бы ни выгрузить, ни связать.
    """

    issues: list[ValidationIssue] = []
    if snapshot is not None:
        # Устаревшая связь равна её отсутствию: запись будет заведена заново,
        # и уникальные ключи проверяются у неё как у новой (см. `_target`).
        links, _stale = split_stale_links(
            [*links, *implicit_links(sections, links, snapshot)], snapshot
        )
    linked = {(item.section, item.code) for item in links}

    issues.extend(
        _counterparty_issues(sections, linked, _link_ids(links, "counterparties"), snapshot)
    )
    issues.extend(_site_issues(sections, linked))
    issues.extend(
        _equipment_type_issues(sections, linked, _link_ids(links, "equipment_models"), snapshot)
    )
    issues.extend(
        _equipment_asset_issues(sections, linked, _link_ids(links, "equipment_units"), snapshot)
    )
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


def _owners(snapshot: PublicSnapshot | None, table: str, column: str) -> dict[str, int]:
    """Значение уникального ключа → строка журнала, которая его занимает."""

    if snapshot is None:
        return {}
    owners: dict[str, int] = {}
    for row in snapshot.table(table):
        value = _key(row.get(column))
        if value:
            owners.setdefault(value, row.id)
    return owners


class _UniqueKey:
    """Сторож уникального ключа журнала: и чужие строки, и сам черновик.

    Значение занимает либо строка журнала, либо другая запись черновика: план
    запишет обе, и журнал откатит публикацию на своём ``UNIQUE`` — сметчик
    увидит ошибку транзакции вместо понятного замечания. Своя строка
    конфликтом не считается: связанная запись (явно или по коду ``PUB_*``)
    пишет значение туда, откуда оно и взято, а вот значение соседней строки
    журнала ей брать нельзя.
    """

    def __init__(
        self,
        snapshot: PublicSnapshot | None,
        table: str,
        column: str,
        *,
        duplicate: str,
        taken: str,
        occupied: str,
    ) -> None:
        self._owners = _owners(snapshot, table, column)
        self._drafted: set[str] = set()
        self._duplicate = duplicate
        self._taken = taken
        self._occupied = occupied

    def issues(
        self, section: str, item: ReferenceItem, field_name: str, value: Any, public_id: int | None
    ) -> list[ValidationIssue]:
        """Замечания по значению записи; ``public_id`` — её строка журнала."""

        key = _key(value)
        if not key:
            return []
        found: list[ValidationIssue] = []
        # Повтор в черновике не отменяет конфликта с журналом: сметчику нужны
        # обе ошибки сразу, а не по одной за проход.
        if key in self._drafted:
            found.append(_error(section, item.code, field_name, self._duplicate))
        self._drafted.add(key)
        owner = self._owners.get(key)
        if owner is not None and owner != public_id:
            message = self._occupied if public_id is not None else self._taken
            found.append(_error(section, item.code, field_name, message))
        return found


def _link_ids(links: Sequence[PublicLink], table: str) -> dict[tuple[str, str], int]:
    """Строка журнала записи по её связи: только связи нужной таблицы."""

    return {
        (link.section, link.code): int(link.public_id)
        for link in links
        if link.public_table == table
    }


def _counterparty_issues(
    sections: Mapping[str, Sequence[ReferenceItem]],
    linked: set[tuple[str, str]],
    link_ids: dict[tuple[str, str], int],
    snapshot: PublicSnapshot | None,
) -> list[ValidationIssue]:
    unique = _UniqueKey(
        snapshot,
        "counterparties",
        "inn",
        duplicate="ИНН повторяется в черновике: в журнале он должен быть уникальным.",
        taken=f"Контрагент с таким ИНН уже есть в журнале, {_LINK_HINT}.",
        occupied="ИНН занят другой записью журнала: журнал не примет два одинаковых.",
    )
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
        issues.extend(
            unique.issues(
                "counterparties",
                item,
                "inn",
                inn,
                link_ids.get(("counterparties", item.code)),
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
    link_ids: dict[tuple[str, str], int],
    snapshot: PublicSnapshot | None,
) -> list[ValidationIssue]:
    unique = _UniqueKey(
        snapshot,
        "equipment_models",
        "model_name",
        duplicate=(
            "Наименование типа техники повторяется в черновике: "
            "в журнале оно должно быть уникальным."
        ),
        taken=f"Тип техники с таким наименованием уже есть в журнале, {_LINK_HINT}.",
        occupied=(
            "Наименование типа техники занято другой записью журнала: "
            "журнал не примет два одинаковых."
        ),
    )
    issues: list[ValidationIssue] = []
    for item in _planned(sections, "equipment_types", linked):
        issues.extend(
            unique.issues(
                "equipment_types",
                item,
                "name",
                item.name,
                link_ids.get(("equipment_types", item.code)),
            )
        )
    return issues


def _equipment_asset_issues(
    sections: Mapping[str, Sequence[ReferenceItem]],
    linked: set[tuple[str, str]],
    link_ids: dict[tuple[str, str], int],
    snapshot: PublicSnapshot | None,
) -> list[ValidationIssue]:
    types = {item.code for item in sections.get("equipment_types") or ()}
    unique = _UniqueKey(
        snapshot,
        "equipment_units",
        "internal_id",
        duplicate=(
            "Инвентарный номер повторяется в черновике: "
            "в журнале он должен быть уникальным."
        ),
        taken=(
            "Единица техники с таким инвентарным номером уже есть "
            f"в журнале, {_LINK_HINT}."
        ),
        occupied=(
            "Инвентарный номер занят другой записью журнала: "
            "журнал не примет два одинаковых."
        ),
    )
    issues: list[ValidationIssue] = []
    for item in _planned(sections, "equipment_assets", linked):
        # Модель нужна вставке, а вставляется только активная запись: у
        # связанной ссылками распоряжается журнал, план их не меняет.
        if item.is_active:
            issues.extend(_asset_model_issues(item, types))
        internal_id = _text(item.payload.get("inventory_number")) or item.code
        issues.extend(
            unique.issues(
                "equipment_assets",
                item,
                "inventory_number",
                internal_id,
                link_ids.get(("equipment_assets", item.code)),
            )
        )
    return issues


def _asset_model_issues(item: ReferenceItem, types: set[str]) -> list[ValidationIssue]:
    """Модель единицы техники: без неё журнал строку не заведёт."""

    type_code = str(item.payload.get("equipment_type_code") or "")
    if not type_code:
        message = "Не указан тип техники: в журнале единица не существует без модели."
    elif type_code not in types:
        message = f"Тип техники {type_code} отсутствует в разделе."
    else:
        return []
    return [_error("equipment_assets", item.code, "equipment_type_code", message)]


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


def _int(value: Any) -> int | None:
    """Ссылка журнала числом; ``None`` — ссылки нет или она не число."""

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _key(value: Any) -> str:
    """Значение уникального ключа журнала для сравнения: без крайних пробелов."""

    return _text(value) or ""


def _machine_type_key(value: Any) -> str:
    """Название типа машины для сравнения: без регистра и лишних пробелов.

    Тип машины журнал заводит руками, поэтому «Буровая установка» и «буровая
    установка» — одна и та же строка; сравнение как у ``normalize_legal_name``.
    """

    return " ".join(_key(value).casefold().split())
