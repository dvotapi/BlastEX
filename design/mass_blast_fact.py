"""Факт бурения и заряжания блока для документов проекта МВ (TASK-018, PR 5).

Факт пишется в проект блока (`BlastDesign.as_drilled_holes`,
`as_charged_holes`, `as_fired_holes` — `design/as_drilled.py`,
`as_charged.py`, `as_fired.py`); здесь он сводится в графы «Ф» таблицы
параметров (прил. 11), фактический расход ВМ и точки Г.1 по исполнительной
съёмке. Проект блока не меняется: величины Ф считаются **теми же функциями,
что Р**, на копии проекта с фактической геометрией (решения владельца
12.11.2026, план PR 5 §2):

- глубина — фактическая длина по оси (`AsDrilledHole.length_m`);
- перебур — Δ_ф = L_ф − (Z_уст.ф − Z_подошвы)/cos α_ф, подошва — проектная
  (Z_уст.проект − H_у), как в формуле длины L = (S − Z)/cos α + Δ (В4);
- ЛСПП, расстояние между скважинами и между рядами — `toe_line.floor_burdens`,
  `editing.local_spacing` и шаг рядов таблицы по смешанной сетке: факт, где
  он есть, иначе проект; печатаются только у скважин с фактом бурения (В5);
- масса заряда — как записано, до 1 кг (В3); забойка — над верхним зарядом
  по фактическим декам, как Р.

Отказы и примечания по факту вводятся в слое «Факт» и накладываются при
показе (`design/mass_blast_layers.execution_view`), а не здесь.
"""
from __future__ import annotations

import math
import re
from copy import deepcopy
from typing import Any, Iterable, Mapping, Sequence

from design.as_charged import normalize_as_charged
from design.as_drilled import normalize_as_drilled
from design.as_fired import normalize_as_fired
from design.editing import local_spacing
from design.lifecycle import execution_payload
from design.mass_blast import content_sha256
from design.mass_blast_calc import explosives_consumption
from design.mass_blast_table import _row_steps, round_to_step
from design.models import (
    AsChargedHole,
    AsDrilledHole,
    BlastDesign,
    Deck,
    Hole,
    HoleLoad,
    Point3,
    is_explosive_deck_kind,
)
from design.safety.holes import _top_stemming
from design.toe_line import floor_burdens

__all__ = [
    "FACT_CHARGE_ROUND_KG",
    "FACT_VERSION",
    "OFFSET_TOLERANCE_M",
    "block_fact",
    "execution_sha256",
    "fact_subdrill_m",
]

FACT_VERSION = "fact-v1"
# Масса заряда Ф — замер: до 1 кг, без округления до шага Р (решение В3).
FACT_CHARGE_ROUND_KG = 1.0
# Допуск отклонения устья от проекта — условие 2 акта готовности (±0,5 м).
OFFSET_TOLERANCE_M = 0.5
# Факта в BlastEX нет у поверхностных соединителей и стартеров: их расход —
# вручную в наряде (решение В9).
NO_FACT_KINDS = frozenset({"nsi_surface", "starter"})
COPY_METHOD = "copy"


def _natural(hole_id: str) -> tuple:
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", hole_id))


def _r(value: float | None, digits: int) -> float | None:
    return None if value is None else round(float(value), digits)


def execution_sha256(design: BlastDesign) -> str:
    """Отпечаток факта проекта блока: запись факта после переноса его меняет."""

    return content_sha256(execution_payload(design))


def fact_subdrill_m(designed: Hole, drilled: AsDrilledHole) -> float | None:
    """Перебур по факту: длина за проектной отметкой подошвы по оси фактической скважины.

    Подошва у скважины — Z_уст.проект − H_у (`Hole.bench_height_m`, по
    вертикали); Δ_ф = L_ф − (Z_уст.ф − Z_подошвы)/cos α_ф. Отрицательный —
    недобур до подошвы.
    """

    floor_z = designed.collar.z - designed.bench_height_m
    cos_a = math.cos(math.radians(_fact_angle_deg(drilled.actual_collar, _actual_toe(designed, drilled))))
    if cos_a < 1e-6:
        return None
    return drilled.length_m - (drilled.actual_collar.z - floor_z) / cos_a


