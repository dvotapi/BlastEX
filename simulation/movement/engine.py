"""Run the movement / heave estimate on a blast design.

The designed pattern, charges and initiation network are never rewritten.
Timing is resolved on a copy of the network so ``firing_events`` stay put.
"""
from __future__ import annotations

from typing import Any

from design.editing import local_burden, local_spacing
from design.models import (
    ROLE_PREDICTED,
    BlastDesign,
    Hole,
    HoleLoad,
    InitiationNetwork,
    stemming_length_m,
)
from design.timing import resolve_network
from simulation.movement.kinematics import (
    KINEMATIC_PARAMETERS,
    along_across_extents,
    designed_diameter_m,
    designed_face_distance_m,
    envelope_from_points,
    estimate_hole_movement,
    mean_outward_normal,
)
from simulation.movement.maps import MOVEMENT_MAP_METRICS, movement_maps
from simulation.movement.models import (
    DISCLAIMER,
    IS_PHYSICS_SIMULATION,
    KIND_ESTIMATE,
    LABEL_EN,
    LABEL_RU,
    MODEL_ID,
    MODEL_VERSION,
    MeasuredMuckpileEcho,
    ModelProvenance,
    MovementInputs,
    PredictedMuckpile,
    estimate_kind_payload,
)

DEFAULT_BURDEN_M = 4.0
DEFAULT_SPACING_M = 5.0


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return default
    return parsed


def _designed_guard(design: BlastDesign) -> tuple:
    return (
        [hole.to_dict() for hole in design.holes],
        [load.to_dict() for load in design.loads],
        dict(design.pattern_params or {}),
        dict(design.charge_rules or {}),
        [item.to_dict() for item in design.network.detonators],
        dict(design.network.electronic_times_ms),
        [item.to_dict() for item in design.network.firing_events],
    )


def _assert_design_untouched(design: BlastDesign, before: tuple, action: str) -> None:
    after = _designed_guard(design)
    if after != before:
        raise RuntimeError(f"{action} must not rewrite the designed pattern, charges or network.")


def _pattern_length(design: BlastDesign, key: str, fallback: float) -> float:
    raw = (design.pattern_params or {}).get(key)
    if raw in (None, ""):
        return fallback
    return max(0.0, _finite(raw, fallback))


def _stemming_m(load: HoleLoad | None, design: BlastDesign) -> float:
    if load is not None:
        from_decks = stemming_length_m(load.decks)
        if from_decks > 0:
            return from_decks
    rules = design.charge_rules or {}
    if rules.get("stemming_m") not in (None, ""):
        return max(0.0, _finite(rules.get("stemming_m"), 0.0))
    return 0.0


def _loads_by_id(design: BlastDesign) -> dict[str, HoleLoad]:
    return {load.hole_id: load for load in design.loads}


def _fire_times(design: BlastDesign) -> tuple[dict[str, float], list[str]]:
    """Resolve delays on a network copy so the designed network is not written."""
    network = InitiationNetwork.from_dict(design.network.to_dict())
    result = resolve_network(network, list(design.holes), list(design.loads))
    return dict(result.times_ms), list(result.warnings)


def _hole_inputs(
    hole: Hole,
    design: BlastDesign,
    load: HoleLoad | None,
    times_ms: dict[str, float],
) -> MovementInputs:
    enabled = [item for item in design.holes if item.enabled]
    pattern_burden = _pattern_length(design, "burden_b_m", DEFAULT_BURDEN_M)
    pattern_spacing = _pattern_length(design, "spacing_a_m", DEFAULT_SPACING_M)
    spacing = local_spacing(enabled, hole)
    if spacing is None or spacing <= 0:
        spacing = pattern_spacing
    # Face-to-collar distance is not burden when the first row sits on the face.
    min_row = min((item.row for item in enabled), default=hole.row)
    measured_burden = local_burden(enabled, hole, design.contour)
    if hole.row > min_row and measured_burden and measured_burden > 0:
        burden = measured_burden
    else:
        burden = pattern_burden
    bench = design.contour.bench.height_m
    if bench <= 0:
        bench = max(0.0, hole.length_m - hole.subdrill_m)
    charge_kg = load.total_charge_kg if load is not None else 0.0
    volume = load.influence_volume_m3 if load is not None else 0.0
    if volume <= 0:
        volume = max(0.0, burden * spacing * bench)
    powder = load.specific_q_kg_m3 if load is not None else 0.0
    if powder <= 0 and volume > 0:
        powder = charge_kg / volume
    face_distance = designed_face_distance_m(hole, design.contour)
    return MovementInputs(
        burden_m=float(burden),
        spacing_m=float(spacing),
        bench_height_m=float(bench),
        diameter_mm=float(hole.diameter_mm),
        diameter_m=designed_diameter_m(hole.diameter_mm),
        charge_mass_kg=float(charge_kg),
        powder_factor_kg_m3=float(powder),
        stemming_m=_stemming_m(load, design),
        influence_volume_m3=float(volume),
        face_distance_m=float(face_distance),
        fire_time_ms=times_ms.get(hole.id),
        row=int(hole.row),
    )


