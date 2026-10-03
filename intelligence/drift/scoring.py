"""Score immutable snapshots with the current production artifact.

Scoring is read-only: the live model is not retrained, promoted or replaced.
Calibration uses the snapshot's stored baseline, never a silent unit
conversion. Fragmentation calibrations score only rows whose baseline is
compatible with the artifact's base (intelligence.calibration.base).
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


def is_fragmentation_calibration(family: str, model_type: str) -> bool:
    """Калибровка кусковатости: её прогнозы сравниваются только на строках её базы.

    Откат на сохранённые прогнозы снимков смешал бы прогнозы разных формул.
    """
    from intelligence.calibration.base import FRAGMENTATION_RESIDUALS
    from intelligence.calibration.types import normalize_model_type

    if normalize_family(family) != FAMILY_CALIBRATION:
        return False
    try:
        return normalize_model_type(model_type) in FRAGMENTATION_RESIDUALS
    except ValueError:
        return False


def fragmentation_base_label(team_id: str, model_id: str) -> str:
    """Подпись базы артефакта калибровки кусковатости для предупреждения дрейфа.

    Артефакт, который не загрузился, подписывается своим id.
    """
    from intelligence.calibration.base import artifact_base
    from intelligence.calibration.persistence import load_model

    try:
        model = load_model(team_id, model_id)
    except Exception:  # noqa: BLE001 — подпись справочная: сбой загрузки не должен ронять проверку дрейфа
        return model_id
    try:
        return artifact_base(model.baseline_model, model.baseline_model_version).label()
    except ValueError:
        # Неизвестная модель в файле артефакта — подпись как записана.
        return f"{str(model.baseline_model).strip()} {str(model.baseline_model_version or '').strip()}".strip()


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
    from intelligence.calibration.base import FRAGMENTATION_RESIDUALS, artifact_base, sample_baseline
    from intelligence.calibration.persistence import load_model
    from intelligence.calibration.prediction import apply_residual
    from intelligence.calibration.types import MODEL_SPECS, normalize_model_type

    model = load_model(team_id, model_id)
    model_type = normalize_model_type(model.model_type)
    spec = MODEL_SPECS[model_type]
    group = spec["target_group"]
    baseline_field = spec["baseline_field"]
    base = None
    if model_type in FRAGMENTATION_RESIDUALS:
        try:
            base = artifact_base(model.baseline_model, model.baseline_model_version)
        except ValueError:
            # Неизвестная модель в файле артефакта: сравнивать нечего, дрейф не падает.
            return {}
    unit = spec.get("unit") or ""
    buckets: dict[str, list[float]] = {}
    key = f"prediction.calibrated_{spec['measured_field']}"
    for sample in samples:
        payload = (sample.targets or {}).get(group) or {}
        # Кусковатость — только строки той же базы, что и артефакт.
        baseline = sample_baseline(payload, model_type, base) if base is not None else payload.get(baseline_field)
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