def _actual_toe(designed: Hole, drilled: AsDrilledHole) -> Point3:
    """Забой по факту на фактической длине (`AsDrilledHole.length_m`).

    Направление — по записанным устью и забою; забоя нет (совпадает с
    устьем) — по проектной оси. Длина — записанная: глубину правят после
    копии проекта, а забой остаётся проектным — тогда он сдвигается по оси,
    иначе перебур (по длине) и точка подошвы (по забою) разошлись бы.
    """

    collar, toe = drilled.actual_collar, drilled.actual_toe
    axis = (toe.x - collar.x, toe.y - collar.y, toe.z - collar.z)
    if math.hypot(*axis) <= 0.01:
        axis = (designed.toe.x - designed.collar.x, designed.toe.y - designed.collar.y, designed.toe.z - designed.collar.z)
    norm = math.hypot(*axis)
    length = drilled.length_m
    if norm <= 1e-9 or length <= 0:
        return toe
    k = length / norm
    return Point3(x=collar.x + axis[0] * k, y=collar.y + axis[1] * k, z=collar.z + axis[2] * k)


def _fact_angle_deg(collar: Point3, toe: Point3) -> float:
    horizontal = math.hypot(toe.x - collar.x, toe.y - collar.y)
    vertical = collar.z - toe.z
    return 0.0 if horizontal == 0.0 and vertical == 0.0 else math.degrees(math.atan2(horizontal, vertical))


def _fact_geometry(design: BlastDesign, drilled: Mapping[str, AsDrilledHole]) -> BlastDesign:
    """Копия проекта блока: у скважин с фактом бурения — фактические устье, забой и перебур.

    Перебур копии — Δ_ф: тогда точка оси на уровне подошвы (ЛСПП) остаётся на
    проектной отметке подошвы, как у проекта.
    """

    copy = deepcopy(design)
    by_id = {hole.id: hole for hole in design.holes}
    for hole in copy.holes:
        item = drilled.get(hole.id)
        if item is None:
            continue
        designed = by_id[hole.id]
        subdrill = fact_subdrill_m(designed, item)
        hole.collar = Point3(x=item.actual_collar.x, y=item.actual_collar.y, z=item.actual_collar.z)
        hole.toe = _actual_toe(designed, item)
        if subdrill is not None:
            hole.subdrill_m = subdrill
        if item.actual_diameter > 0:
            hole.diameter_mm = item.actual_diameter
    return copy


def _fact_load(item: AsChargedHole, fallback_product: str) -> HoleLoad:
    """Проектный вид фактического заряда — для расхода ВМ той же функцией, что у проекта.

    Масса записи главнее дек: массы взрывчатых дек приводятся к ней (деки
    скопированы из проекта, а масса — замер); дек нет — одна дека марки записи.
    """

    decks = [Deck.from_dict(deck.to_dict()) for deck in item.decks]
    explosive = [deck for deck in decks if is_explosive_deck_kind(deck.kind)]
    deck_mass = sum(float(deck.mass_kg or 0.0) for deck in explosive)
    mass = float(item.charge_mass_kg or 0.0)
    if explosive and deck_mass > 0 and mass > 0 and abs(deck_mass - mass) > 1e-6:
        for deck in explosive:
            deck.mass_kg = float(deck.mass_kg or 0.0) * mass / deck_mass
    elif explosive and deck_mass <= 0 and mass > 0:
        # Деки без масс: записанная масса делится по длине дек (длин нет — поровну).
        lengths = [abs(float(deck.to_m) - float(deck.from_m)) for deck in explosive]
        total = sum(lengths)
        for deck, length in zip(explosive, lengths):
            deck.mass_kg = mass * (length / total if total > 0 else 1.0 / len(explosive))
    elif not explosive and mass > 0:
        product = item.explosive_product or fallback_product
        decks.append(Deck(kind="charge", from_m=0.0, to_m=0.0, explosive_key=product, mass_kg=mass, product=product))
    return HoleLoad(
        hole_id=item.design_hole_id,
        decks=decks,
        total_charge_kg=mass,
        primers=list(item.primers),
        primer_items=list(item.primer_items),
    )


