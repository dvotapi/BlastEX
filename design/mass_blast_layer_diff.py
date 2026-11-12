"""Расхождение повторного переноса слоя — словами для окна проекта (TASK-018, PR 6).

`seed_diff` / `execution_seed_diff` (`design/mass_blast_layers.py`) возвращают
путь в данных слоя и значения «было / станет». Окно показывает их таблицей
«что / было / станет» без служебных ключей и без JSON: подпись и текст
значений собираются здесь, по структуре переноса `layer_seed`.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from design.mass_blast_schedule import PERSONNEL_ROLES

__all__ = ["describe_change", "describe_changes"]

_PROJECT = {
    "name": "Наименование проекта",
    "project_no": "№ проекта",
    "project_date": "Дата проекта",
    "object_name": "Объект",
    "site_code": "Код объекта",
    "blast_date": "Дата взрыва",
    "blast_time": "Время взрыва",
}
_ZONES = {"people": "Опасная зона для людей, м", "mechanisms": "Опасная зона для механизмов, м", "buildings": "Безопасное расстояние для зданий, м"}
_PARTIES = {"customer_name": "Заказчик", "contractor_name": "Подрядчик"}
_PERSON = {"position": "должность", "name": "Ф. И. О.", "authority": "основание полномочий", "is_head": "технический руководитель"}
_ROLES = {
    **PERSONNEL_ROLES,
    "blast_manager": "Ответственный руководитель массового взрыва",
    "explosives_supervisor": "Ответственный за выдачу ВМ",
}
_TOP = {
    "project_revision_id": "Ревизия проекта",
    "blocks": "Блоки (скважины, масса ВВ)",
    "materials": "ВМ по проекту",
    "explosive_kg": "Масса ВВ по проекту, кг",
    "diameter_mm": "Диаметр скважин, мм",
    "intervals": "Интервалы замедления",
    "customer_tech_contact": "Технический руководитель заказчика (организация, адрес, телефон)",
    "explosive_names": "Марки ВВ",
    "letterhead": "Бланк Общества",
    "drilled_by": "Бурение выполнил",
    "surveyor_name": "Маркшейдер — исполнитель съёмки",
    "conditions": "Условия готовности блока",
    "admittance_not_before": "Допуск не ранее",
    "volume_contour_m3": "Объём по маркшейдерскому контуру, м³",
    "specific_q_kg_m3": "Удельный расход ВВ, кг/м³",
    "acceptance_text": "Текст акта приёмки",
    "fact_issues": "Замечания по факту",
    "blocks_fact": "Число блоков с фактом",
    "kind": "Вид слоя",
}
_GROUPS = {
    "blast_manager": "Ответственный руководитель массового взрыва",
    "talon_receiver": "Получатель талона-допуска",
    "customer_approver": "Технический руководитель заказчика",
    "addressee": "Адресат уведомления",
    "contract": "Договор подряда",
    "requisites": "Реквизиты проекта",
    "fact": "Сводка выпущенного слоя «Факт»",
}
_CONTRACT = {
    "contract_no": "№ договора",
    "contract_date": "дата договора",
    "acceptance_appendix_no": "№ приложения",
    "customer_responsible": "ответственное лицо заказчика",
}
_FACT_COLUMNS = {
    "depth_fact_m": "глубина Ф, м",
    "subdrill_fact_m": "перебур Ф, м",
    "lspp_fact_m": "ЛСПП Ф, м",
    "spacing_fact_m": "между скважинами Ф, м",
    "burden_fact_m": "между рядами Ф, м",
    "charge_fact_kg": "масса заряда Ф, кг",
    "stemming_fact_m": "забойка Ф, м",
}
_DRILLED_BY = {"CUSTOMER": "заказчик", "CONTRACTOR": "Общество", "": "—"}
_BLOCK_FACT = re.compile(r"^blocks_fact\[(\d+)\](?:\.(.+))?$")


def _number(value: float) -> str:
    text = f"{value:,.3f}".rstrip("0").rstrip(".").replace(",", " ").replace(".", ",")
    return text or "0"


def _text(value: Any) -> str:
    """Значение для таблицы: число по-русски, список — перечнем, без JSON."""

    if value is None or value == "" or value == [] or value == {}:
        return "—"
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, (int, float)):
        return _number(float(value))
    if isinstance(value, str):
        return value if len(value) <= 160 else value[:157] + "…"
    if isinstance(value, Mapping):
        if "name" in value and ("quantity" in value or "project_qty" in value):
            quantity = value.get("project_qty", value.get("quantity"))
            return f"{value.get('name', '')} — {_text(quantity)} {value.get('unit', '')}".strip()
        if "code" in value and "holes" in value:
            return f"блок {value.get('code', '')}: {value.get('holes', 0)} скв., {_text(value.get('charge_kg'))} кг"
        if "position" in value or "name" in value:
            return " ".join(str(value.get(key) or "") for key in ("position", "name")).strip() or "—"
        parts = [_text(part) for part in value.values() if part not in (None, "", [], {})]
        return "; ".join(parts) if parts else "—"
    if isinstance(value, (list, tuple)):
        items = [_text(item) for item in value]
        shown = "; ".join(items[:6])
        return shown + (f"; … всего {len(items)}" if len(items) > 6 else "")
    return str(value)


def _block_fact_label(index: int, rest: str | None) -> str:
    block = f"Блок {index + 1}"
    if not rest:
        return f"{block} — факт (устья скважин по съёмке)"
    if rest == "consumption":
        return f"{block} — расход ВМ по факту"
    hole, _, column = rest.rpartition(".")
    if column in _FACT_COLUMNS and hole:
        return f"{block}, скв. {hole} — {_FACT_COLUMNS[column]}"
    return f"{block} — данные факта"


def _label(path: str) -> str:
    match = _BLOCK_FACT.match(path)
    if match:
        return _block_fact_label(int(match.group(1)), match.group(2))
    head, _, rest = path.partition(".")
    if head == "project" and rest in _PROJECT:
        return _PROJECT[rest]
    if head == "zones":
        return _ZONES.get(rest, "Опасная зона, м")
    if head == "parties":
        return _PARTIES.get(rest, "Стороны договора")
    if head == "people":
        role, _, part = rest.partition(".")
        label = _ROLES.get(role, "Ответственное лицо")
        return f"{label} — {_PERSON[part]}" if part in _PERSON else label
    if head == "contract":
        return f"Договор подряда — {_CONTRACT.get(rest, 'реквизиты')}"
    if head in _GROUPS:
        part = rest.rpartition(".")[2]
        return f"{_GROUPS[head]} — {_PERSON[part]}" if part in _PERSON else _GROUPS[head]
    if head in _TOP and not rest:
        return _TOP[head]
    return "Прочие данные проекта"


def describe_change(change: Mapping[str, Any]) -> dict[str, Any]:
    """Изменение с подписью и текстами «было / станет» для окна."""

    path = str(change.get("path") or "")
    before, after = change.get("before"), change.get("after")
    if path.endswith("drilled_by"):
        before, after = _DRILLED_BY.get(str(before or ""), before), _DRILLED_BY.get(str(after or ""), after)
    if path == "project_revision_id":
        before_text, after_text = "прежняя", "текущая"
    else:
        before_text, after_text = _text(before), _text(after)
    return {**change, "label": _label(path), "before_text": before_text, "after_text": after_text}


def describe_changes(changes: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [describe_change(change) for change in changes]
