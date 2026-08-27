"""Heatmap payload for hole-level predicted X50 / oversize / toe / residual."""
from __future__ import annotations

from typing import Any

from intelligence.spatial.types import (
    ROLE_PREDICTED,
    SPATIAL_MAP_METRICS,
    UNITS,
    HolePrediction,
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


def spatial_maps(holes: list[HolePrediction]) -> dict[str, Any]:
    """One sample per hole: predicted X50, oversize, toe and residuals."""
    samples: list[dict[str, Any]] = []
    for row in holes:
        samples.append(
            {
                "hole_id": row.hole_id,
                "kind": row.kind,
                "x": row.x,
                "y": row.y,
                "x50": row.x50_mm,
                "oversize": row.oversize_pct,
                "toe": row.toe_probability,
                "residual_x50": row.residual_x50_mm,
                "residual_oversize": row.residual_oversize_pct,
                "residual_toe": row.residual_toe,
                "role": ROLE_PREDICTED,
            }
        )
    stats: dict[str, dict[str, float]] = {}
    for metric in SPATIAL_MAP_METRICS:
        values = [float(sample[metric]) for sample in samples if sample.get(metric) is not None]
        stats[metric] = {key: round(val, 3) for key, val in _stats(values).items()}
    return {
        "metrics": list(SPATIAL_MAP_METRICS),
        "holes": samples,
        "stats": stats,
        "units": {name: UNITS[name] for name in SPATIAL_MAP_METRICS},
        "role": ROLE_PREDICTED,
    }
