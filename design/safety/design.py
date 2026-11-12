"""Безопасные расстояния по одному проекту блока: `safety_for_design`.

Проект только читается: сеть разрешается на копии (`resolve_network`
записывает моменты в `network.firing_events`). Результат `to_dict()` пойдёт
в контекст документа v2 (PR 2); снимки v1 и `block_from_design` им не
затрагиваются.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from design.models import BlastDesign, Deck, HoleLoad, is_explosive_deck_kind
from design.safety import SAFETY_FORMULA_VERSION, SafetyIssue
from design.safety.airblast import (
    AirblastCharge,
    AirblastGroup,
    AirblastResult,
    airblast_glazing,
    airblast_groups,
    kz_lookup,
)
from design.safety.flyrock import RELIEF_HEIGHT_LIMIT_M, FlyrockResult, flyrock_series
from design.safety.holes import MaterialIndex, SafetyHole, material_index, primer_items, primer_mass_kg, safety_holes
from design.safety.objects import ObjectAssessment, ProtectedObject, assess_objects
from design.safety.params import AIRBLAST_GROUP_MS, SafetyParams
from design.safety.seismic import Charge, DelayGroup, SeismicResult, delay_groups, seismic_safety
from design.safety.zones import Zones, danger_zones
from design.timing import resolve_network

__all__ = ["SafetyResult", "safety_for_design"]


@dataclass(frozen=True)
class SafetyResult:
    params: SafetyParams
    holes: tuple[SafetyHole, ...]
    flyrock: FlyrockResult
    seismic: SeismicResult
    airblast: AirblastResult
    zones: Zones
    objects: tuple[ObjectAssessment, ...] = ()
    issues: tuple[SafetyIssue, ...] = ()
    explosive_kg: float = 0.0
    primer_kg: float = 0.0
    formula_version: str = SAFETY_FORMULA_VERSION
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> list[SafetyIssue]:
        return [issue for issue in self.issues if issue.level == "error"]

    def to_dict(self) -> dict[str, Any]:
        params = self.params
        return {
            "formula_version": self.formula_version,
            "params": {
                "k_ground": params.k_ground,
                "k_structure": params.k_structure,
                "alpha_blast": params.alpha_blast,
                "people_min_m": params.people_min_m,
                "k_mech": params.k_mech,
                "rock_group_ix": params.rock_group_ix,
                "rock_group_v_reduce": params.rock_group_v_reduce,
                "frost": params.frost,
                "buildings_damaged": params.buildings_damaged,
                "relief_height_m": params.relief_height_m,
                "slope_angle_deg": params.slope_angle_deg,
                "delay_group_ms": params.delay_group_ms,
                "hardness_f": params.hardness_f,
                "sources": dict(params.sources),
            },
            "explosive_kg": round(self.explosive_kg, 3),
            "primer_kg": round(self.primer_kg, 3),
            "holes": [hole.to_dict() for hole in self.holes],
            "flyrock": self.flyrock.to_dict(),
            "seismic": self.seismic.to_dict(),
            "airblast": self.airblast.to_dict(),
            "zones": self.zones.to_dict(),
            "objects": [item.to_dict() for item in self.objects],
            "issues": [issue.to_dict() for issue in self.issues],
            **self.meta,
        }


def safety_for_design(
    design: BlastDesign,
    params: SafetyParams,
    *,
    materials: Iterable[Any] | None = None,
    objects: Sequence[ProtectedObject] = (),
) -> SafetyResult:
    """Разлёт, сейсмика, УВВ, опасные зоны и охраняемые объекты по проекту блока."""

    index = material_index(materials)
    issues: list[SafetyIssue] = list(params.issues)
    holes, uncharged, no_mass = safety_holes(design, index)
    if uncharged:
        issues.append(
            SafetyIssue("warning", "holes_not_charged", f"Без заряда {len(uncharged)} скв.: в расчёт безопасных расстояний не вошли.")
        )
    if no_mass:
        issues.append(
            SafetyIssue(
                "warning",
                "primer_mass_unknown",
                f"Масса ПД не задана ни в проекте, ни в справочнике материалов ({len(no_mass)} скв.): в Q сейсмики не вошла.",
            )
        )

    flyrock = flyrock_series(
        holes,
        hardness_f=params.hardness_f,
        relief_height_m=params.relief_height_m,
        slope_angle_deg=params.slope_angle_deg,
    )
    issues.extend(flyrock.issues)

    loads = {load.hole_id: load for load in design.loads}
    times = _deck_times(design)
    untimed = sorted({hole.hole_id for hole in holes if hole.hole_id not in times})
    if untimed:
        issues.append(
            SafetyIssue(
                "warning",
                "delay_groups_unknown",
                f"{len(untimed)} скв. не получают сигнал сети: для сейсмики и УВВ они считаются взорванными "
                "одновременно, одной группой.",
            )
        )

    seismic_charges, untimed_seismic = _seismic_charges(holes, loads, times, index)
    groups = delay_groups(seismic_charges, params.delay_group_ms)
    if untimed_seismic:
        groups.append(DelayGroup(None, None, tuple(untimed_seismic)))
    seismic = seismic_safety(
        groups,
        k_ground=params.k_ground,
        k_structure=params.k_structure,
        alpha=params.alpha_blast,
        buildings_damaged=params.buildings_damaged,
    )

    air_charges, untimed_air, free_column = _airblast_charges(holes, loads, times, params)
    if free_column:
        issues.append(
            SafetyIssue(
                "warning",
                "kz_free_column",
                f"Без забойки {len(free_column)} скв.: K_з взят по свободной от заряда части (п. 803).",
            )
        )
    air_groups = airblast_groups(air_charges, AIRBLAST_GROUP_MS)
    if untimed_air:
        air_groups.append(AirblastGroup(tuple(untimed_air)))
    if design.network.detonating_cords:
        issues.append(
            SafetyIssue(
                "warning",
                "detcord_not_counted",
                "Сеть с детонирующим шнуром: масса ДШ в Q_э (п. 805) в этой версии не учтена.",
            )
        )
    airblast = airblast_glazing(
        air_groups,
        rock_group_ix=params.rock_group_ix,
        rock_group_v_reduce=params.rock_group_v_reduce,
        frost=params.frost,
        interval_unknown=bool(untimed_air),
    )
    issues.extend(airblast.issues)

    # Прил. 21: вниз по склону — не менее 300 м; склон — косогор или превышение
    # блока над границей зоны больше 30 м (оба случая п. 785).
    on_slope = bool(
        (params.slope_angle_deg and params.slope_angle_deg > 0)
        or (params.relief_height_m and params.relief_height_m > RELIEF_HEIGHT_LIMIT_M)
    )
    zones = danger_zones(
        flyrock_m=flyrock.with_relief.value,
        people_min_m=params.people_min_m,
        on_slope=on_slope,
        k_mech=params.k_mech,
        seismic_m=seismic.accepted.value,
        airblast_m=airblast.accepted.value,
        manual=dict(params.manual_zones),
    )
    issues.extend(zones.issues)

    assessed, object_issues = assess_objects(
        objects,
        people_m=zones.people.value or 0.0,
        mechanisms_m=zones.mechanisms.value or 0.0,
        seismic_m=seismic.accepted.value or 0.0,
        airblast_m=airblast.accepted.value or 0.0,
        buildings_m=zones.buildings.value,
    )
    issues.extend(object_issues)
    return SafetyResult(
        params=params,
        holes=tuple(holes),
        flyrock=flyrock,
        seismic=seismic,
        airblast=airblast,
        zones=zones,
        objects=tuple(assessed),
        issues=tuple(issues),
        explosive_kg=sum(hole.charge_kg for hole in holes),
        primer_kg=sum(hole.primer_kg for hole in holes),
    )


def _deck_times(design: BlastDesign) -> dict[str, dict[int, float]]:
    """Моменты срабатывания взрывчатых дек по скважинам; сеть — на копии."""

    network = copy.deepcopy(design.network)
    enabled = [hole for hole in design.holes if hole.enabled]
    timing = resolve_network(network, enabled, design.loads)
    times: dict[str, dict[int, float]] = {}
    for event in timing.events:
        if event.level == "deck" and event.deck_index is not None:
            times.setdefault(event.hole_id, {})[event.deck_index] = float(event.time_ms)
    # Скважина с моментом, но без событий дек (заряд не по декам) — момент скважины.
    for hole_id, time_ms in timing.times_ms.items():
        times.setdefault(hole_id, {-1: float(time_ms)})
    return times


def _explosive_decks(load: HoleLoad | None) -> list[tuple[int, Deck]]:
    if load is None:
        return []
    return [(index, deck) for index, deck in enumerate(load.decks) if is_explosive_deck_kind(deck.kind) and deck.mass_kg > 0]


def _deck_time(times: dict[int, float], index: int) -> float:
    return times.get(index, times.get(-1, min(times.values())))


def _seismic_charges(
    holes: Sequence[SafetyHole],
    loads: dict[str, HoleLoad],
    times: dict[str, dict[int, float]],
    materials: MaterialIndex,
) -> tuple[list[Charge], list[Charge]]:
    """Заряды для сейсмики: деки с массой, ПД — к деке, в которой стоят (решение В4: Q = ВВ + ПД)."""

    timed: list[Charge] = []
    untimed: list[Charge] = []
    for hole in holes:
        load = loads.get(hole.hole_id)
        decks = _explosive_decks(load)
        masses = {index: float(deck.mass_kg) for index, deck in decks}
        for primer in primer_items(load):
            mass = primer_mass_kg(primer, materials)
            if mass is None or not decks:
                continue
            index = _primer_deck(decks, primer.position_m)
            masses[index] += mass
        hole_times = times.get(hole.hole_id)
        for index, mass in masses.items():
            if hole_times is None:
                untimed.append(Charge(hole.hole_id, 0.0, mass))
            else:
                timed.append(Charge(hole.hole_id, _deck_time(hole_times, index), mass))
    return timed, untimed


def _primer_deck(decks: list[tuple[int, Deck]], position_m: float) -> int:
    for index, deck in decks:
        if min(deck.from_m, deck.to_m) - 1e-6 <= position_m <= max(deck.from_m, deck.to_m) + 1e-6:
            return index
    return min(decks, key=lambda item: min(abs(position_m - item[1].from_m), abs(position_m - item[1].to_m)))[0]


def _airblast_charges(
    holes: Sequence[SafetyHole],
    loads: dict[str, HoleLoad],
    times: dict[str, dict[int, float]],
    params: SafetyParams,
) -> tuple[list[AirblastCharge], list[AirblastCharge], list[str]]:
    timed: list[AirblastCharge] = []
    untimed: list[AirblastCharge] = []
    free_column: list[str] = []
    for hole in holes:
        by_free = hole.stemming_m <= 0
        if by_free:
            kz = kz_lookup(hole.free_length_m / hole.diameter_m, params.kz_by_free)
            free_column.append(hole.hole_id)
        else:
            kz = kz_lookup(hole.stemming_m / hole.diameter_m, params.kz_by_stemming)
        hole_times = times.get(hole.hole_id)
        for index, deck in _explosive_decks(loads.get(hole.hole_id)):
            length = abs(deck.to_m - deck.from_m)
            if length <= 0:
                continue
            charge = AirblastCharge(
                hole_id=hole.hole_id,
                time_ms=_deck_time(hole_times, index) if hole_times else 0.0,
                capacity_kg_m=deck.mass_kg / length,
                charge_length_m=length,
                diameter_m=hole.diameter_m,
                kz=kz,
                kz_by_free=by_free,
            )
            (timed if hole_times else untimed).append(charge)
    return timed, untimed, free_column

