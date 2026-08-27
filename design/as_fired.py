"""As-fired execution records (phase BDX-009).

Designed timing stays on ``BlastDesign.network``. Executed detonator,
programmed time, verified time and firing timestamp live only on
``BlastDesign.as_fired_holes``. Recording or comparing never mutates
``Hole``, ``HoleLoad`` or the initiation network.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from design.models import (
    ROLE_EXECUTED,
    AsFiredHole,
    BlastDesign,
    DataProvenance,
    Detonator,
    Hole,
    InitiationNetwork,
)

MISSING_TIME_WARNING = "Нет проектного времени инициирования для скважины"


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
        [item.to_dict() for item in design.network.electronic_channels],
    )


def _assert_design_untouched(design: BlastDesign, before: tuple, action: str) -> None:
    after = _designed_guard(design)
    if after != before:
        raise RuntimeError(f"{action} не должна менять проектные скважины, заряд или сеть.")


def normalize_as_fired(item: AsFiredHole) -> AsFiredHole:
    """Force executed role and keep detonator linked to the designed hole."""
    detonator = Detonator.from_dict(item.detonator.to_dict())
    if not detonator.hole_id:
        detonator.hole_id = item.design_hole_id
    provenance = item.provenance
    provenance.role = ROLE_EXECUTED
    return AsFiredHole(
        design_hole_id=item.design_hole_id,
        detonator=detonator,
        programmed_time_ms=float(item.programmed_time_ms or 0.0),
        verified_time_ms=item.verified_time_ms,
        firing_timestamp=str(item.firing_timestamp or ""),
        role=ROLE_EXECUTED,
        provenance=provenance,
    )


def designed_hole_times(design: BlastDesign) -> dict[str, float]:
    """Resolve designed times on a copy of the network so the original stays intact."""
    from design.timing import resolve_network

    network = deepcopy(design.network)
    result = resolve_network(network, list(design.holes), list(design.loads))
    return result.times_ms


def designed_detonator(network: InitiationNetwork, hole_id: str) -> Detonator | None:
    hole_level = [
        item
        for item in network.detonators
        if item.hole_id == hole_id and item.deck_index is None and item.primer_index is None
    ]
    if hole_level:
        return hole_level[0]
    any_level = [item for item in network.detonators if item.hole_id == hole_id]
    return any_level[0] if any_level else None


def as_fired_from_design_hole(
    design: BlastDesign,
    hole: Hole,
    *,
    source: str = "copied_from_design",
) -> AsFiredHole:
    """Build an executed stub from the designed network. The network is not changed."""
    times = designed_hole_times(design)
    detonator = designed_detonator(design.network, hole.id)
    if detonator is None:
        detonator = Detonator(id=f"det-{hole.id}", hole_id=hole.id)
    else:
        detonator = Detonator.from_dict(detonator.to_dict())
    return normalize_as_fired(
        AsFiredHole(
            design_hole_id=hole.id,
            detonator=detonator,
            programmed_time_ms=float(times.get(hole.id, 0.0)),
            provenance=DataProvenance(source=source, method="copy", role=ROLE_EXECUTED),
        )
    )


def record_as_fired(design: BlastDesign, item: AsFiredHole) -> AsFiredHole:
    """Upsert one executed fire. Designed network fields stay untouched."""
    designed = next((hole for hole in design.holes if hole.id == item.design_hole_id), None)
    if designed is None:
        raise ValueError(f"Проектная скважина «{item.design_hole_id}» не найдена.")
    before = _designed_guard(design)
    recorded = normalize_as_fired(item)
    if not recorded.design_hole_id:
        raise ValueError("У фактического взрыва нет связи с проектом (design_hole_id).")
    if not recorded.firing_timestamp:
        recorded.firing_timestamp = _utc_now_iso()
    if not recorded.provenance.timestamp:
        recorded.provenance.timestamp = recorded.firing_timestamp
    for index, existing in enumerate(design.as_fired_holes):
        if existing.design_hole_id == recorded.design_hole_id:
            if not recorded.detonator.id and not recorded.detonator.product:
                recorded.detonator = existing.detonator
            if recorded.verified_time_ms is None:
                recorded.verified_time_ms = existing.verified_time_ms
            design.as_fired_holes[index] = recorded
            _assert_design_untouched(design, before, "Запись факта взрыва")
            return recorded
    design.as_fired_holes.append(recorded)
    _assert_design_untouched(design, before, "Запись факта взрыва")
    return recorded


def record_as_fired_many(
    design: BlastDesign,
    items: list[AsFiredHole],
    *,
    replace: bool = False,
) -> list[AsFiredHole]:
    before = _designed_guard(design)
    if replace:
        design.as_fired_holes = []
    recorded: list[AsFiredHole] = []
    for item in items:
        recorded.append(record_as_fired(design, item))
    _assert_design_untouched(design, before, "Пакетная запись факта взрыва")
    return recorded


def _delta(actual: float | None, designed: float | None) -> float | None:
    if actual is None or designed is None:
        return None
    return round(float(actual) - float(designed), 3)


def compare_hole(
    designed_hole: Hole,
    executed: AsFiredHole,
    designed_time_ms: float | None,
    designed_det: Detonator | None,
) -> dict[str, Any]:
    actual = normalize_as_fired(executed)
    designed_product = designed_det.product if designed_det else ""
    designed_kind = designed_det.kind if designed_det else ""
    designed_det_id = designed_det.id if designed_det else ""
    verified = actual.verified_time_ms
    return {
        "design_hole_id": designed_hole.id,
        "role": ROLE_EXECUTED,
        "comparison": "design_vs_fired",
        "designed_time_ms": _round_opt(designed_time_ms),
        "programmed_time_ms": round(actual.programmed_time_ms, 3),
        "verified_time_ms": _round_opt(verified),
        "programmed_time_delta_ms": _delta(actual.programmed_time_ms, designed_time_ms),
        "verified_time_delta_ms": _delta(verified, designed_time_ms),
        "timing_error_ms": _delta(verified, actual.programmed_time_ms),
        "designed_detonator_id": designed_det_id,
        "actual_detonator_id": actual.detonator.id,
        "designed_detonator_product": designed_product,
        "actual_detonator_product": actual.detonator.product,
        "designed_detonator_kind": designed_kind,
        "actual_detonator_kind": actual.detonator.kind,
        "detonator_product_mismatch": bool(designed_product or actual.detonator.product)
        and designed_product != actual.detonator.product,
        "detonator_kind_mismatch": bool(designed_kind or actual.detonator.kind)
        and designed_kind != actual.detonator.kind,
        "firing_timestamp": actual.firing_timestamp,
    }


def compare_design(design: BlastDesign) -> dict[str, Any]:
    """Compare executed firing with the designed network. Designed data is read-only."""
    before = _designed_guard(design)
    designed_holes = {hole.id: hole for hole in design.holes}
    designed_set = [hole for hole in design.holes if hole.enabled]
    times = designed_hole_times(design)
    deviations: list[dict[str, Any]] = []
    warnings: list[str] = []

    for item in design.as_fired_holes:
        hole = designed_holes.get(item.design_hole_id)
        if hole is None:
            warnings.append(f"Фактический взрыв ссылается на отсутствующий проект «{item.design_hole_id}».")
            continue
        designed_time = times.get(hole.id)
        if designed_time is None:
            warnings.append(f"{MISSING_TIME_WARNING} «{hole.id}».")
        deviations.append(
            compare_hole(
                hole,
                item,
                designed_time,
                designed_detonator(design.network, hole.id),
            )
        )

    missing = [
        hole.id
        for hole in designed_set
        if hole.id not in {item.design_hole_id for item in design.as_fired_holes}
    ]
    if missing:
        preview = ", ".join(missing[:8])
        extra = f" и ещё {len(missing) - 8}" if len(missing) > 8 else ""
        warnings.append(f"Нет факта взрыва для скважин: {preview}{extra}.")

    _assert_design_untouched(design, before, "Сравнение факта взрыва с проектом")
    return {
        "role": ROLE_EXECUTED,
        "comparison": "design_vs_fired",
        "compared_count": len(deviations),
        "designed_count": len(designed_set),
        "as_fired_count": len(design.as_fired_holes),
        "deviations": deviations,
        "warnings": warnings,
        "as_fired_holes": [item.to_dict() for item in design.as_fired_holes],
    }
