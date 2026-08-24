"""Heatmap payload for predicted fragmentation. Same shape as ``design.maps``."""
from __future__ import annotations

from typing import Any

FRAGMENTATION_MAP_METRICS = (
    "x50",
    "x80",
    "oversize",
    "powder_factor",
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


def fragmentation_maps(hole_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """One sample per hole region: X50, X80, oversize %, powder factor."""
    holes: list[dict[str, Any]] = []
    for row in hole_rows:
        prediction = row.get("prediction") or {}
        inputs = row.get("inputs") or {}
        holes.append(
            {
                "hole_id": row["hole_ids"][0] if row.get("hole_ids") else row.get("id", ""),
                "kind": row.get("hole_kind", "production"),
                "x": row.get("x", 0.0),
                "y": row.get("y", 0.0),
                "x50": prediction.get("x50_mm"),
                "x80": prediction.get("x80_mm"),
                "oversize": prediction.get("oversize_pct"),
                "powder_factor": prediction.get("powder_factor_kg_m3", inputs.get("powder_factor_kg_m3")),
            }
        )
    stats: dict[str, dict[str, float]] = {}
    for metric in FRAGMENTATION_MAP_METRICS:
        values = [float(sample[metric]) for sample in holes if sample.get(metric) is not None]
        stats[metric] = {key: round(val, 3) for key, val in _stats(values).items()}
    return {
        "metrics": list(FRAGMENTATION_MAP_METRICS),
        "holes": holes,
        "stats": stats,
    }
