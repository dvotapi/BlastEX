"""Score immutable snapshots with the current production artifact.

Scoring is read-only: the live model is not retrained, promoted or replaced.
Calibration uses the snapshot's stored predicted baseline (ROLE_PREDICTED),
never a silent unit conversion.
"""
from __future__ import annotations

from typing import Any

from intelligence.datasets.builder import DatasetSnapshot
from intelligence.drift.types import ROLE_PREDICTED
from intelligence.registry.types import (
    FAMILY_CALIBRATION,
    FAMILY_LEARNING,
    FAMILY_OUTCOMES,
    normalize_family,
)


def score_snapshots(
    team_id: str,
    family: str,
    model_id: str,
    snapshots: list[DatasetSnapshot],
) -> dict[str, list[float]]:
    """Return per-target predicted series. Failures skip a sample, never deploy."""
    family = normalize_family(family)
    samples = [sample for snapshot in snapshots for sample in snapshot.samples]
    if family == FAMILY_LEARNING:
        return _score_learning(team_id, model_id, samples)
    if family == FAMILY_OUTCOMES:
        return _score_outcomes(team_id, model_id, samples)
    if family == FAMILY_CALIBRATION:
        return _score_calibration(team_id, model_id, samples)
    return {}


def _score_learning(team_id: str, model_id: str, samples: list[Any]) -> dict[str, list[float]]:
    from intelligence.learning.persistence import load_model
    from intelligence.learning.prediction import apply_model

    model = load_model(team_id, model_id)
    buckets: dict[str, list[float]] = {}
    for sample in samples:
        try:
            overlay = apply_model(model, features=sample.features)
        except (TypeError, ValueError):
            continue
        for name, item in (overlay.predictions or {}).items():
            value = getattr(item, "value", None)
            if value is None:
                continue
            buckets.setdefault(f"prediction.{name}", []).append(float(value))
    return buckets


def _score_outcomes(team_id: str, model_id: str, samples: list[Any]) -> dict[str, list[float]]:
    from intelligence.outcomes.persistence import load_model
    from intelligence.outcomes.prediction import apply_model

    model = load_model(team_id, model_id)
    buckets: dict[str, list[float]] = {}
    for sample in samples:
        try:
            overlay = apply_model(model, features=sample.features)
        except (TypeError, ValueError):
            continue
        for name, item in (overlay.predictions or {}).items():
            value = getattr(item, "value", None)
            if value is None:
                continue
            buckets.setdefault(f"prediction.{name}", []).append(float(value))
    return buckets


def _score_calibration(team_id: str, model_id: str, samples: list[Any]) -> dict[str, list[float]]:
    from intelligence.calibration.persistence import load_model
    from intelligence.calibration.prediction import apply_residual
    from intelligence.calibration.types import MODEL_SPECS, normalize_model_type

    model = load_model(team_id, model_id)
    spec = MODEL_SPECS[normalize_model_type(model.model_type)]
    group = spec["target_group"]
    baseline_field = spec["baseline_field"]
    unit = spec.get("unit") or ""
    buckets: dict[str, list[float]] = {}
    key = f"prediction.calibrated_{spec['measured_field']}"
    for sample in samples:
        payload = (sample.targets or {}).get(group) or {}
        baseline = payload.get(baseline_field)
        if baseline is None:
            continue
        try:
            overlay = apply_residual(
                model,
                features=sample.features,
                baseline=float(baseline),
                baseline_source=str(spec.get("baseline_source") or ""),
            )
        except (TypeError, ValueError):
            continue
        buckets.setdefault(key, []).append(float(overlay.calibrated))
    if unit and key in buckets:
        # Unit is already encoded in measured_field (x50_mm, oversize_pct, ...).
        _ = ROLE_PREDICTED
    return buckets
