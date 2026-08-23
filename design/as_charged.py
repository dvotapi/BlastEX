"""As-charged execution records (phase BDX-009).

Designed charging stays on ``BlastDesign.loads``. Executed decks, mass,
stemming and primers live only on ``BlastDesign.as_charged_holes``.
Recording or comparing never mutates ``Hole``, ``HoleLoad`` or the network.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from design.models import (
    ROLE_EXECUTED,
    AsChargedHole,
    AsDrilledHole,
    BlastDesign,
    DataProvenance,
    Deck,
    Hole,
    HoleLoad,
    Primer,
    charge_column_bounds_m,
    explosive_charge_mass_kg,
    primary_explosive_product,
    primer_position_m,
    stemming_length_m,
)

MISSING_LOAD_WARNING = "Нет проектного заряда для скважины"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _round_opt(value: float | None, places: int = 3) -> float | None:
    if value is None:
        return None
    return round(float(value), places)


def _designed_guard(design: BlastDesign) -> tuple:
    return (
        [hole.to_dict() for hole in design.holes],
        [load.to_dict() for load in design.loads],
        [item.to_dict() for item in design.network.detonators],
        dict(design.network.electronic_times_ms),
        [item.to_dict() for item in design.network.firing_events],
    )


def _assert_design_untouched(design: BlastDesign, before: tuple, action: str) -> None:
    after = _designed_guard(design)
    if after != before:
        raise RuntimeError(f"{action} не должна менять проектные скважины, заряд или сеть.")


def normalize_as_charged(item: AsChargedHole) -> AsChargedHole:
    """Fill derived executed charging. Role is forced to executed."""
    decks = [Deck.from_dict(deck.to_dict()) for deck in item.decks]
    items = list(item.primer_items)
    if not items and item.primers:
        items = [Primer(position_m=depth) for depth in item.primers]
    depths = list(item.primers) if item.primers else [primer.position_m for primer in items]
    mass = float(item.charge_mass_kg or 0.0)
    if mass <= 0:
        mass = explosive_charge_mass_kg(decks)
    stemming = float(item.stemming_length_m or 0.0)
    if stemming <= 0:
        stemming = stemming_length_m(decks)
    product = str(item.explosive_product or "").strip()
    if not product:
        product = primary_explosive_product(decks)
    provenance = item.provenance
    provenance.role = ROLE_EXECUTED
    return AsChargedHole(
        design_hole_id=item.design_hole_id,
        decks=decks,
        primers=depths,
        primer_items=items,
        explosive_product=product,
        charge_mass_kg=mass,
        stemming_length_m=stemming,
        loading_timestamp=str(item.loading_timestamp or ""),
        role=ROLE_EXECUTED,
        provenance=provenance,
    )


def as_charged_from_design_load(
    load: HoleLoad,
    *,
    source: str = "copied_from_design",
    explosive_key: str = "",
) -> AsChargedHole:
    """Build an executed stub from the designed load. The designed HoleLoad is not changed."""
    return normalize_as_charged(
        AsChargedHole(
            design_hole_id=load.hole_id,
            decks=[Deck.from_dict(deck.to_dict()) for deck in load.decks],
            primers=list(load.primers),
            primer_items=[Primer.from_dict(item.to_dict()) for item in load.primer_items],
            explosive_product=primary_explosive_product(load.decks, explosive_key),
            charge_mass_kg=float(load.total_charge_kg or 0.0),
            stemming_length_m=stemming_length_m(load.decks),
            provenance=DataProvenance(source=source, method="copy", role=ROLE_EXECUTED),
        )
    )


def record_as_charged(design: BlastDesign, item: AsChargedHole) -> AsChargedHole:
    """Upsert one executed charge. Designed ``Hole`` / ``HoleLoad`` stay untouched."""
    designed = next((hole for hole in design.holes if hole.id == item.design_hole_id), None)
    if designed is None:
        raise ValueError(f"Проектная скважина «{item.design_hole_id}» не найдена.")
    before = _designed_guard(design)
    recorded = normalize_as_charged(item)
    if not recorded.design_hole_id:
        raise ValueError("У фактического заряда нет связи с проектом (design_hole_id).")
    if not recorded.loading_timestamp:
        recorded.loading_timestamp = _utc_now_iso()
    if not recorded.provenance.timestamp:
        recorded.provenance.timestamp = recorded.loading_timestamp
    for index, existing in enumerate(design.as_charged_holes):
        if existing.design_hole_id == recorded.design_hole_id:
            if not recorded.decks:
                recorded.decks = existing.decks
                recorded.charge_mass_kg = recorded.charge_mass_kg or existing.charge_mass_kg
                recorded.stemming_length_m = recorded.stemming_length_m or existing.stemming_length_m
                recorded.explosive_product = recorded.explosive_product or existing.explosive_product
            if not recorded.primer_items and not recorded.primers:
                recorded.primer_items = existing.primer_items
                recorded.primers = existing.primers
            if not recorded.loading_timestamp:
                recorded.loading_timestamp = existing.loading_timestamp
            design.as_charged_holes[index] = recorded
            _assert_design_untouched(design, before, "Запись факта заряжания")
            return recorded
    design.as_charged_holes.append(recorded)
    _assert_design_untouched(design, before, "Запись факта заряжания")
    return recorded


def record_as_charged_many(
    design: BlastDesign,
    items: list[AsChargedHole],
    *,
    replace: bool = False,
) -> list[AsChargedHole]:
    before = _designed_guard(design)
    if replace:
        design.as_charged_holes = []
    recorded: list[AsChargedHole] = []
    for item in items:
        recorded.append(record_as_charged(design, item))
    _assert_design_untouched(design, before, "Пакетная запись факта заряжания")
    return recorded


def _designed_mass(load: HoleLoad | None) -> float:
    if load is None:
        return 0.0
    return float(load.total_charge_kg or explosive_charge_mass_kg(load.decks) or 0.0)


def _delta(actual: float | None, designed: float | None) -> float | None:
    if actual is None or designed is None:
        return None
    return round(float(actual) - float(designed), 3)


def compare_hole(
    designed_hole: Hole,
    designed_load: HoleLoad | None,
    executed: AsChargedHole,
    drilled: AsDrilledHole | None,
    *,
    design_explosive_key: str = "",
) -> dict[str, Any]:
    actual = normalize_as_charged(executed)
    designed_decks = designed_load.decks if designed_load else []
    designed_primers = designed_load.primer_items if designed_load else []
    designed_primer_depths = designed_load.primers if designed_load else []
    designed_product = primary_explosive_product(designed_decks, design_explosive_key)
    designed_stemming = stemming_length_m(designed_decks)
    designed_primer = primer_position_m(designed_primers, designed_primer_depths)
    actual_primer = primer_position_m(actual.primer_items, actual.primers)
    designed_from, designed_to = charge_column_bounds_m(designed_decks)
    actual_from, actual_to = charge_column_bounds_m(actual.decks)
    actual_depth = drilled.length_m if drilled is not None else designed_hole.length_m
    leftover = None
    overcharge = None
    if actual_to is not None:
        leftover = max(0.0, actual_depth - actual_to)
        overcharge = max(0.0, actual_to - actual_depth)
    return {
        "design_hole_id": designed_hole.id,
        "role": ROLE_EXECUTED,
        "comparison": "design_vs_charged",
        "designed_product": designed_product,
        "actual_product": actual.explosive_product,
        "product_mismatch": bool(designed_product or actual.explosive_product)
        and designed_product != actual.explosive_product,
        "designed_charge_kg": round(_designed_mass(designed_load), 3),
        "actual_charge_kg": round(actual.charge_mass_kg, 3),
        "charge_mass_delta_kg": round(actual.charge_mass_kg - _designed_mass(designed_load), 3),
        "designed_stemming_m": round(designed_stemming, 3),
        "actual_stemming_m": round(actual.stemming_length_m, 3),
        "stemming_delta_m": round(actual.stemming_length_m - designed_stemming, 3),
        "designed_primer_m": _round_opt(designed_primer),
        "actual_primer_m": _round_opt(actual_primer),
        "primer_position_delta_m": _delta(actual_primer, designed_primer),
        "designed_deck_from_m": _round_opt(designed_from),
        "designed_deck_to_m": _round_opt(designed_to),
        "actual_deck_from_m": _round_opt(actual_from),
        "actual_deck_to_m": _round_opt(actual_to),
        "deck_from_delta_m": _delta(actual_from, designed_from),
        "deck_to_delta_m": _delta(actual_to, designed_to),
        "actual_hole_depth_m": round(actual_depth, 3),
        "depth_basis": "drilled" if drilled is not None else "designed",
        "leftover_unloaded_m": _round_opt(leftover),
        "overcharge_m": _round_opt(overcharge),
        "loading_timestamp": actual.loading_timestamp,
        "deck_count": len(actual.decks),
        "designed_deck_count": len(designed_decks),
    }


def compare_design(design: BlastDesign) -> dict[str, Any]:
    """Compare executed charging with designed loads. Designed data is read-only."""
    before = _designed_guard(design)
    designed_holes = {hole.id: hole for hole in design.holes}
    designed_loads = {load.hole_id: load for load in design.loads}
    drilled = {item.design_hole_id: item for item in design.as_drilled_holes}
    deviations: list[dict[str, Any]] = []
    warnings: list[str] = []
    designed_set = [hole for hole in design.holes if hole.enabled]

    for item in design.as_charged_holes:
        hole = designed_holes.get(item.design_hole_id)
        if hole is None:
            warnings.append(f"Фактический заряд ссылается на отсутствующий проект «{item.design_hole_id}».")
            continue
        load = designed_loads.get(hole.id)
        if load is None:
            warnings.append(f"{MISSING_LOAD_WARNING} «{hole.id}» — сравниваем с пустым проектом.")
        deviations.append(
            compare_hole(
                hole,
                load,
                item,
                drilled.get(hole.id),
                design_explosive_key=design.explosive_key,
            )
        )

    missing = [
        hole.id
        for hole in designed_set
        if hole.id not in {item.design_hole_id for item in design.as_charged_holes}
    ]
    if missing:
        preview = ", ".join(missing[:8])
        extra = f" и ещё {len(missing) - 8}" if len(missing) > 8 else ""
        warnings.append(f"Нет факта заряжания для скважин: {preview}{extra}.")

    _assert_design_untouched(design, before, "Сравнение факта заряжания с проектом")
    return {
        "role": ROLE_EXECUTED,
        "comparison": "design_vs_charged",
        "compared_count": len(deviations),
        "designed_count": len(designed_set),
        "as_charged_count": len(design.as_charged_holes),
        "deviations": deviations,
        "warnings": warnings,
        "as_charged_holes": [item.to_dict() for item in design.as_charged_holes],
    }
