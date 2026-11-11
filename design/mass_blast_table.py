"""Таблица параметров взрывных работ (прил. 11 ФНП 494) как данные (TASK-018, PR 2, §3.2).

По каждой включённой скважине проекта блока — графы прил. 11 (Р; графы Ф
пустые, их заполнит PR 5 по факту заряжания) и служебные величины для
техрасчёта (объём на скважину, η_з, r_разл, НСИ, ПД кг, q), которые рендер не
печатает. Масса заряда — по декам проекта, округлена до шага профиля
документов (по умолчанию 5 кг); итог — по округлённым. Разбивка на страницы
и «общая запись» повторов — дело рендера (PR 3).

Примечание — только действие: «снизить заряд», если ЛСПП у подошвы меньше
0,8·W проекта (`toe_line.floor_burdens`, `short`; решение владельца В4), плюс
ручное примечание проекта МВ к скважине. Примечание, общее для ≥ 60 %
скважин, выносится в шапку.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Mapping, Sequence

from design.drilling_passport import first_row_selection
from design.editing import local_spacing, logical_row, row_family, row_index
from design.models import BlastDesign, Hole, HoleLoad, explosive_charge_mass_kg, is_explosive_deck_kind
from design.safety.holes import MaterialIndex, _row_step, primer_items, primer_mass_kg
from design.toe_line import floor_burdens

__all__ = ["COMMON_NOTE_SHARE", "NOTE_REDUCE_CHARGE", "ParameterTable", "parameter_table", "round_to_step"]

NOTE_REDUCE_CHARGE = "снизить заряд"
COMMON_NOTE_SHARE = 0.6
DEFAULT_CHARGE_ROUND_KG = 5.0


def round_to_step(value: float, step: float) -> float:
    """Округление до кратного шагу, половина — вверх (как MROUND формы)."""

    if step <= 0:
        return value
    units = (Decimal(str(value)) / Decimal(str(step))).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return float(units * Decimal(str(step)))


def _natural(hole_id: str) -> tuple:
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", hole_id))


def _water_column(hole: Hole) -> float | None:
    """Столб воды: от верха воды до забоя; воды нет — пусто."""

    tops = [min(item.from_m, item.to_m) for item in hole.water_intervals]
    if not tops:
        return None
    return max(0.0, hole.length_m - min(tops))


@dataclass(frozen=True)
class ParameterTable:
    rows: list[dict[str, Any]]
    totals: dict[str, Any]
    common_note: str
    charge_round_kg: float
    issues: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "totals": self.totals,
            "common_note": self.common_note,
            "charge_round_kg": self.charge_round_kg,
        }


def _row_steps(enabled: list[Hole]) -> dict[str, float | None]:
    """Шаг между рядами у скважины; у первого ряда — шаг ближайшей скважины ряда позади него."""

    index = row_index(enabled)
    same_row: dict[int, list[Hole]] = {}
    for hole in enabled:
        same_row.setdefault(hole.row, []).append(hole)
    steps = {hole.id: _row_step(index, same_row[hole.row], hole) for hole in enabled}
    for hole in enabled:
        if steps[hole.id] is not None:
            continue
        behind = index.get((row_family(hole.kind), logical_row(hole.row) + 1), [])
        if behind:
            nearest = min(behind, key=lambda o: math.hypot(o.collar.x - hole.collar.x, o.collar.y - hole.collar.y))
            steps[hole.id] = steps.get(nearest.id)
    return steps


def parameter_table(
    design: BlastDesign,
    materials: MaterialIndex,
    *,
    charge_round_kg: float = DEFAULT_CHARGE_ROUND_KG,
    hole_notes: Mapping[str, str] | None = None,
    flyrock_by_hole: Mapping[str, float] | None = None,
    stemming_by_hole: Mapping[str, float] | None = None,
) -> ParameterTable:
    """Строки прил. 11 по включённым скважинам проекта блока (проект не меняется).

    `stemming_by_hole` — l_заб над верхним зарядом из `safety.holes` (та же,
    что в разлёте и K_з), `flyrock_by_hole` — r_разл по скважине.
    """

    enabled = [hole for hole in design.holes if hole.enabled]
    loads: dict[str, HoleLoad] = {load.hole_id: load for load in design.loads}
    first_row, _ = first_row_selection(design)
    burdens = floor_burdens(design) if first_row else {}
    steps = _row_steps(enabled)
    same_row: dict[int, list[Hole]] = {}
    for hole in enabled:
        same_row.setdefault(hole.row, []).append(hole)
    notes = {str(key): str(value).strip() for key, value in (hole_notes or {}).items() if str(value or "").strip()}
    rows: list[dict[str, Any]] = []
    for hole in sorted(enabled, key=lambda item: _natural(item.id)):
        load = loads.get(hole.id)
        decks = list(load.decks) if load else []
        charge = explosive_charge_mass_kg(decks)
        primers = primer_items(load)
        primer_kg = sum(mass for mass in (primer_mass_kg(item, materials) for item in primers) if mass is not None)
        is_first = hole.id in first_row
        burden = burdens.get(hole.id) if is_first else None
        spacing = local_spacing(same_row[hole.row], hole)
        step = steps.get(hole.id)
        bench = hole.length_m - hole.subdrill_m
        auto = NOTE_REDUCE_CHARGE if burden is not None and burden.short else ""
        note = "; ".join(item for item in (auto, notes.get(hole.id, "")) if item)
        volume = bench * spacing * step if spacing and step else None
        charge_length = sum(abs(d.to_m - d.from_m) for d in decks if is_explosive_deck_kind(d.kind))
        water = _water_column(hole)
        rows.append(
            {
                "hole_id": hole.id,
                "first_row": is_first,
                "diameter_mm": round(hole.diameter_mm),
                "bench_height_m": round(bench, 1),
                "depth_m": round(hole.length_m, 1),
                "depth_fact_m": None,
                "subdrill_m": round(hole.subdrill_m, 1),
                "subdrill_fact_m": None,
                "water_m": None if water is None else round(water, 1),
                "lspp_m": None if burden is None else round(burden.value_m, 2),
                "lspp_fact_m": None,
                "spacing_m": None if spacing is None else round(spacing, 2),
                "spacing_fact_m": None,
                "burden_m": None if step is None else round(step, 2),
                "burden_fact_m": None,
                "charge_kg": round_to_step(charge, charge_round_kg),
                "charge_fact_kg": None,
                "stemming_m": round((stemming_by_hole or {}).get(hole.id, 0.0), 1),
                "stemming_fact_m": None,
                "primers_pcs": len(primers),
                "note": note,
                # служебные — не печатаются
                "charge_exact_kg": round(charge, 3),
                "volume_m3": None if volume is None else round(volume, 1),
                "eta_charge": round(charge_length / hole.length_m, 3) if hole.length_m > 0 else None,
                "flyrock_r_m": (flyrock_by_hole or {}).get(hole.id),
                "nsi_downhole_pcs": len(primers),
                "primer_kg": round(primer_kg, 3),
                "q_kg_m3": round((charge + primer_kg) / volume, 2) if volume else None,
            }
        )

    common = _common_note(rows)
    if common:
        for row in rows:
            parts = [part.strip() for part in row["note"].split(";") if part.strip()]
            row["note"] = "; ".join(part for part in parts if part != common)
    return ParameterTable(rows=rows, totals=_totals(rows), common_note=common, charge_round_kg=charge_round_kg)


def _common_note(rows: Sequence[Mapping[str, Any]]) -> str:
    counter = Counter(part.strip() for row in rows for part in str(row["note"]).split(";") if part.strip())
    if not counter or not rows:
        return ""
    note, count = counter.most_common(1)[0]
    return note if count >= COMMON_NOTE_SHARE * len(rows) else ""


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _totals(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def known(key: str) -> list[float]:
        return [float(row[key]) for row in rows if row[key] is not None]

    volumes = known("volume_m3")
    mean_a, mean_b, mean_sub = _mean(known("spacing_m")), _mean(known("burden_m")), _mean(known("subdrill_m"))
    charge = sum(known("charge_kg"))
    primer_kg = sum(known("primer_kg"))
    flyrock = known("flyrock_r_m")
    depths = known("depth_m")
    volume = sum(volumes) if rows and len(volumes) == len(rows) else None
    return {
        "hole_count": len(rows),
        "depth_m": round(sum(depths), 1),
        "depth_mean_m": round(sum(depths) / len(depths), 2) if depths else None,
        "depth_min_m": min(depths) if depths else None,
        "depth_max_m": max(depths) if depths else None,
        "subdrill_mean_m": None if mean_sub is None else round(mean_sub, 1),
        "spacing_mean_m": None if mean_a is None else round(mean_a, 2),
        "burden_mean_m": None if mean_b is None else round(mean_b, 2),
        "charge_kg": round(charge, 3),
        "charge_max_kg": max(known("charge_kg")) if rows else None,
        "stemming_min_m": min(known("stemming_m")) if rows else None,
        "primers_pcs": int(sum(known("primers_pcs"))),
        "first_row_count": sum(1 for row in rows if row["first_row"]),
        # служебные
        "volume_m3": None if volume is None else round(volume, 1),
        "flyrock_max_m": max(flyrock) if flyrock else None,
        "primer_kg": round(primer_kg, 3),
        "q_kg_m3": round((charge + primer_kg) / volume, 2) if volume else None,
    }
