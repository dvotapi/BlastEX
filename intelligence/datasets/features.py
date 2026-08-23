"""Feature groups extracted from a closed BlastDesign.

Groups are Level 0 aggregates for later models (BDX-012). Extraction never
writes back onto the live design.
"""
from __future__ import annotations

import math
from typing import Any

from design.models import (
    ROLE_DESIGNED,
    BlastDesign,
    Hole,
    HoleLoad,
    explosive_charge_mass_kg,
    stemming_length_m,
)

FEATURE_GROUPS = (
    "SITE",
    "GEOLOGY",
    "GEOMETRY",
    "CHARGING",
    "TIMING",
    "EXECUTION",
    "ENVIRONMENT",
)

FEATURE_SCHEMA_VERSION = "1.0.0"


def _mean(values: list[float | None]) -> float | None:
    nums = [float(item) for item in values if item is not None]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 6)


def _round(value: float | None, places: int = 6) -> float | None:
    if value is None:
        return None
    return round(float(value), places)


def _distance3(ax: float, ay: float, az: float, bx: float, by: float, bz: float) -> float:
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)


def _shoelace_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    total = 0.0
    count = len(points)
    for index in range(count):
        x1, y1 = points[index]
        x2, y2 = points[(index + 1) % count]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def _dominant_text(values: list[str]) -> str:
    counts: dict[str, int] = {}
    for raw in values:
        text = str(raw or "").strip()
        if not text:
            continue
        counts[text] = counts.get(text, 0) + 1
    if not counts:
        return ""
    return max(counts.items(), key=lambda item: (item[1], item[0]))[0]


def _enabled_holes(design: BlastDesign) -> list[Hole]:
    return [hole for hole in design.holes if hole.enabled]


def _loads_by_id(design: BlastDesign) -> dict[str, HoleLoad]:
    return {load.hole_id: load for load in design.loads}


def extract_site_features(design: BlastDesign, *, site_id: str) -> dict[str, Any]:
    bench = design.contour.bench
    crs = design.coordinate_system
    return {
        "group": "SITE",
        "site_id": site_id,
        "design_id": design.design_id,
        "design_name": design.name,
        "rock_name": design.rock_name,
        "coordinate_system_name": getattr(crs, "name", "") or "",
        "epsg": getattr(crs, "epsg", None),
        "units": getattr(crs, "units", "m") or "m",
        "bench_height_m": _round(bench.height_m, 3),
        "bench_face_angle_deg": _round(bench.face_angle_deg, 3),
        "contour_name": design.contour.name,
        "water_table_z_m": design.water_table_z_m,
        "receptor_count": len(design.receptors),
        "role": ROLE_DESIGNED,
    }


def extract_geology_features(design: BlastDesign) -> dict[str, Any]:
    densities: list[float | None] = []
    ucs: list[float | None] = []
    rqd: list[float | None] = []
    fracturing: list[str] = []
    blastability: list[str] = []
    water: list[str] = []
    interval_count = 0
    for domain in design.domains:
        props = domain.properties
        densities.append(props.density_kg_m3)
        ucs.append(props.ucs_mpa)
        rqd.append(props.rqd_pct)
        fracturing.append(props.fracturing)
        blastability.append(props.blastability)
        water.append(props.water_condition)
    wet_holes = 0
    for hole in _enabled_holes(design):
        interval_count += len(hole.intervals) + len(hole.measured_intervals)
        if hole.water_intervals or hole.measured_water_intervals:
            wet_holes += 1
        for interval in list(hole.intervals) + list(hole.measured_intervals):
            densities.append(interval.properties.density_kg_m3)
            ucs.append(interval.properties.ucs_mpa)
            rqd.append(interval.properties.rqd_pct)
            fracturing.append(interval.properties.fracturing)
            blastability.append(interval.properties.blastability)
            water.append(interval.properties.water_condition)
    return {
        "group": "GEOLOGY",
        "domain_count": len(design.domains),
        "interval_count": interval_count,
        "mean_density_kg_m3": _mean(densities),
        "mean_ucs_mpa": _mean(ucs),
        "mean_rqd_pct": _mean(rqd),
        "dominant_fracturing": _dominant_text(fracturing),
        "dominant_blastability": _dominant_text(blastability),
        "water_condition": _dominant_text(water),
        "wet_hole_count": wet_holes,
        "role": ROLE_DESIGNED,
    }