def _site_muckpile(
    holes: list[PredictedHoleMovement],
    design: BlastDesign,
) -> PredictedMuckpile:
    if not holes:
        provenance = ModelProvenance(parameters=dict(KINEMATIC_PARAMETERS))
        return PredictedMuckpile(
            length_m=0.0,
            width_m=0.0,
            height_m=0.0,
            volume_m3=0.0,
            throw_m=0.0,
            heave_m=0.0,
            swell_factor=1.0,
            in_situ_volume_m3=0.0,
            centroid_x=0.0,
            centroid_y=0.0,
            provenance=provenance,
        )
    in_situ = sum(item.inputs.influence_volume_m3 for item in holes)
    if in_situ <= 0:
        in_situ = sum(item.inputs.burden_m * item.inputs.spacing_m * item.inputs.bench_height_m for item in holes)
    mean_swell = sum(item.swell_factor for item in holes) / len(holes)
    mean_throw = sum(item.throw_m for item in holes) / len(holes)
    mean_heave = sum(item.heave_m for item in holes) / len(holes)
    mean_bench = sum(item.inputs.bench_height_m for item in holes) / len(holes)
    predicted_pts = [(item.predicted_x, item.predicted_y) for item in holes]
    face = mean_outward_normal(design.contour)
    length_m, width_m = along_across_extents(predicted_pts, face)
    if length_m <= 0:
        length_m = max((item.inputs.spacing_m for item in holes), default=0.0) * max(1, len({item.inputs.row for item in holes}))
    if width_m <= 0:
        width_m = mean_throw + max((item.inputs.burden_m for item in holes), default=0.0)
    volume = in_situ * mean_swell
    height = mean_bench + mean_heave
    if length_m > 0 and width_m > 0:
        height = max(height, volume / (length_m * width_m))
    centroid_x = sum(item.predicted_x for item in holes) / len(holes)
    centroid_y = sum(item.predicted_y for item in holes) / len(holes)
    provenance = ModelProvenance(
        inputs={
            "hole_count": len(holes),
            "in_situ_volume_m3": round(in_situ, 3),
            "mean_powder_factor_kg_m3": round(
                sum(item.inputs.powder_factor_kg_m3 for item in holes) / len(holes), 4
            ),
        },
        parameters=dict(KINEMATIC_PARAMETERS),
    )
    return PredictedMuckpile(
        length_m=round(length_m, 3),
        width_m=round(width_m, 3),
        height_m=round(height, 3),
        volume_m3=round(volume, 3),
        throw_m=round(mean_throw, 3),
        heave_m=round(mean_heave, 3),
        swell_factor=round(mean_swell, 3),
        in_situ_volume_m3=round(in_situ, 3),
        centroid_x=round(centroid_x, 3),
        centroid_y=round(centroid_y, 3),
        envelope=envelope_from_points(predicted_pts),
        provenance=provenance,
    )


def list_models() -> list[dict[str, Any]]:
    payload = {
        "id": MODEL_ID,
        "version": MODEL_VERSION,
        "label": "Кинематическая оценка развала / вывала",
    }
    payload.update(estimate_kind_payload())
    return [payload]


def predict_design(
    design: BlastDesign,
    *,
    measured: list[MeasuredMuckpileEcho] | None = None,
) -> dict[str, Any]:
    """Estimate muckpile movement. Overlay only; designed holes stay put."""
    before = _designed_guard(design)
    times_ms, timing_warnings = _fire_times(design)
    _assert_design_untouched(design, before, "Resolving timing for the movement estimate")
    loads = _loads_by_id(design)
    enabled = [hole for hole in design.holes if hole.enabled]
    hole_rows: list[PredictedHoleMovement] = []
    warnings = list(timing_warnings)
    if not enabled:
        warnings.append("Нет активных скважин — оценка развала пустая.")
    for hole in enabled:
        inputs = _hole_inputs(hole, design, loads.get(hole.id), times_ms)
        if inputs.charge_mass_kg <= 0:
            warnings.append(f"Скважина {hole.id}: нет массы заряда, оценка слабая.")
        hole_rows.append(estimate_hole_movement(hole, inputs, design.contour, enabled, times_ms))
    muckpile = _site_muckpile(hole_rows, design)
    serialized = []
    for item, hole in zip(hole_rows, enabled):
        row = item.to_dict()
        row["hole_kind"] = hole.kind
        serialized.append(row)
    measured_rows = [item.to_dict() for item in (measured or [])]
    payload = {
        "model": MODEL_ID,
        "model_version": MODEL_VERSION,
        "role": ROLE_PREDICTED,
        "prediction_applied": True,
        "design_rewritten": False,
        "muckpile": muckpile.to_dict(),
        "holes": serialized,
        "maps": movement_maps(serialized),
        "warnings": warnings,
        "measured": measured_rows,
        "map_metrics": list(MOVEMENT_MAP_METRICS),
    }
    payload.update(estimate_kind_payload())
    _assert_design_untouched(design, before, "Movement / heave estimate")
    if payload.get("is_physics_simulation"):
        raise RuntimeError("Movement estimate must not claim to be a physics simulation.")
    if payload.get("kind") != KIND_ESTIMATE:
        raise RuntimeError("Movement estimate must keep kind=empirical_kinematic_estimate.")
    text = str(payload.get("disclaimer", "")).lower()
    if LABEL_RU not in text or LABEL_EN not in text:
        raise RuntimeError("Disclaimer must stay labelled оценка / estimate.")
    if IS_PHYSICS_SIMULATION:
        raise RuntimeError("This module is not a physics engine.")
    return payload
