"""Предзаполнение нового паспорта на бурение (TASK-015, PR 6).

Решение владельца 10.11.2026: в новом паспорте каждое поле либо заполнено,
либо заполняется само. Порядок источников для поля, не заданного в запросе:

1. справочники — объект (название, заказчик), горизонт по скважинам,
   буровой станок из «Условий бурения» объекта (или единственный буровой
   станок), его название, единица техники (№), коронка (диаметр), даты
   бурения по нормативу станка;
2. прошлый паспорт того же объекта — люди (подписи, ознакомление,
   согласования), «Составлен на основании», допуски, Wпред и станок, если
   справочники их не дали или их там нет.

Порядок работ и профиль — `_apply_site_profile` сервиса (профиль паспорта).
Номер паспорта и блок — `create_passport`. Справочник не прочитан — только
то, что можно взять из проекта и прошлого паспорта.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from api.schemas.drilling_passport import TEXT_LIMITS
from cost.model.drilling import pick_condition
from design.drilling_passport import drilling_days, floor_horizon, holes_for_passport
from design.models import BlastDesign

# Поля, которые переходят из прошлого паспорта того же объекта.
FROM_PREVIOUS = (
    "agreed_by", "approved_by", "compiled_by", "personnel", "basis", "extra_approvals",
    "tol_depth_m", "tol_collar_m", "w_max_m", "rig_type_code", "rig_name", "rig_number", "bit_diameter_mm",
)
# Из прошлого паспорта — только если справочник объекта их не дал.
FALLBACK_FROM_PREVIOUS = ("object_name", "customer")
DEFAULT_SHIFT_HOURS = 11.0


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return None
    return number


def _payload(item) -> Mapping[str, Any]:
    return dict(item.payload or {}) if item is not None else {}


def _active(snapshot, section: str) -> list:
    if snapshot is None:
        return []
    return sorted(snapshot.active_items(section), key=lambda item: item.code)


def _is_drill_rig(item) -> bool:
    return str(_payload(item).get("kind") or "DRILL_RIG") == "DRILL_RIG"


class _References:
    """Справочники снимка в виде, который ждёт `cost.model.drilling.pick_condition`."""

    def __init__(self, snapshot) -> None:
        self._snapshot = snapshot

    def items(self, section: str):
        return tuple(self._snapshot.active_items(section))


def drilling_condition(snapshot, rig_code: str, site_code: str) -> Mapping[str, Any] | None:
    """Норма бурения станка — то же правило, что у модели себестоимости:
    станок + карьер → станок + порода объекта → норма станка по умолчанию."""

    if snapshot is None or not rig_code:
        return None
    site = _payload(snapshot.item("sites", site_code)) if site_code else {}
    condition, _ = pick_condition(_References(snapshot), rig_code, str(site.get("rock_code") or "") or None, site_code or None)
    return _payload(condition) if condition is not None else None


def _rig_type(snapshot, site_code: str) -> str:
    """Буровой станок объекта: из его условий бурения, иначе единственный буровой."""

    site_rigs = {
        str(_payload(item).get("equipment_type_code") or "")
        for item in _active(snapshot, "drilling_conditions")
        if str(_payload(item).get("site_code") or "") == site_code and site_code
    } - {""}
    if len(site_rigs) == 1:
        return site_rigs.pop()
    rigs = [item.code for item in _active(snapshot, "equipment_types") if _is_drill_rig(item)]
    return rigs[0] if len(rigs) == 1 else ""


def _rig_number(snapshot, rig_code: str) -> str:
    for item in _active(snapshot, "equipment_assets"):
        payload = _payload(item)
        if str(payload.get("equipment_type_code") or "") == rig_code:
            return str(payload.get("inventory_number") or payload.get("serial_number") or "")
    return ""


def _bit_diameter(snapshot, condition: Mapping[str, Any] | None) -> float | None:
    code = str((condition or {}).get("bit_material_code") or "")
    if not code or snapshot is None:
        return None
    return _number(_payload(snapshot.item("materials", code)).get("diameter_mm"))


def shift_hours(snapshot, site_code: str) -> float:
    site = _number(_payload(snapshot.item("sites", site_code)).get("shift_hours")) if snapshot and site_code else None
    if site and site > 0:
        return site
    rates = _active(snapshot, "organization_rates")
    organization = _number(_payload(rates[0]).get("shift_hours")) if rates else None
    return organization if organization and organization > 0 else DEFAULT_SHIFT_HOURS


def _customer(snapshot, site: Mapping[str, Any]) -> str:
    code = str(site.get("customer_code") or "")
    counterparty = snapshot.item("counterparties", code) if code and snapshot is not None else None
    if counterparty is not None and counterparty.name:
        return str(counterparty.name)
    return str(site.get("customer_legal_name") or "")


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or (
        isinstance(value, Mapping) and not any(str(part or "").strip() for part in value.values())
    )


def previous_of_site(passports: Iterable[Mapping[str, Any]], site_code: str) -> Mapping[str, Any] | None:
    """Последний изменённый паспорт того же объекта (список — свежие первыми)."""

    if not site_code:
        return None
    for passport in passports:
        if str((passport.get("payload") or {}).get("site_code") or "") == site_code:
            return passport.get("payload") or {}
    return None


def prefill(
    payload: dict[str, Any],
    explicit: set[str],
    *,
    snapshot,
    design: BlastDesign,
    previous: Mapping[str, Any] | None,
    passport_date: str,
) -> None:
    """Заполнить поля нового паспорта, не заданные в запросе (на месте)."""

    def put(key: str, value: Any) -> None:
        """Пустое и не заданное в запросе поле — значением."""
        if key not in explicit and _empty(payload.get(key)) and not _empty(value):
            payload[key] = value

    # Прошлый паспорт объекта главнее умолчаний кода (согласования, допуски):
    # люди, станок и Wпред переходят из паспорта в паспорт.
    for key in FROM_PREVIOUS:
        value = (previous or {}).get(key)
        if key not in explicit and not _empty(value):
            payload[key] = value

    site_code = str(payload.get("site_code") or "")
    site_item = snapshot.item("sites", site_code) if snapshot is not None and site_code else None
    site = _payload(site_item)
    if site_item is not None:
        put("object_name", str(site_item.name or ""))
        put("customer", _customer(snapshot, site))
    for key in FALLBACK_FROM_PREVIOUS:
        put(key, (previous or {}).get(key))
    put("horizon", floor_horizon(design))
    rig_code = str(payload.get("rig_type_code") or "") or ("" if "rig_type_code" in explicit else _rig_type(snapshot, site_code))
    put("rig_type_code", rig_code)
    rig_item = snapshot.item("equipment_types", rig_code) if snapshot is not None and rig_code else None
    if rig_item is not None:
        put("rig_name", str(rig_item.name or ""))
    put("rig_number", _rig_number(snapshot, rig_code) if rig_code else "")
    condition = drilling_condition(snapshot, rig_code, site_code)
    put("bit_diameter_mm", _bit_diameter(snapshot, condition))

    # Даты бурения: начало — дата паспорта, окончание — по нормативу станка.
    put("drilling_start", passport_date)
    start = str(payload.get("drilling_start") or "")
    try:
        first_day = date.fromisoformat(start)
    except ValueError:
        fit_limits(payload, explicit)
        return
    total_m = sum(row.length_m for row in holes_for_passport(design, set()))
    days = drilling_days(
        total_m,
        speed_m_per_h=_number((condition or {}).get("tech_speed_m_per_h")),
        unproductive_h=_number((condition or {}).get("unproductive_h_per_shift")),
        shift_hours=shift_hours(snapshot, site_code),
    )
    put("drilling_end", (first_day + timedelta(days=(days or 1) - 1)).isoformat())
    fit_limits(payload, explicit)


def fit_limits(payload: dict[str, Any], explicit: set[str]) -> None:
    """Подставленные тексты — по пределам полей паспорта (`TEXT_LIMITS`).

    Названия в справочниках длиннее полей паспорта (до 300 знаков против 200
    у объекта и 80 у станка): без обрезки черновик создавался бы, а любое
    его сохранение падало бы с 422.
    """

    for key, limit in TEXT_LIMITS.items():
        value = payload.get(key)
        if key not in explicit and isinstance(value, str) and len(value) > limit:
            payload[key] = value[:limit].rstrip()