def _overlay_fired_detonators(design: BlastDesign, enabled: Mapping[str, Hole]) -> None:
    """Скважинные инициаторы по факту взрывания (`as_fired`) — поверх проектной сети копии.

    Записанный детонатор с маркой заменяет проектные назначения скважины
    (детонаторы и скважинные соединители): расход НСИ и электронных — по
    факту. Запись без марки (заготовка без проектного детонатора) сеть не трогает.
    """

    fired = {
        item.design_hole_id: normalize_as_fired(deepcopy(item))
        for item in design.as_fired_holes
        if item.design_hole_id in enabled and str(item.detonator.product or "").strip()
    }
    if not fired:
        return
    network = design.network
    network.detonators = [item for item in network.detonators if item.hole_id not in fired]
    network.downhole_connectors = [item for item in network.downhole_connectors if item.hole_id not in fired]
    for hole_id, item in fired.items():
        detonator = item.detonator
        detonator.hole_id = hole_id
        detonator.deck_index = None
        detonator.primer_index = None
        network.detonators.append(detonator)


def _fact_stemming(item: AsChargedHole) -> float:
    if any(is_explosive_deck_kind(deck.kind) for deck in item.decks):
        return _top_stemming(list(item.decks))
    return float(item.stemming_length_m or 0.0)


