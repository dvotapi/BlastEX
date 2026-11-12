"""Исполнение наряда в MagEX → графы наряда BlastEX после взрыва (TASK-018, PR 7, §7, решение В7).

MagEX ведёт по позиции «выписано / выдано / возвращено / израсходовано / утрачено /
на руках» в единице учёта и в кг (`GET /naryads/{id}`); строки наряда BlastEX —
по виду, марке и замедлению. Связь — строки выписки принятой версии
(`magex.lines` ревизии слоя: позиция MagEX и ключи строк наряда). Несколько
строк одной позиции: значения позиции — на первую строку, остальным 0, с
предупреждением. Разд. 1 по блокам — из `block_results`.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

__all__ = ["CONSUMPTION_ENTERED", "block_results", "consumption_entered", "explosive_consumed_kg", "values_by_line"]

CONSUMPTION_ENTERED = frozenset({"consumption_by_photo", "closed"})
_FIELDS = ("issued", "returned", "consumed")


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def consumption_entered(execution: Mapping[str, Any]) -> bool:
    """Расход внесён: статус «расход по фото» / «закрыта» или событие `consumption_entered`."""

    if str(execution.get("status") or "") in CONSUMPTION_ENTERED:
        return True
    return any(str(item.get("event") or "") == "consumption_entered" for item in execution.get("closing_events") or [])


def values_by_line(
    execution: Mapping[str, Any],
    magex_lines: Sequence[Mapping[str, Any]],
    view_lines: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, dict[str, float | None]], list[dict[str, str]]]:
    """Выдано, возвращено, израсходовано по ключам строк наряда в их единице."""

    units = {str(line.get("key")): line for line in view_lines}
    by_material = {str(line.get("material_id")): line for line in execution.get("lines") or []}
    result: dict[str, dict[str, float | None]] = {}
    issues: list[dict[str, str]] = []
    for row in magex_lines:
        keys = [str(key) for key in row.get("keys") or []]
        found = by_material.get(str(row.get("material_id")))
        if not keys or found is None:
            continue
        first = keys[0]
        line = units.get(first) or {}
        unit = str(line.get("unit") or "")
        accounting = str(row.get("unit") or "")
        values: dict[str, float | None] = {}
        for name in _FIELDS:
            qty, kg = _number(found.get(name)), _number(found.get(f"{name}_kg"))
            if unit == "кг":
                values[name] = kg if kg is not None else (qty if accounting == "kg" else None)
            elif unit == "шт" and accounting == "kg":
                mass = _number(line.get("unit_mass_kg"))
                values[name] = round(qty / mass, 3) if qty is not None and mass else None
            else:
                values[name] = qty
        result[first] = values
        for other in keys[1:]:
            result[other] = {name: 0.0 for name in _FIELDS}
        if len(keys) > 1:
            names = ", ".join(str((units.get(key) or {}).get("name") or key) for key in keys)
            issues.append({
                "level": "warning", "code": "magex_lines_merged",
                "message": f"В MagEX одна позиция на строки «{names}»: исполнение показано в первой строке.",
                "path": f"lines.{first}",
            })
    return result, issues


def block_results(execution: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Разд. 1 после взрыва по коду блока (`block_results` MagEX) — в полях строк наряда."""

    result: dict[str, dict[str, Any]] = {}
    for item in execution.get("block_results") or []:
        code = str(item.get("code") or "")
        if not code:
            continue
        row = {
            "charged_holes": item.get("holes_charged"),
            "charged_kg": _number(item.get("charged_kg")),
            "fired_holes": item.get("charges_blasted"),
            "fired_kg": _number(item.get("blasted_kg")),
            "misfired": item.get("misfires"),
            "deviation_kg": _number(item.get("deviation_kg")),
        }
        result[code] = {key: value for key, value in row.items() if value is not None}
    return result


def explosive_consumed_kg(
    execution: Mapping[str, Any], magex_lines: Sequence[Mapping[str, Any]], explosive_keys: set[str],
) -> float | None:
    """Израсходовано ВВ по наряду, кг (только когда расход внесён)."""

    if not consumption_entered(execution):
        return None
    ids = {str(row.get("material_id")) for row in magex_lines if set(map(str, row.get("keys") or [])) & explosive_keys}
    total = 0.0
    for line in execution.get("lines") or []:
        if str(line.get("material_id")) in ids:
            value = _number(line.get("consumed_kg"))
            if value is None:
                return None
            total += value
    return round(total, 3)
