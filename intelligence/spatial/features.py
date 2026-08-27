"""Per-hole and neighborhood features for spatial ML (BDX-022).

Designed geometry / charging stay ROLE_DESIGNED. As-charged / as-drilled
values are copied as ROLE_EXECUTED context and never become the designed
layer. Extraction never writes back onto the live design.
"""
from __future__ import annotations

import math
from typing import Any

from design.editing import local_burden, local_spacing
from design.models import (
    ROLE_DESIGNED,
    ROLE_EXECUTED,
    BlastDesign,
    Hole,
    HoleLoad,
    explosive_charge_mass_kg,
    stemming_length_m,
)
from intelligence.spatial.types import (
    DEFAULT_NEIGHBOR_K,
    FEATURE_SCHEMA_VERSION,
    HOLE_FEATURE_NAMES,
    METRIC_OVERSIZE,
    METRIC_TOE,
    METRIC_X50,
    ROLE_PREDICTED,
    HoleObservation,
)

KIND_CODES = {
    "production": 0.0,
    "buffer": 1.0,
    "trim": 2.0,
    "presplit": 3.0,
    "contour": 4.0,
    "stab": 5.0,
    "satellite": 6.0,
    "infill": 7.0,
}


def _round(value: float | None, places: int = 6) -> float | None:
    if value is None:
        return None
    return round(float(value), places)


