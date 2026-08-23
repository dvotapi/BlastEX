"""Local residuals at hole / neighborhood scale (BDX-022).

A residual keeps the unit of the named field. x50_mm residuals stay in
millimetres; oversize stays in percent. There is no silent conversion.
"""
from __future__ import annotations

from typing import Any

from intelligence.spatial.types import (
    METRIC_OVERSIZE,
    METRIC_TOE,
    METRIC_X50,
    RESIDUAL_OVERSIZE,
    RESIDUAL_TOE,
    RESIDUAL_X50,
    ROLE_MEASURED,
    ROLE_PREDICTED,
    HoleObservation,
    HolePrediction,
    NeighborhoodPrediction,
)


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: list[float | None]) -> float | None:
    nums = [float(item) for item in values if item is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def block_baseline(observations: list[HoleObservation], metric: str) -> float | None:
    """Block-level predicted baseline. Measured is never used as the predicted mean."""
    predicted = _mean([_as_float((item.predicted or {}).get(metric)) for item in observations])
    if predicted is not None:
        return predicted
    return None


def residual_target(observation: HoleObservation, metric: str, *, block_predicted: float | None) -> float | None:
    """Training target for a local residual.

    Prefer hole-level measured minus block predicted. If only physics
    predictions exist, use hole predicted minus the block predicted mean.
    Measured never overwrites the predicted layer.
    """
    local_measured = _as_float((observation.measured or {}).get(metric))
    local_predicted = _as_float((observation.predicted or {}).get(metric))
    if local_measured is not None and block_predicted is not None:
        return float(local_measured - block_predicted)
    if local_predicted is not None and block_predicted is not None:
        return float(local_predicted - block_predicted)
    return None


def residual_tables(
    observations: list[HoleObservation],
    *,
    feature_names: list[str],
) -> dict[str, dict[str, Any]]:
    """Build X / y tables for residual_x50 / residual_oversize / residual_toe."""
    baselines = {
        METRIC_X50: block_baseline(observations, METRIC_X50),
        METRIC_OVERSIZE: block_baseline(observations, METRIC_OVERSIZE),
        METRIC_TOE: block_baseline(observations, METRIC_TOE),
    }
    mapping = {
        RESIDUAL_X50: METRIC_X50,
        RESIDUAL_OVERSIZE: METRIC_OVERSIZE,
        RESIDUAL_TOE: METRIC_TOE,
    }
    tables: dict[str, dict[str, Any]] = {}
    for residual_name, metric in mapping.items():
        X: list[list[float]] = []
        y: list[float] = []
        hole_ids: list[str] = []
        for item in observations:
            target = residual_target(item, metric, block_predicted=baselines[metric])
            if target is None:
                continue
            X.append([float(item.features.get(name, 0.0) or 0.0) for name in feature_names])
            y.append(float(target))
            hole_ids.append(item.hole_id)
        tables[residual_name] = {
            "name": residual_name,
            "metric": metric,
            "unit": "mm" if metric == METRIC_X50 else ("%" if metric == METRIC_OVERSIZE else ""),
            "role": ROLE_PREDICTED,
            "X": X,
            "y": y,
            "hole_ids": hole_ids,
            "block_predicted": baselines[metric],
        }
    return tables


def apply_residuals(
    observations: list[HoleObservation],
    residuals: dict[str, list[float | None]],
    *,
    block: dict[str, float | None],
) -> list[HolePrediction]:
    """Ŷ_hole = Ŷ_block + residual. Role stays predicted."""
    rows: list[HolePrediction] = []
    for index, item in enumerate(observations):
        rx50 = _nth(residuals.get(RESIDUAL_X50), index)
        rover = _nth(residuals.get(RESIDUAL_OVERSIZE), index)
        rtoe = _nth(residuals.get(RESIDUAL_TOE), index)
        x50 = _sum(block.get(METRIC_X50), rx50)
        oversize = _sum(block.get(METRIC_OVERSIZE), rover)
        toe = _sum(block.get(METRIC_TOE), rtoe)
        if x50 is not None:
            x50 = max(0.0, x50)
        if oversize is not None:
            oversize = min(100.0, max(0.0, oversize))
        if toe is not None:
            toe = min(1.0, max(0.0, toe))
        measured_x50 = _as_float((item.measured or {}).get(METRIC_X50))
        measured_over = _as_float((item.measured or {}).get(METRIC_OVERSIZE))
        measured_toe = _as_float((item.measured or {}).get(METRIC_TOE))
        rows.append(
            HolePrediction(
                hole_id=item.hole_id,
                x=item.x,
                y=item.y,
                kind=item.kind,
                x50_mm=x50,
                oversize_pct=oversize,
                toe_probability=toe,
                residual_x50_mm=rx50,
                residual_oversize_pct=rover,
                residual_toe=rtoe,
                measured_x50_mm=measured_x50,
                measured_oversize_pct=measured_over,
                measured_toe_probability=measured_toe,
                residual_vs_measured_x50_mm=_diff(measured_x50, x50),
                residual_vs_measured_oversize_pct=_diff(measured_over, oversize),
                residual_vs_measured_toe=_diff(measured_toe, toe),
                neighbor_ids=list(item.neighbor_ids),
                role=ROLE_PREDICTED,
            )
        )
    return rows


def neighborhood_from_holes(
    holes: list[HolePrediction],
    observations: list[HoleObservation],
) -> list[NeighborhoodPrediction]:
    by_id = {item.hole_id: item for item in holes}
    neighborhoods: list[NeighborhoodPrediction] = []
    for item in observations:
        members = [by_id[item.hole_id]] if item.hole_id in by_id else []
        for hid in item.neighbor_ids:
            if hid in by_id:
                members.append(by_id[hid])
        if not members:
            continue
        neighborhoods.append(
            NeighborhoodPrediction(
                hole_id=item.hole_id,
                member_ids=[row.hole_id for row in members],
                x=item.x,
                y=item.y,
                x50_mm=_mean([row.x50_mm for row in members]),
                oversize_pct=_mean([row.oversize_pct for row in members]),
                toe_probability=_mean([row.toe_probability for row in members]),
                residual_x50_mm=_mean([row.residual_x50_mm for row in members]),
                residual_oversize_pct=_mean([row.residual_oversize_pct for row in members]),
                residual_toe=_mean([row.residual_toe for row in members]),
                role=ROLE_PREDICTED,
            )
        )
    return neighborhoods


def physics_residuals(observations: list[HoleObservation]) -> dict[str, list[float | None]]:
    """Fallback residual: hole physics minus block physics mean."""
    mapping = {
        RESIDUAL_X50: METRIC_X50,
        RESIDUAL_OVERSIZE: METRIC_OVERSIZE,
        RESIDUAL_TOE: METRIC_TOE,
    }
    out: dict[str, list[float | None]] = {}
    for residual_name, metric in mapping.items():
        baseline = block_baseline(observations, metric)
        values: list[float | None] = []
        for item in observations:
            local = _as_float((item.predicted or {}).get(metric))
            if local is None or baseline is None:
                values.append(None)
            else:
                values.append(float(local - baseline))
        out[residual_name] = values
    return out


def _nth(values: list[float | None] | None, index: int) -> float | None:
    if not values or index >= len(values):
        return None
    return values[index]


def _sum(left: float | None, right: float | None) -> float | None:
    if left is None and right is None:
        return None
    return float(left or 0.0) + float(right or 0.0)


def _diff(measured: float | None, predicted: float | None) -> float | None:
    if measured is None or predicted is None:
        return None
    return float(measured) - float(predicted)


# ROLE_MEASURED is referenced so tests can assert residual-vs-measured stays measured-minus-predicted.
_ = ROLE_MEASURED
