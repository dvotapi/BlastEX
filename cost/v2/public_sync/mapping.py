"""Сопоставление разделов справочников blastex с таблицами схемы ``public``.

Модуль чистый: он ничего не читает и не пишет, а превращает уже прочитанный
снимок таблиц журнала (``PublicSnapshot``) в предложения записей blastex
(``Proposal``). Всё знание о полях журнала — §4.1 спецификации — собрано
здесь одним местом, поэтому изменение колонок ``public`` правится в одном
файле и ловится тестами.

Числа в ``Proposal.payload`` — строки без экспоненты (``format(Decimal,
"f")``): payload уходит в JSON, а ``Decimal`` в нём не сериализуется, при
этом строка сохраняет копейки без float-артефактов. Даты цен живут не в
payload, а в полях ``valid_from``/``valid_to`` — так же, как в
``ReferenceItem``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Mapping

from cost.v2.models import decimal_value, money

__all__ = [
    "MACHINE_KINDS",
    "Proposal",
    "PublicRow",
    "PublicSnapshot",
    "TABLES",
    "build_proposals",
    "kind_for_machine_type",
    "normalize_legal_name",
    "public_code",
]


# Таблицы `public`, которые нужны для сравнения: и сопоставленные напрямую, и
# вспомогательные (`machine_types`, `delay_series`, `contracts`) — без них не
# собрать общие поля и ссылки.
TABLES: tuple[str, ...] = (
    "counterparties",
    "sites",
    "machine_types",
    "equipment_models",
    "equipment_units",
    "initiating_device_types",
    "delay_series",
    "tool_types",
    "tools_inventory",
    "explosive_material_prices",
    "explosive_spec_items",
    "explosive_purchase_specs",
    "contracts",
)

# Виды техники blastex по реальным названиям типов машин журнала. Всё, чего
# нет в словаре («Самосвал», «Топливозаправщик», новые типы), — `OTHER`.
MACHINE_KINDS: dict[str, str] = {
    "Буровая установка": "DRILL_RIG",
    "Машина смесительно-зарядная": "SZM",
    "Автомобиль для перевозки взрывчатых веществ": "HAZMAT_TRUCK",
    "Вахтовый автобус": "LIGHT_VEHICLE",
    "Бульдозер": "TRACTOR",
    "Экскаватор": "TRACTOR",
    "Погрузчик": "TRACTOR",
}

# Префиксы кодов blastex для записей `public` без связи (§4.3). Цены имеют
# собственный префикс `PRICE_PUB_<источник>`: у одного материала их несколько.
_CODE_PREFIXES: dict[str, str] = {
    "sites": "PUB_SITE",
    "counterparties": "PUB_COUNTERPARTY",
    "equipment_models": "PUB_MODEL",
    "equipment_units": "PUB_UNIT",
    "initiating_device_types": "PUB_IDT",
    "tool_types": "PUB_TOOL",
    "explosive_material_prices": "PRICE_PUB_EMP",
    "explosive_spec_items": "PRICE_PUB_SPEC",
    "tools_inventory": "PRICE_PUB_TOOLBUY",
}

# Кавычки всех начертаний, встречающиеся в наименованиях журнала.
_QUOTES = "«»“”„‟‘’'`\""

_WRITTEN_OFF = "Списано"


@dataclass(frozen=True)
class PublicRow:
    """Строка таблицы ``public``, уже прочитанная из базы."""

    table: str
    id: int
    values: Mapping[str, Any]

    def get(self, name: str) -> Any:
        return self.values.get(name)


@dataclass(frozen=True)
class PublicSnapshot:
    """Всё, что нужно для расчёта разницы с черновиком справочников."""

    rows: Mapping[str, tuple[PublicRow, ...]]

    def table(self, name: str) -> tuple[PublicRow, ...]:
        return tuple(self.rows.get(name, ()))

    def by_id(self, name: str) -> dict[int, PublicRow]:
        """Строки таблицы по первичному ключу — для разрешения ссылок."""

        return {row.id: row for row in self.table(name)}


@dataclass(frozen=True)
class Proposal:
    """Запись blastex, построенная из строки ``public``.

    ``shared_fields`` перечисляет «общие поля» §4.1: ключи ``payload`` и поля
    верхнего уровня (``name``, ``comment``, ``is_active``, ``valid_from``,
    ``valid_to``), по которым считается разница с черновиком. Поля, которых в
    списке нет (например ``kind`` типа техники), ставятся только при создании
    записи и не перетирают выбор пользователя.
    """

    section: str
    public_table: str
    public_id: int
    code: str
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    shared_fields: tuple[str, ...] = ()
    comment: str = ""
    valid_from: date | None = None
    valid_to: date | None = None


def normalize_legal_name(text: str) -> str:
    """Нормализует юридическое имя для сравнения объекта с контрагентом.

    В журнале одно и то же общество записано то полным именем, то кратким, с
    разными кавычками и лишними пробелами (`АО «Теплогорский  карьер»` и
    `ао "теплогорский карьер"`), поэтому сравниваются регистр, пробелы и вид
    кавычек, приведённые к одному написанию.
    """

    if not text:
        return ""
    lowered = str(text).casefold()
    unified = "".join('"' if char in _QUOTES else char for char in lowered)
    return " ".join(unified.split())


def public_code(table: str, public_id: int) -> str:
    """Код записи blastex для строки ``public`` без связи (``PUB_SITE_12``)."""

    prefix = _CODE_PREFIXES.get(table, f"PUB_{table.upper()}")
    return f"{prefix}_{public_id}"


def kind_for_machine_type(name: str | None) -> str:
    """Вид техники blastex по названию типа машины журнала."""

    return MACHINE_KINDS.get((name or "").strip(), "OTHER")


def build_proposals(
    snapshot: PublicSnapshot,
    counterparty_codes: Mapping[int, str],
    type_codes: Mapping[int, str],
) -> list[Proposal]:
    """Строит предложения записей blastex по снимку ``public`` (§4.1).

    Порядок — от родителей к детям (контрагенты → объекты → типы техники →
    основные средства → материалы → цены), чтобы ссылка всегда указывала на
    уже построенное предложение. ``counterparty_codes`` и ``type_codes``
    приходят из связей ``public_links`` (id строки ``public`` → код записи
    blastex); строкам без связи код выдаётся сам, ``PUB_*``. Переданные
    словари не изменяются: функция работает с копиями.
    """

    known_counterparties = dict(counterparty_codes)
    known_types = dict(type_codes)
    device_codes: dict[int, str] = {}
    tool_codes: dict[int, str] = {}

    proposals: list[Proposal] = []
    proposals.extend(_counterparty_proposals(snapshot, known_counterparties))
    proposals.extend(_site_proposals(snapshot, known_counterparties))
    proposals.extend(_equipment_type_proposals(snapshot, known_types))
    proposals.extend(_equipment_asset_proposals(snapshot, known_types))
    proposals.extend(_device_material_proposals(snapshot, device_codes))
    proposals.extend(_tool_material_proposals(snapshot, tool_codes))
    proposals.extend(
        _price_proposals(snapshot, known_counterparties, device_codes, tool_codes)
    )
    return proposals


# --- Разделы ---------------------------------------------------------------


def _counterparty_proposals(
    snapshot: PublicSnapshot, codes: dict[int, str]
) -> list[Proposal]:
    proposals: list[Proposal] = []
    for row in snapshot.table("counterparties"):
        code = codes.setdefault(row.id, public_code(row.table, row.id))
        # Контрагент, который одновременно клиент и поставщик, в blastex
        # получает роль CUSTOMER: она главнее для расчёта выручки (§4.1).
        role = "CUSTOMER" if _flag(row.get("is_client"), default=False) else "SUPPLIER"
        payload = _clean(
            {
                "short_name": _text(row.get("short_name")),
                "inn": _text(row.get("inn")),
                "role": role,
            }
        )
        proposals.append(
            Proposal(
                section="counterparties",
                public_table=row.table,
                public_id=row.id,
                code=code,
                name=_text(row.get("full_name")) or code,
                payload=payload,
                is_active=_flag(row.get("is_active")),
                shared_fields=("name", "short_name", "inn", "role", "is_active"),
            )
        )
    return proposals


def _site_proposals(snapshot: PublicSnapshot, codes: dict[int, str]) -> list[Proposal]:
    lookup = _counterparty_lookup(snapshot)
    proposals: list[Proposal] = []
    for row in snapshot.table("sites"):
        legal_name = _text(row.get("client_legal_name"))
        customer_id = lookup.get(normalize_legal_name(legal_name or ""))
        customer_code = (
            codes.get(customer_id) or public_code("counterparties", customer_id)
            if customer_id is not None
            else None
        )
        payload = _clean(
            {
                "short_name": _text(row.get("short_name")),
                "mineral_type": _text(row.get("mineral_type")),
                "customer_code": customer_code,
                # Текст заказчика хранится, только если контрагент не найден:
                # иначе имя дублировалось бы рядом со ссылкой и расходилось.
                "customer_legal_name": None if customer_code else legal_name,
            }
        )
        proposals.append(
            Proposal(
                section="sites",
                public_table=row.table,
                public_id=row.id,
                code=public_code(row.table, row.id),
                name=_text(row.get("full_name")) or public_code(row.table, row.id),
                payload=payload,
                is_active=_flag(row.get("is_active")),
                shared_fields=(
                    "name",
                    "short_name",
                    "mineral_type",
                    "customer_code",
                    "customer_legal_name",
                    "is_active",
                ),
            )
        )
    return proposals


def _counterparty_lookup(snapshot: PublicSnapshot) -> dict[str, int]:
    """Нормализованные имена контрагентов → id строки ``public``."""

    lookup: dict[str, int] = {}
    for row in snapshot.table("counterparties"):
        for value in (row.get("short_name"), row.get("full_name")):
            key = normalize_legal_name(_text(value) or "")
            if key:
                lookup.setdefault(key, row.id)
    return lookup


def _equipment_type_proposals(
    snapshot: PublicSnapshot, codes: dict[int, str]
) -> list[Proposal]:
    machine_types = snapshot.by_id("machine_types")
    proposals: list[Proposal] = []
    for row in snapshot.table("equipment_models"):
        code = codes.setdefault(row.id, public_code(row.table, row.id))
        machine_type = machine_types.get(_int(row.get("machine_type_id")))
        machine_type_name = _text(machine_type.get("name")) if machine_type else None
        payload = _clean(
            {
                "brand": _text(row.get("brand")),
                "machine_type_name": machine_type_name,
                # kind — только для новой записи: словарь не должен менять
                # вид техники, выбранный пользователем (§4.1).
                "kind": kind_for_machine_type(machine_type_name),
            }
        )
        proposals.append(
            Proposal(
                section="equipment_types",
                public_table=row.table,
                public_id=row.id,
                code=code,
                name=_text(row.get("model_name")) or code,
                payload=payload,
                shared_fields=("name", "brand", "machine_type_name"),
            )
        )
    return proposals


def _equipment_asset_proposals(
    snapshot: PublicSnapshot, type_codes: Mapping[int, str]
) -> list[Proposal]:
    proposals: list[Proposal] = []
    for row in snapshot.table("equipment_units"):
        model_id = _int(row.get("model_id"))
        type_code = type_codes.get(model_id) or (
            public_code("equipment_models", model_id) if model_id is not None else None
        )
        internal_id = _text(row.get("internal_id"))
        payload = _clean(
            {
                "inventory_number": internal_id,
                "serial_number": _text(row.get("serial_number")),
                "equipment_type_code": type_code,
            }
        )
        proposals.append(
            Proposal(
                section="equipment_assets",
                public_table=row.table,
                public_id=row.id,
                code=public_code(row.table, row.id),
                name=internal_id or public_code(row.table, row.id),
                payload=payload,
                # Статусом единицы управляет журнал: списанная техника
                # деактивируется в blastex, обратно приложение не пишет.
                is_active=_text(row.get("status")) != _WRITTEN_OFF,
                shared_fields=(
                    "name",
                    "inventory_number",
                    "serial_number",
                    "equipment_type_code",
                    "is_active",
                ),
            )
        )
    return proposals


def _device_material_proposals(
    snapshot: PublicSnapshot, codes: dict[int, str]
) -> list[Proposal]:
    delays = _standard_delays(snapshot)
    proposals: list[Proposal] = []
    for row in snapshot.table("initiating_device_types"):
        code = codes.setdefault(row.id, public_code(row.table, row.id))
        payload = _clean(
            {
                "material_kind": "СИ",
                "storage_class": "NSI",
                "delay_ms": _number(delays.get(row.id)),
            }
        )
        proposals.append(
            Proposal(
                section="materials",
                public_table=row.table,
                public_id=row.id,
                code=code,
                name=_text(row.get("name")) or code,
                payload=payload,
                comment=_text(row.get("description")) or "",
                shared_fields=("name", "comment", "delay_ms"),
            )
        )
    return proposals


def _standard_delays(snapshot: PublicSnapshot) -> dict[int, Any]:
    """Стандартный интервал замедления по типу СИ (``is_standard = true``)."""

    delays: dict[int, Any] = {}
    for row in snapshot.table("delay_series"):
        device_id = _int(row.get("device_type_id"))
        if device_id is None or not _flag(row.get("is_standard"), default=False):
            continue
        delays.setdefault(device_id, row.get("delay_ms"))
    return delays


def _tool_material_proposals(
    snapshot: PublicSnapshot, codes: dict[int, str]
) -> list[Proposal]:
    proposals: list[Proposal] = []
    for row in snapshot.table("tool_types"):
        code = codes.setdefault(row.id, public_code(row.table, row.id))
        payload = _clean(
            {
                "material_kind": "Буровой инструмент",
                "lifetime_m": _number(row.get("expected_lifetime_meters")),
                "diameter_mm": _number(row.get("diameter")),
                "thread_type": _text(row.get("thread_type")),
            }
        )
        proposals.append(
            Proposal(
                section="materials",
                public_table=row.table,
                public_id=row.id,
                code=code,
                name=_text(row.get("name")) or code,
                payload=payload,
                comment=_text(row.get("description")) or "",
                shared_fields=(
                    "name",
                    "comment",
                    "lifetime_m",
                    "diameter_mm",
                    "thread_type",
                ),
            )
        )
    return proposals


# --- Цены ------------------------------------------------------------------

_PRICE_SHARED_FIELDS = (
    "name",
    "material_code",
    "supplier_code",
    "price_rub",
    "delivery_rub",
    "valid_from",
    "valid_to",
)


def _price_proposals(
    snapshot: PublicSnapshot,
    counterparty_codes: Mapping[int, str],
    device_codes: Mapping[int, str],
    tool_codes: Mapping[int, str],
) -> list[Proposal]:
    contracts = snapshot.by_id("contracts")

    def supplier_code(contract_id: Any) -> str | None:
        contract = contracts.get(_int(contract_id))
        if contract is None:
            return None
        counterparty_id = _int(contract.get("counterparty_id"))
        if counterparty_id is None:
            return None
        return counterparty_codes.get(counterparty_id) or public_code(
            "counterparties", counterparty_id
        )

    proposals: list[Proposal] = []
    proposals.extend(_contract_price_proposals(snapshot, device_codes, supplier_code))
    proposals.extend(_spec_price_proposals(snapshot, device_codes, supplier_code))
    proposals.extend(_tool_price_proposals(snapshot, counterparty_codes, tool_codes))
    return proposals


def _contract_price_proposals(
    snapshot: PublicSnapshot,
    device_codes: Mapping[int, str],
    supplier_code: Any,
) -> list[Proposal]:
    """Цены СИ по договору: ``price_per_unit_base / unit_conversion_factor``."""

    names = _names(snapshot, "initiating_device_types")
    proposals: list[Proposal] = []
    for row in snapshot.table("explosive_material_prices"):
        material_code = device_codes.get(_int(row.get("device_type_id")))
        if material_code is None:
            continue
        price = decimal_value(row.get("price_per_unit_base")) / _factor(
            row.get("unit_conversion_factor")
        )
        valid_from = _as_date(row.get("valid_from"))
        payload = _clean(
            {
                "material_code": material_code,
                "supplier_code": supplier_code(row.get("contract_id")),
                "price_rub": _money(price),
                "delivery_rub": _money(Decimal("0")),
            }
        )
        material_name = names.get(_int(row.get("device_type_id")), material_code)
        proposals.append(
            Proposal(
                section="material_prices",
                public_table=row.table,
                public_id=row.id,
                code=public_code(row.table, row.id),
                name=f"{material_name} — цена с {valid_from or '—'}",
                payload=payload,
                shared_fields=_PRICE_SHARED_FIELDS,
                valid_from=valid_from,
                valid_to=_as_date(row.get("valid_to")),
            )
        )
    return proposals


def _spec_price_proposals(
    snapshot: PublicSnapshot,
    device_codes: Mapping[int, str],
    supplier_code: Any,
) -> list[Proposal]:
    """Цены СИ по спецификации закупки с долей доставки.

    Доля доставки считается по той же формуле, что и представление
    ``v_explosive_unit_costs``: доставка спецификации делится на сумму
    позиций и приходится на цену пропорционально стоимости позиции.
    """

    specs = snapshot.by_id("explosive_purchase_specs")
    names = _names(snapshot, "initiating_device_types")
    items = snapshot.table("explosive_spec_items")
    factors = _delivery_factors(specs, items)

    proposals: list[Proposal] = []
    for row in items:
        material_code = device_codes.get(_int(row.get("device_type_id")))
        if material_code is None:
            continue
        spec = specs.get(_int(row.get("spec_id")))
        price = decimal_value(row.get("price_per_unit_no_vat")) / _factor(
            row.get("conversion_factor")
        )
        delivery = price * factors.get(_int(row.get("spec_id")), Decimal("0"))
        payload = _clean(
            {
                "material_code": material_code,
                "supplier_code": supplier_code(spec.get("contract_id")) if spec else None,
                "price_rub": _money(price),
                "delivery_rub": _money(delivery),
            }
        )
        spec_number = _text(spec.get("spec_number")) if spec else None
        material_name = names.get(_int(row.get("device_type_id")), material_code)
        proposals.append(
            Proposal(
                section="material_prices",
                public_table=row.table,
                public_id=row.id,
                code=public_code(row.table, row.id),
                name=f"{material_name} — спецификация {spec_number or '—'}",
                payload=payload,
                shared_fields=_PRICE_SHARED_FIELDS,
                valid_from=_as_date(spec.get("spec_date")) if spec else None,
            )
        )
    return proposals


def _delivery_factors(
    specs: Mapping[int, PublicRow], items: Iterable[PublicRow]
) -> dict[int, Decimal]:
    """Доля доставки к стоимости позиций по каждой спецификации."""

    totals: dict[int, Decimal] = {}
    for row in items:
        spec_id = _int(row.get("spec_id"))
        if spec_id is None:
            continue
        amount = decimal_value(row.get("quantity_ordered")) * decimal_value(
            row.get("price_per_unit_no_vat")
        )
        totals[spec_id] = totals.get(spec_id, Decimal("0")) + amount

    factors: dict[int, Decimal] = {}
    for spec_id, total in totals.items():
        spec = specs.get(spec_id)
        delivery = decimal_value(spec.get("total_delivery_cost_no_vat")) if spec else Decimal("0")
        factors[spec_id] = Decimal("0") if total == 0 else delivery / total
    return factors


def _tool_price_proposals(
    snapshot: PublicSnapshot,
    counterparty_codes: Mapping[int, str],
    tool_codes: Mapping[int, str],
) -> list[Proposal]:
    """Цена бурового инструмента — последняя покупка по типу и поставщику."""

    names = _names(snapshot, "tool_types")
    latest: dict[tuple[int, int | None], PublicRow] = {}
    for row in snapshot.table("tools_inventory"):
        tool_type_id = _int(row.get("tool_type_id"))
        purchase_date = _as_date(row.get("purchase_date"))
        if tool_type_id is None or purchase_date is None or row.get("purchase_price") is None:
            continue
        key = (tool_type_id, _int(row.get("supplier_id")))
        current = latest.get(key)
        if current is None or (purchase_date, row.id) >= (
            _as_date(current.get("purchase_date")),
            current.id,
        ):
            latest[key] = row

    proposals: list[Proposal] = []
    for (tool_type_id, supplier_id), row in sorted(
        latest.items(), key=lambda item: item[1].id
    ):
        material_code = tool_codes.get(tool_type_id)
        if material_code is None:
            continue
        supplier_code = (
            counterparty_codes.get(supplier_id) or public_code("counterparties", supplier_id)
            if supplier_id is not None
            else None
        )
        purchase_date = _as_date(row.get("purchase_date"))
        payload = _clean(
            {
                "material_code": material_code,
                "supplier_code": supplier_code,
                "price_rub": _money(decimal_value(row.get("purchase_price"))),
                "delivery_rub": _money(Decimal("0")),
            }
        )
        proposals.append(
            Proposal(
                section="material_prices",
                public_table=row.table,
                public_id=row.id,
                code=public_code(row.table, row.id),
                name=f"{names.get(tool_type_id, material_code)} — закупка {purchase_date}",
                payload=payload,
                shared_fields=_PRICE_SHARED_FIELDS,
                valid_from=purchase_date,
            )
        )
    return proposals


def _names(snapshot: PublicSnapshot, table: str) -> dict[int, str]:
    return {
        row.id: _text(row.get("name")) or ""
        for row in snapshot.table(table)
        if _text(row.get("name"))
    }


# --- Преобразование значений ------------------------------------------------


def _clean(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Убирает из payload ключи без значения.

    Пустое поле журнала — это отсутствие данных, а не значение `None`:
    сравнение с черновиком идёт через `payload.get(...)`, и лишний ключ
    только раздувал бы разницу.
    """

    return {key: value for key, value in payload.items() if value is not None}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _flag(value: Any, *, default: bool = True) -> bool:
    return default if value is None else bool(value)


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _number(value: Any) -> str | None:
    """Число payload строкой без экспоненты; пустое значение — `None`."""

    if value is None or value == "":
        return None
    return format(decimal_value(value), "f")


def _money(value: Decimal) -> str:
    return format(money(value), "f")


def _factor(value: Any) -> Decimal:
    """Коэффициент пересчёта единицы; ноль и пустое значение — единица."""

    factor = decimal_value(value, Decimal("1"))
    return Decimal("1") if factor == 0 else factor


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    if text is None:
        return None
    return date.fromisoformat(text[:10])