def _finite(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _mean(values: list[float | None]) -> float | None:
    nums = [float(item) for item in values if item is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def _distance2(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


def _enabled_holes(design: BlastDesign) -> list[Hole]:
    return [hole for hole in design.holes if hole.enabled]


def _loads_by_id(design: BlastDesign) -> dict[str, HoleLoad]:
    return {load.hole_id: load for load in design.loads}


def _designed_delay_ms(design: BlastDesign, hole_id: str) -> float | None:
    times = dict(design.network.electronic_times_ms)
    if hole_id in times:
        return _finite(times[hole_id])
    for detonator in design.network.detonators:
        if detonator.hole_id == hole_id:
            return _finite(detonator.delay_ms)
    return None


def _hole_rock(hole: Hole, design: BlastDesign) -> tuple[float | None, float | None]:
    densities: list[float | None] = []
    ucs: list[float | None] = []
    for interval in hole.intervals:
        densities.append(_finite(interval.properties.density_kg_m3))
        ucs.append(_finite(interval.properties.ucs_mpa))
    if densities or ucs:
        return _mean(densities), _mean(ucs)
    if design.domains:
        props = design.domains[0].properties
        return _finite(props.density_kg_m3), _finite(props.ucs_mpa)
    return None, None


def _designed_charge(load: HoleLoad | None) -> tuple[float | None, float | None, float | None]:
    if load is None:
        return None, None, None
    charge = _finite(load.total_charge_kg)
    if charge is None or charge <= 0:
        charge = _finite(explosive_charge_mass_kg(load.decks))
    stemming = _finite(stemming_length_m(load.decks))
    powder = _finite(load.specific_q_kg_m3)
    return charge, stemming, powder


def nearest_neighbor_ids(
    observations: list[HoleObservation],
    hole_id: str,
    *,
    k: int = DEFAULT_NEIGHBOR_K,
) -> list[str]:
    current = next((item for item in observations if item.hole_id == hole_id), None)
    if current is None:
        return []
    ranked = sorted(
        (item for item in observations if item.hole_id != hole_id),
        key=lambda item: _distance2(current.x, current.y, item.x, item.y),
    )
    return [item.hole_id for item in ranked[: max(0, int(k))]]


def attach_neighborhoods(
    observations: list[HoleObservation],
    *,
    k: int = DEFAULT_NEIGHBOR_K,
) -> list[HoleObservation]:
    """Fill neighbor ids and neighborhood-mean features. Mean residual stays 0-centered."""
    by_id = {item.hole_id: item for item in observations}
    for item in observations:
        item.neighbor_ids = nearest_neighbor_ids(observations, item.hole_id, k=k)
        members = [item] + [by_id[hid] for hid in item.neighbor_ids if hid in by_id]
        item.features["nb_mean_charge_kg"] = _mean([row.features.get("charge_kg") for row in members]) or 0.0
        item.features["nb_mean_burden_m"] = _mean([row.features.get("burden_m") for row in members]) or 0.0
        item.features["nb_mean_powder_factor_kg_m3"] = (
            _mean([row.features.get("powder_factor_kg_m3") for row in members]) or 0.0
        )
    return observations


def add_relative_features(observations: list[HoleObservation]) -> list[HoleObservation]:
    """Hole minus blast-block mean. Units stay those of the named field."""
    charge_mean = _mean([item.features.get("charge_kg") for item in observations])
    burden_mean = _mean([item.features.get("burden_m") for item in observations])
    powder_mean = _mean([item.features.get("powder_factor_kg_m3") for item in observations])
    ucs_mean = _mean([item.features.get("ucs_mpa") for item in observations])
    for item in observations:
        charge = item.features.get("charge_kg")
        burden = item.features.get("burden_m")
        powder = item.features.get("powder_factor_kg_m3")
        ucs = item.features.get("ucs_mpa")
        item.features["rel_charge_kg"] = (float(charge) - float(charge_mean)) if charge is not None and charge_mean is not None else 0.0
        item.features["rel_burden_m"] = (float(burden) - float(burden_mean)) if burden is not None and burden_mean is not None else 0.0
        item.features["rel_powder_factor_kg_m3"] = (
            (float(powder) - float(powder_mean)) if powder is not None and powder_mean is not None else 0.0
        )
        item.features["rel_ucs_mpa"] = (float(ucs) - float(ucs_mean)) if ucs is not None and ucs_mean is not None else 0.0
    return observations


def vectorize_hole(observation: HoleObservation, feature_names: list[str] | tuple[str, ...] = HOLE_FEATURE_NAMES) -> list[float]:
    return [float(observation.features.get(name, 0.0) or 0.0) for name in feature_names]


def extract_hole_observation(design: BlastDesign, hole: Hole) -> HoleObservation:
    """Read-only hole row. Designed charges stay designed."""
    enabled = _enabled_holes(design)
    load = _loads_by_id(design).get(hole.id)
    pattern = dict(design.pattern_params or {})
    burden = local_burden(enabled, hole, design.contour)
    if burden is None:
        burden = _finite(pattern.get("burden_b_m"))
    spacing = local_spacing(enabled, hole)
    if spacing is None:
        spacing = _finite(pattern.get("spacing_a_m"))
    charge, stemming, powder = _designed_charge(load)
    density, ucs = _hole_rock(hole, design)
    wet = 1.0 if (hole.water_intervals or hole.measured_water_intervals) else 0.0
    features = {
        "x_m": float(hole.collar.x),
        "y_m": float(hole.collar.y),
        "burden_m": float(burden or 0.0),
        "spacing_m": float(spacing or 0.0),
        "diameter_mm": float(hole.diameter_mm or 0.0),
        "length_m": float(hole.length_m),
        "subdrill_m": float(hole.subdrill_m or 0.0),
        "charge_kg": float(charge or 0.0),
        "stemming_m": float(stemming or 0.0),
        "powder_factor_kg_m3": float(powder or 0.0),
        "delay_ms": float(_designed_delay_ms(design, hole.id) or 0.0),
        "density_kg_m3": float(density or 0.0),
        "ucs_mpa": float(ucs or 0.0),
        "wet": wet,
        "kind_code": KIND_CODES.get(str(hole.kind or "production"), 0.0),
    }
    executed: dict[str, float | None] = {}
    charged = next((item for item in design.as_charged_holes if item.design_hole_id == hole.id), None)
    if charged is not None:
        executed["charge_kg"] = _finite(charged.charge_mass_kg)
        executed["stemming_m"] = _finite(charged.stemming_length_m)
    drilled = next((item for item in design.as_drilled_holes if item.design_hole_id == hole.id), None)
    if drilled is not None:
        executed["length_m"] = _finite(drilled.length_m if hasattr(drilled, "length_m") else drilled.actual_depth)
        executed["diameter_mm"] = _finite(drilled.actual_diameter)
    return HoleObservation(
        hole_id=hole.id,
        x=float(hole.collar.x),
        y=float(hole.collar.y),
        kind=str(hole.kind or "production"),
        features=features,
        feature_role=ROLE_DESIGNED,
        executed=executed,
        source_blast_id=design.design_id,
    )


def extract_hole_observations(
    design: BlastDesign,
    *,
    site_id: str = "",
    neighbor_k: int = DEFAULT_NEIGHBOR_K,
    include_physics: bool = True,
) -> list[HoleObservation]:
    """All enabled holes. The live design is read-only."""
    rows = [extract_hole_observation(design, hole) for hole in _enabled_holes(design)]
    for row in rows:
        row.site_id = site_id
    add_relative_features(rows)
    attach_neighborhoods(rows, k=neighbor_k)
    if include_physics:
        attach_physics_predictions(design, rows)
    attach_block_measured(design, rows)
    return rows


def attach_block_measured(design: BlastDesign, observations: list[HoleObservation]) -> list[HoleObservation]:
    """Copy blast-block measured targets as context. They are not hole labels."""
    result = design.blast_result
    if result is None:
        return observations
    frag = result.fragmentation
    toe = result.toe_condition
    leftover = _finite(toe.leftover_height_m) if toe is not None else None
    toe_p = None
    if leftover is not None:
        toe_p = float(min(1.0, max(0.0, leftover)))
    for item in observations:
        if frag is not None:
            item.measured.setdefault(METRIC_X50, _finite(frag.x50_mm))
            item.measured.setdefault(METRIC_OVERSIZE, _finite(frag.oversize_pct))
        if toe_p is not None:
            item.measured.setdefault(METRIC_TOE, toe_p)
    return observations


def attach_physics_predictions(design: BlastDesign, observations: list[HoleObservation]) -> list[HoleObservation]:
    """Kuz-Ram hole regions as ROLE_PREDICTED context, never as measured labels."""
    try:
        from simulation.fragmentation.engine import predict_region
        from simulation.fragmentation.regions import (
            DEFAULT_EXPLOSIVE_DENSITY_T_M3,
            DEFAULT_EXPLOSIVE_ENERGY_MJ_KG,
            DEFAULT_ROCK_DENSITY_T_M3,
            DEFAULT_ROCK_FISSURING,
            DEFAULT_ROCK_UCS_MPA,
            ExplosiveSpec,
            RockSpec,
            collect_hole_regions,
        )
    except Exception:
        return observations
    try:
        regions = collect_hole_regions(
            design,
            lump_size_mm=400.0,
            default_rock=RockSpec(
                name=design.rock_name or "rock",
                density_t_m3=DEFAULT_ROCK_DENSITY_T_M3,
                ucs_mpa=DEFAULT_ROCK_UCS_MPA,
                fissuring_ff=DEFAULT_ROCK_FISSURING,
            ),
            default_explosive=ExplosiveSpec(
                name=design.explosive_key or "ANFO",
                density_t_m3=DEFAULT_EXPLOSIVE_DENSITY_T_M3,
                power_mj_kg=DEFAULT_EXPLOSIVE_ENERGY_MJ_KG,
            ),
        )
    except Exception:
        return observations
    by_hole: dict[str, Any] = {}
    for region in regions:
        if region.kind != "hole" or not region.hole_ids:
            continue
        try:
            prediction = predict_region(region.inputs, model="kuzram")
        except Exception:
            continue
        by_hole[region.hole_ids[0]] = prediction
    for item in observations:
        prediction = by_hole.get(item.hole_id)
        if prediction is None:
            continue
        item.predicted[METRIC_X50] = _finite(prediction.x50_mm)
        item.predicted[METRIC_OVERSIZE] = _finite(prediction.oversize_pct)
        item.predicted[METRIC_TOE] = _toe_from_local(item)
    return observations


def _toe_from_local(observation: HoleObservation) -> float:
    """Predicted toe leftover probability from local designed features only."""
    burden = float(observation.features.get("burden_m") or 0.0)
    charge = float(observation.features.get("charge_kg") or 0.0)
    subdrill = float(observation.features.get("subdrill_m") or 0.0)
    stemming = float(observation.features.get("stemming_m") or 0.0)
    length = float(observation.features.get("length_m") or 0.0)
    score = 0.15
    if burden > 4.5:
        score += 0.08 * (burden - 4.5)
    if charge > 0 and charge < 60.0:
        score += 0.01 * (60.0 - charge)
    if subdrill < 0.6:
        score += 0.12 * (0.6 - subdrill)
    if length > 0 and stemming > 0.35 * length:
        score += 0.15
    return float(min(1.0, max(0.0, score)))


def hole_rows_from_payload(rows: list[dict[str, Any]] | None, *, site_id: str = "") -> list[HoleObservation]:
    items = [HoleObservation.from_dict(row) for row in (rows or [])]
    for item in items:
        if site_id and not item.site_id:
            item.site_id = site_id
    if items and not any(item.neighbor_ids for item in items):
        attach_neighborhoods(items)
    if items and not any("rel_charge_kg" in item.features for item in items):
        add_relative_features(items)
    return items


def snapshot_hole_payload(observations: list[HoleObservation]) -> list[dict[str, Any]]:
    return [item.to_dict() for item in observations]


def feature_schema_version() -> str:
    return FEATURE_SCHEMA_VERSION
