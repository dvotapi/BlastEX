"""Заряжание скважин: забойка, деки заряда/промежутков, боевики.

Масса заряда считается через `cost.geometry.charge_diameter_m` и
`linear_capacity_kg_per_m` — теми же функциями, что и смета (`cost/geometry.py`),
поэтому масса заряда скважины в проекте и в смете совпадает до килограмма.
"""
from __future__ import annotations

from typing import Any

from Blast import ExplosiveProperties
from cost.geometry import charge_diameter_m, linear_capacity_kg_per_m
from design.geology import designed_rock_intervals, properties_at
from design.models import Deck, Hole, HoleInterval, HoleLoad, RockPropertySet

DECKING_TYPES = ("continuous", "spaced")


def hole_geology_for_charging(hole: Hole) -> list[HoleInterval]:
    """Designed rock intervals available to a future charging-rules engine (BDX-004).

    This phase only exposes the data. Measured intervals are intentionally excluded.
    """
    return designed_rock_intervals(hole)


def rock_properties_for_charging(hole: Hole, along_m: float) -> RockPropertySet | None:
    """Designed properties at a depth along the hole. BDX-004 will consume this."""
    return properties_at(hole, along_m)


def apply_charge_rules(
    holes: list[Hole],
    rules: dict[str, Any],
    explosive: ExplosiveProperties,
) -> list[HoleLoad]:
    """Строит заряжание для каждой скважины по единым правилам.

    rules:
      hole_oversize_coeff  коэффициент разбуривания (диаметр заряда = диаметр коронки × коэфф.)
      stemming_m            длина забойки, м (если не задана — берётся stemming_k × диаметр скважины)
      stemming_k             длина забойки в диаметрах скважины (по умолчанию 20)
      decking                "continuous" | "spaced"
      deck_count             число зарядов при "spaced" (>=2)
      air_gap_m              длина воздушного промежутка между зарядами при "spaced", м
      primer_offset_m        отступ боевика от нижнего торца деки заряда, м
      grid_a_m, grid_b_m     сетка для объёма влияния скважины (a×b×эффективная высота уступа)
    """
    hole_oversize_coeff = float(rules.get("hole_oversize_coeff", 1.05))
    stemming_m_fixed = rules.get("stemming_m")
    stemming_k = float(rules.get("stemming_k", 20.0))
    decking = str(rules.get("decking", "continuous"))
    if decking not in DECKING_TYPES:
        decking = "continuous"
    deck_count = max(1, int(rules.get("deck_count", 1)))
    air_gap_m = max(0.0, float(rules.get("air_gap_m", 1.0)))
    primer_offset_m = max(0.0, float(rules.get("primer_offset_m", 0.3)))
    grid_a_m = float(rules.get("grid_a_m", 0.0))
    grid_b_m = float(rules.get("grid_b_m", 0.0))

    loads: list[HoleLoad] = []
    for hole in holes:
        loads.append(
            _charge_hole(
                hole,
                explosive=explosive,
                hole_oversize_coeff=hole_oversize_coeff,
                stemming_m_fixed=stemming_m_fixed,
                stemming_k=stemming_k,
                decking=decking,
                deck_count=deck_count,
                air_gap_m=air_gap_m,
                primer_offset_m=primer_offset_m,
                grid_a_m=grid_a_m,
                grid_b_m=grid_b_m,
            )
        )
    return loads


def _charge_hole(
    hole: Hole,
    *,
    explosive: ExplosiveProperties,
    hole_oversize_coeff: float,
    stemming_m_fixed: float | None,
    stemming_k: float,
    decking: str,
    deck_count: int,
    air_gap_m: float,
    primer_offset_m: float,
    grid_a_m: float,
    grid_b_m: float,
) -> HoleLoad:
    length_m = hole.length_m
    diameter_m = hole.diameter_mm / 1000.0

    stemming_m = float(stemming_m_fixed) if stemming_m_fixed is not None else stemming_k * diameter_m
    stemming_m = max(0.0, min(stemming_m, length_m))
    charge_length_total = length_m - stemming_m

    charge_diameter = charge_diameter_m(hole.diameter_mm, hole_oversize_coeff)
    capacity = linear_capacity_kg_per_m(charge_diameter, explosive.density_t_m3)

    decks: list[Deck] = []
    if stemming_m > 0:
        decks.append(Deck(kind="stemming", from_m=0.0, to_m=stemming_m))

    charge_spans = _charge_spans(charge_length_total, stemming_m, decking, deck_count, air_gap_m)
    primers: list[float] = []
    for from_m, to_m in charge_spans:
        mass_kg = (to_m - from_m) * capacity
        decks.append(Deck(kind="charge", from_m=from_m, to_m=to_m, explosive_key=explosive.name, mass_kg=mass_kg))
        primers.append(max(from_m, to_m - primer_offset_m))

    # Воздушные промежутки между зарядами при рассредоточенном заряде.
    for (_, prev_to), (next_from, _) in zip(charge_spans, charge_spans[1:]):
        if next_from > prev_to:
            decks.append(Deck(kind="air", from_m=prev_to, to_m=next_from))

    decks.sort(key=lambda d: d.from_m)

    total_charge_kg = sum(d.mass_kg for d in decks if d.kind == "charge")
    influence_volume_m3 = grid_a_m * grid_b_m * hole.bench_height_m
    specific_q = total_charge_kg / influence_volume_m3 if influence_volume_m3 > 0 else 0.0

    return HoleLoad(
        hole_id=hole.id,
        decks=decks,
        total_charge_kg=total_charge_kg,
        influence_volume_m3=influence_volume_m3,
        specific_q_kg_m3=specific_q,
        primers=primers,
    )


def _charge_spans(
    charge_length_total: float,
    stemming_m: float,
    decking: str,
    deck_count: int,
    air_gap_m: float,
) -> list[tuple[float, float]]:
    """Границы дек заряда (от_м, до_м от устья), без учёта забойки в списке."""
    if charge_length_total <= 0:
        return []

    if decking != "spaced" or deck_count < 2:
        return [(stemming_m, stemming_m + charge_length_total)]

    total_air = air_gap_m * (deck_count - 1)
    charge_portion = charge_length_total - total_air
    if charge_portion <= 0:
        # Промежутки не помещаются — заряд остаётся сплошным.
        return [(stemming_m, stemming_m + charge_length_total)]

    each_deck_len = charge_portion / deck_count
    spans: list[tuple[float, float]] = []
    cursor = stemming_m
    for i in range(deck_count):
        deck_from = cursor
        deck_to = deck_from + each_deck_len
        spans.append((deck_from, deck_to))
        cursor = deck_to + (air_gap_m if i < deck_count - 1 else 0.0)
    return spans