def extract_geometry_features(design: BlastDesign) -> dict[str, Any]:
    holes = _enabled_holes(design)
    params = design.pattern_params or {}
    spacing = params.get("spacing_a_m")
    burden = params.get("burden_b_m")
    area = _shoelace_area([(vertex.x, vertex.y) for vertex in design.contour.vertices])
    return {
        "group": "GEOMETRY",
        "hole_count": len(design.holes),
        "enabled_hole_count": len(holes),
        "mean_spacing_m": _round(float(spacing) if spacing not in (None, "") else None, 3),
        "mean_burden_m": _round(float(burden) if burden not in (None, "") else None, 3),
        "mean_diameter_mm": _mean([hole.diameter_mm for hole in holes]),
        "mean_depth_m": _mean([hole.length_m for hole in holes]),
        "mean_subdrill_m": _mean([hole.subdrill_m for hole in holes]),
        "mean_angle_deg": _mean([hole.angle_deg for hole in holes]),
        "pattern_type": str(params.get("pattern", "") or ""),
        "block_area_m2": _round(area, 3),
        "bench_height_m": _round(design.contour.bench.height_m, 3),
        "role": ROLE_DESIGNED,
    }


def extract_charging_features(design: BlastDesign) -> dict[str, Any]:
    loads = _loads_by_id(design)
    holes = _enabled_holes(design)
    masses: list[float] = []
    factors: list[float | None] = []
    stemming: list[float] = []
    deck_count = 0
    primer_count = 0
    for hole in holes:
        load = loads.get(hole.id)
        if load is None:
            continue
        mass = float(load.total_charge_kg or 0.0)
        if mass <= 0 and load.decks:
            mass = explosive_charge_mass_kg(load.decks)
        masses.append(mass)
        if load.specific_q_kg_m3:
            factors.append(load.specific_q_kg_m3)
        elif load.influence_volume_m3:
            factors.append(mass / load.influence_volume_m3)
        stemming.append(stemming_length_m(load.decks))
        deck_count += len(load.decks)
        primer_count += len(load.primer_items or load.primers)
    return {
        "group": "CHARGING",
        "charged_hole_count": len(masses),
        "total_charge_kg": _round(sum(masses), 3) if masses else None,
        "mean_charge_kg": _mean(masses),
        "mean_powder_factor_kg_m3": _mean(factors),
        "mean_stemming_m": _mean(stemming),
        "explosive_key": design.explosive_key,
        "deck_count": deck_count,
        "primer_count": primer_count,
        "role": ROLE_DESIGNED,
    }


def extract_timing_features(design: BlastDesign) -> dict[str, Any]:
    network = design.network
    delays = [float(item.delay_ms) for item in network.detonators]
    if not delays:
        delays = [float(value) for value in network.downhole_delay_ms.values()]
    times = [float(value) for value in network.electronic_times_ms.values()]
    if not times:
        times = [float(event.time_ms) for event in network.firing_events if event.time_ms is not None]
    return {
        "group": "TIMING",
        "system": network.system,
        "timing_mode": network.timing_mode,
        "detonator_count": len(network.detonators),
        "connector_count": len(network.connectors) + len(network.surface_connectors),
        "mean_delay_ms": _mean(delays),
        "min_delay_ms": _round(min(delays), 3) if delays else None,
        "max_delay_ms": _round(max(delays), 3) if delays else None,
        "hole_times_count": len(times),
        "mean_hole_time_ms": _mean(times),
        "role": ROLE_DESIGNED,
    }


