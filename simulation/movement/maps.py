"""Predicted-only heatmap payload for throw / heave / swell."""
from __future__ import annotations

from typing import Any

MOVEMENT_MAP_METRICS = (
    "throw",
    "heave",
    "swell",
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


def movement_maps(holes: list[dict[str, Any]]) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    for row in holes:
        samples.append(
            {
                "hole_id": row.get("hole_id", ""),
                "kind": row.get("hole_kind", "production"),
                "x": row.get("x", 0.0),
                "y": row.get("y", 0.0),
                "throw": row.get("throw_m"),
                "heave": row.get("heave_m"),
                "swell": row.get("swell_factor"),
            }
        )
    stats: dict[str, dict[str, float]] = {}
    for metric in MOVEMENT_MAP_METRICS:
        values = [float(sample[metric]) for sample in samples if sample.get(metric) is not None]
        stats[metric] = {key: round(val, 3) for key, val in _stats(values).items()}
    return {
        "metrics": list(MOVEMENT_MAP_METRICS),
        "role": "predicted",
        "holes": samples,
        "stats": stats,
    }