def _list(ids: Sequence[str], limit: int = 8) -> str:
    shown = ", ".join(ids[:limit])
    return shown + (f" и ещё {len(ids) - limit}" if len(ids) > limit else "")


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def block_fact(
    design: BlastDesign,
    table: Mapping[str, Any],
    materials: Iterable[Any] | None = None,
    *,
    starter_product: str = "",
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Факт блока: строки таблицы параметров с графами Ф, итоги, расход ВМ и точки Г.1.

    `table` — таблица параметров ревизии проекта (`blocks_v2[i].parameter_table`):
    строки Р берутся из неё как есть (их подписали), первый ряд — её же.
    """

    enabled = sorted((hole for hole in design.holes if hole.enabled), key=lambda hole: _natural(hole.id))
    by_id = {hole.id: hole for hole in enabled}
    drilled = {
        item.design_hole_id: normalize_as_drilled(deepcopy(item))
        for item in design.as_drilled_holes if item.design_hole_id in by_id
    }
    charged = {
        item.design_hole_id: normalize_as_charged(deepcopy(item))
        for item in design.as_charged_holes if item.design_hole_id in by_id
    }
    fact = _fact_geometry(design, drilled)
    fact_enabled = [hole for hole in fact.holes if hole.enabled]
    same_row: dict[int, list[Hole]] = {}
    for hole in fact_enabled:
        same_row.setdefault(hole.row, []).append(hole)
    steps = _row_steps(fact_enabled) if drilled else {}
    burdens = floor_burdens(fact) if drilled else {}
    fact_holes = {hole.id: hole for hole in fact_enabled}

    rows: list[dict[str, Any]] = []
    for project_row in table.get("rows") or ():
        row = dict(project_row)
        hole_id = str(row.get("hole_id"))
        item = drilled.get(hole_id)
        charge = charged.get(hole_id)
        row["drilled"] = item is not None
        row["charged"] = charge is not None
        if item is not None and hole_id in by_id:
            proxy = fact_holes[hole_id]
            spacing = local_spacing(same_row[proxy.row], proxy)
            burden = burdens.get(hole_id) if row.get("first_row") else None
            row["depth_fact_m"] = _r(item.length_m, 1)
            row["subdrill_fact_m"] = _r(fact_subdrill_m(by_id[hole_id], item), 1)
            row["lspp_fact_m"] = None if burden is None else _r(burden.value_m, 2)
            row["spacing_fact_m"] = _r(spacing, 2)
            row["burden_fact_m"] = _r(steps.get(hole_id), 2)
        if charge is not None:
            row["charge_fact_kg"] = round_to_step(charge.charge_mass_kg, FACT_CHARGE_ROUND_KG)
            row["charge_fact_exact_kg"] = round(charge.charge_mass_kg, 3)
            row["stemming_fact_m"] = _r(_fact_stemming(charge), 1)
        rows.append(row)

    issues: list[dict[str, str]] = []
    no_drill = [hole.id for hole in enabled if hole.id not in drilled]
    no_charge = [hole.id for hole in enabled if hole.id not in charged]
    if no_drill:
        issues.append(_issue(
            "fact_drilling_missing",
            f"Нет факта бурения у {len(no_drill)} скв. ({_list(no_drill)}): графы Ф бурения у них пустые, "
            "на Г.1 они — по проекту.",
        ))
    if no_charge:
        issues.append(_issue(
            "fact_charging_missing",
            f"Нет факта заряжания у {len(no_charge)} скв. ({_list(no_charge)}): масса и забойка Ф у них пустые.",
        ))
    # Только скважины таблицы: копии у выключенных скважин в документ не идут.
    copied = sorted(
        {item.design_hole_id for item in design.as_drilled_holes if item.provenance.method == COPY_METHOD}
        | {item.design_hole_id for item in design.as_charged_holes if item.provenance.method == COPY_METHOD},
        key=_natural,
    )
    copied = [hole_id for hole_id in copied if hole_id in by_id]
    if copied:
        issues.append(_issue(
            "fact_copied_from_design",
            f"У {len(copied)} скв. факт записан копией проекта ({_list(copied)}): проверьте, что он подтверждён замером.",
        ))

    fact_loads = [_fact_load(item, design.explosive_key) for item in charged.values()]
    consumption_design = deepcopy(design)
    consumption_design.loads = fact_loads
    _overlay_fired_detonators(consumption_design, by_id)
    consumption = [
        line.to_dict()
        for line in explosives_consumption(consumption_design, materials, starter_product=starter_product)
        if line.kind not in NO_FACT_KINDS
    ]

    holes = []
    rows_by_id = {str(row.get("hole_id")): row for row in rows}
    for hole in enabled:
        proxy = fact_holes[hole.id]
        item = drilled.get(hole.id)
        inclined = math.hypot(proxy.toe.x - proxy.collar.x, proxy.toe.y - proxy.collar.y) > 0.05
        point: dict[str, Any] = {
            "hole_id": hole.id,
            "x": round(proxy.collar.x, 3), "y": round(proxy.collar.y, 3), "z": round(proxy.collar.z, 3),
            "toe": [round(proxy.toe.x, 3), round(proxy.toe.y, 3)] if inclined else None,
            "depth_m": round(item.length_m if item else hole.length_m, 2),
            "charge_kg": rows_by_id.get(hole.id, {}).get("charge_fact_kg"),
            "first_row": bool(rows_by_id.get(hole.id, {}).get("first_row")),
            "diameter_mm": round(proxy.diameter_mm),
            "surveyed": item is not None,
            "offset_m": round(math.hypot(proxy.collar.x - hole.collar.x, proxy.collar.y - hole.collar.y), 2)
            if item is not None else None,
        }
        holes.append(point)

    return (
        {
            "version": FACT_VERSION,
            "execution_sha256": execution_sha256(design),
            "rows": rows,
            "totals": _totals(rows, dict(table.get("totals") or {})),
            "consumption": consumption,
            "holes": holes,
        },
        issues,
    )


def _totals(rows: Sequence[Mapping[str, Any]], project: dict[str, Any]) -> dict[str, Any]:
    """Итоги Р (из ревизии) и Ф: Ф-итог графы — только когда факт этой графы есть у всех скважин."""

    drilled = [row for row in rows if row.get("drilled")]
    charged = [row for row in rows if row.get("charged")]
    all_drilled = bool(rows) and len(drilled) == len(rows)
    all_charged = bool(rows) and len(charged) == len(rows)

    def known(key: str) -> list[float]:
        return [float(row[key]) for row in rows if row.get(key) is not None]

    def mean(key: str, digits: int) -> float | None:
        value = _mean(known(key)) if all_drilled else None
        return None if value is None else round(value, digits)

    stemming = known("stemming_fact_m")
    return {
        **project,
        "drilled_count": len(drilled),
        "charged_count": len(charged),
        "depth_fact_m": round(sum(known("depth_fact_m")), 1) if all_drilled else None,
        "subdrill_fact_mean_m": mean("subdrill_fact_m", 1),
        "spacing_fact_mean_m": mean("spacing_fact_m", 2),
        "burden_fact_mean_m": mean("burden_fact_m", 2),
        "charge_fact_kg": round(sum(known("charge_fact_kg")), 3) if all_charged else None,
        "charge_fact_partial_kg": round(sum(known("charge_fact_exact_kg")), 3),
        "stemming_fact_min_m": min(stemming) if all_charged and stemming else None,
    }


def _issue(code: str, message: str, level: str = "warning") -> dict[str, str]:
    return {"level": level, "code": code, "message": message, "path": "fact"}