def extract_execution_features(design: BlastDesign) -> dict[str, Any]:
    holes = {hole.id: hole for hole in design.holes}
    loads = _loads_by_id(design)
    designed_times = dict(design.network.electronic_times_ms)
    for detonator in design.network.detonators:
        designed_times.setdefault(detonator.hole_id, detonator.delay_ms)

    collar_offsets: list[float] = []
    depth_deltas: list[float] = []
    for item in design.as_drilled_holes:
        designed = holes.get(item.design_hole_id)
        if designed is None:
            continue
        collar_offsets.append(
            _distance3(
                item.actual_collar.x,
                item.actual_collar.y,
                item.actual_collar.z,
                designed.collar.x,
                designed.collar.y,
                designed.collar.z,
            )
        )
        depth_deltas.append(item.length_m - designed.length_m)

    mass_deltas: list[float] = []
    for item in design.as_charged_holes:
        designed_load = loads.get(item.design_hole_id)
        designed_mass = float(designed_load.total_charge_kg) if designed_load else 0.0
        mass_deltas.append(float(item.charge_mass_kg) - designed_mass)

    time_deltas: list[float] = []
    for item in design.as_fired_holes:
        designed_time = designed_times.get(item.design_hole_id)
        if designed_time is None:
            continue
        actual = item.verified_time_ms if item.verified_time_ms is not None else item.programmed_time_ms
        time_deltas.append(float(actual) - float(designed_time))

    enabled = max(1, len(_enabled_holes(design)))
    return {
        "group": "EXECUTION",
        "as_drilled_count": len(design.as_drilled_holes),
        "as_charged_count": len(design.as_charged_holes),
        "as_fired_count": len(design.as_fired_holes),
        "mean_collar_offset_m": _mean(collar_offsets),
        "mean_depth_deviation_m": _mean(depth_deltas),
        "mean_charge_mass_delta_kg": _mean(mass_deltas),
        "mean_time_delta_ms": _mean(time_deltas),
        "drilled_coverage": round(len(design.as_drilled_holes) / enabled, 6),
        "charged_coverage": round(len(design.as_charged_holes) / enabled, 6),
        "fired_coverage": round(len(design.as_fired_holes) / enabled, 6),
        "role": "executed",
    }


def extract_environment_features(design: BlastDesign) -> dict[str, Any]:
    holes = _enabled_holes(design)
    wet = 0
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for hole in holes:
        if hole.water_intervals or hole.measured_water_intervals:
            wet += 1
        xs.append(hole.collar.x)
        ys.append(hole.collar.y)
        zs.append(hole.collar.z)
    centroid = (
        (sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs)) if xs else None
    )
    nearest: float | None = None
    if centroid is not None:
        distances = [
            _distance3(
                receptor.location.x,
                receptor.location.y,
                receptor.location.z,
                centroid[0],
                centroid[1],
                centroid[2],
            )
            for receptor in design.receptors
        ]
        nearest = min(distances) if distances else None
    model = design.vibration_models[0] if design.vibration_models else None
    surfaces = design.surfaces
    present = []
    for kind in ("top", "floor", "face", "post_blast"):
        if getattr(surfaces, kind, None) is not None:
            present.append(kind)
    wet_fraction = round(wet / len(holes), 6) if holes else None
    return {
        "group": "ENVIRONMENT",
        "water_table_z_m": design.water_table_z_m,
        "wet_hole_count": wet,
        "wet_hole_fraction": wet_fraction,
        "receptor_count": len(design.receptors),
        "nearest_receptor_distance_m": _round(nearest, 3),
        "vibration_model_k": model.k if model else None,
        "vibration_model_n": model.n if model else None,
        "vibration_convention": model.scaled_distance if model else "",
        "surface_kinds": present,
        "role": ROLE_DESIGNED,
    }


def extract_features(design: BlastDesign, *, site_id: str) -> dict[str, dict[str, Any]]:
    """Return all seven feature groups. The live design is read-only."""
    return {
        "SITE": extract_site_features(design, site_id=site_id),
        "GEOLOGY": extract_geology_features(design),
        "GEOMETRY": extract_geometry_features(design),
        "CHARGING": extract_charging_features(design),
        "TIMING": extract_timing_features(design),
        "EXECUTION": extract_execution_features(design),
        "ENVIRONMENT": extract_environment_features(design),
    }
