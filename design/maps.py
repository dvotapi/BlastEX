"""Per-hole engineering maps for a blast design (phase BDX-003).

Heatmap-style data: one record per enabled hole plus min/avg/max stats.
Charging (BDX-004) consumes burden/spacing from these samples when present.
"""
from __future__ import annotations

from typing import Any

from design.editing import local_burden, local_spacing
from design.geometry import collar_burden, toe_burden, true_burden
from design.models import BlastDesign, Hole

MAP_METRICS = (
    "burden",
    "spacing",
    "hole_depth",
    "subdrill",
    "bench_height",
    "toe_burden",
    "collar_burden",
)


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "avg": 0.0, "max": 0.0, "count": 0.0}
    return {
        "min": min(values),
        "avg": sum(values) / len(values),
        "max": max(values),
        "count": float(len(values)),
    }


def _round_opt(value: float | None, places: int = 3) -> float | None:
    if value is None:
        return None
    return round(float(value), places)


def hole_map_record(hole: Hole, holes: list[Hole], contour) -> dict[str, Any]:
    burden = local_burden(holes, hole, contour)
    if burden is None:
        burden = true_burden(hole, contour)
    return {
        "hole_id": hole.id,
        "kind": hole.kind,
        "x": hole.collar.x,
        "y": hole.collar.y,
        "burden": _round_opt(burden),
        "spacing": _round_opt(local_spacing(holes, hole)),
        "hole_depth": round(hole.length_m, 3),
        "subdrill": round(hole.subdrill_m, 3),
        "bench_height": round(hole.bench_height_m, 3),
        "toe_burden": _round_opt(toe_burden(hole, contour)),
        "collar_burden": _round_opt(collar_burden(hole, contour)),
        "true_face_burden": _round_opt(true_burden(hole, contour)),
    }


def engineering_maps(design: BlastDesign) -> dict[str, Any]:
    """Return per-hole map samples and aggregate stats for MAP_METRICS."""
    enabled = [h for h in design.holes if h.enabled]
    holes = [hole_map_record(h, enabled, design.contour) for h in enabled]
    stats: dict[str, dict[str, float]] = {}
    for metric in MAP_METRICS:
        values = [float(row[metric]) for row in holes if row.get(metric) is not None]
        stats[metric] = {key: round(val, 3) for key, val in _stats(values).items()}
    return {
        "metrics": list(MAP_METRICS),
        "holes": holes,
        "stats": stats,
    }
