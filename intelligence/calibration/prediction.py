"""Apply a residual model on top of an empirical/physics baseline.

The result is a recommendation overlay. It never writes back onto a design
and never treats a candidate model as silent production.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from intelligence.calibration.algorithms import get_algorithm
from intelligence.calibration.features import flatten_features, vectorize_features
from intelligence.calibration.types import (
    APPLIED_AS_OVERLAY,
    MODEL_KUZRAM_RESIDUAL,
    MODEL_OVERSIZE_RESIDUAL,
    MODEL_PPV_RESIDUAL,
    MODEL_SPECS,
    ROLE_RECOMMENDATION,
    STATUS_CANDIDATE,
    STATUS_PRODUCTION,
    CalibrationModel,
    CalibrationPrediction,
    normalize_model_type,
)
from intelligence.datasets.features import extract_features
from intelligence.uncertainty.assess import assess_vector, unavailable
from design.models import BlastDesign


def clamp_calibrated(model_type: str, value: float) -> float:
    model_type = normalize_model_type(model_type)
    if model_type == MODEL_OVERSIZE_RESIDUAL:
        return float(min(100.0, max(0.0, value)))
    if model_type == MODEL_PPV_RESIDUAL:
        return float(max(0.0, value))
    return float(max(0.0, value))


def _warnings_for(model: CalibrationModel) -> list[str]:
    warnings: list[str] = []
    if model.status == STATUS_CANDIDATE:
        warnings.append("Модель в статусе candidate: рекомендация, не производственный расчёт.")
    if model.status != STATUS_PRODUCTION:
        warnings.append("Калибровка не утверждена как production и не подменяет инженерный проект.")
    warnings.append("ML не изменяет и не утверждает проект БВР — только слой рекомендации.")
    return warnings


def apply_residual(
    model: CalibrationModel,
    *,
    features: dict[str, Any],
    baseline: float,
    baseline_source: str = "",
) -> CalibrationPrediction:
    """calibrated = baseline + residual. Overlay only; design is untouched."""
    if model.estimator is None:
        raise ValueError("Артефакт модели не загружен.")
    algo = get_algorithm(model.algorithm)
    vector = vectorize_features(features, model.feature_names, float(baseline))
    X = np.asarray([vector], dtype=float)
    residual = float(algo.predict(model.estimator, X)[0])
    calibrated = clamp_calibrated(model.model_type, float(baseline) + residual)
    spec = MODEL_SPECS[normalize_model_type(model.model_type)]
    result = CalibrationPrediction(
        baseline=float(baseline),
        residual=residual,
        calibrated=calibrated,
        model_id=model.model_id,
        site_id=model.site_id,
        model_type=model.model_type,
        model_version=model.model_version,
        training_dataset_version=model.training_dataset_version,
        feature_schema_version=model.feature_schema_version,
        training_date=model.training_date,
        algorithm=model.algorithm,
        status=model.status,
        metrics=dict(model.metrics),
        applied_as=APPLIED_AS_OVERLAY,
        modifies_design=False,
        calibration_applied=True,
        baseline_source=baseline_source or spec["baseline_source"],
        unit=spec["unit"],
        warnings=_warnings_for(model),
        role=ROLE_RECOMMENDATION,
    )
    rmse = (model.metrics or {}).get("rmse")
    assessment = assess_vector(
        prediction=calibrated,
        vector=vector,
        feature_names=model.feature_names,
        feature_ranges=model.feature_ranges,
        training_matrix=model.training_matrix,
        estimator=model.estimator,
        rmse=float(rmse) if rmse is not None else None,
        residual_offset=float(baseline),
        clamp=lambda value, model_type=model.model_type: clamp_calibrated(model_type, value),
        X=X,
    )
    result.apply_assessment(assessment)
    result.calibrated = float(assessment.prediction) if assessment.prediction is not None else calibrated
    result.residual = result.calibrated - float(baseline)
    return result


def baseline_without_model(
    *,
    baseline: float,
    model_type: str,
    site_id: str = "",
    baseline_source: str = "",
    reason: str = "",
) -> CalibrationPrediction:
    spec = MODEL_SPECS[normalize_model_type(model_type)]
    warnings = ["Калибровка не применена: используется только инженерный базис."]
    if reason:
        warnings.insert(0, reason)
    result = CalibrationPrediction(
        baseline=float(baseline),
        residual=0.0,
        calibrated=float(baseline),
        model_id="",
        site_id=site_id,
        model_type=normalize_model_type(model_type),
        model_version=0,
        training_dataset_version=0,
        feature_schema_version="",
        training_date="",
        algorithm="",
        status="",
        metrics={},
        applied_as=APPLIED_AS_OVERLAY,
        modifies_design=False,
        calibration_applied=False,
        baseline_source=baseline_source or spec["baseline_source"],
        unit=spec["unit"],
        warnings=warnings,
        role=ROLE_RECOMMENDATION,
    )
    result.apply_assessment(
        unavailable(
            prediction=float(baseline),
            reason=reason or "Калибровка не применена: интервал ML недоступен.",
        )
    )
    return result


def features_from_design(design: BlastDesign, *, site_id: str) -> dict[str, Any]:
    return extract_features(design, site_id=site_id)


def flatten_from_design(design: BlastDesign, *, site_id: str) -> dict[str, float | None]:
    return flatten_features(features_from_design(design, site_id=site_id))


def empirical_baseline(design: BlastDesign, model_type: str) -> tuple[float | None, str]:
    """Resolve Kuz-Ram / PPV empirical baseline without touching the design."""
    model_type = normalize_model_type(model_type)
    stored = _stored_predicted(design, model_type)
    if stored is not None:
        return stored, "stored_predicted"
    computed = _compute_empirical(design, model_type)
    if computed is not None:
        spec = MODEL_SPECS[model_type]
        return computed, spec["baseline_source"]
    return None, ""


def _stored_predicted(design: BlastDesign, model_type: str) -> float | None:
    result = design.blast_result
    if result is None or result.basis is None:
        return None
    if model_type in {MODEL_KUZRAM_RESIDUAL, MODEL_OVERSIZE_RESIDUAL}:
        predicted = result.basis.predicted_fragmentation
        if predicted is None:
            return None
        if model_type == MODEL_KUZRAM_RESIDUAL:
            return float(predicted.x50_mm) if predicted.x50_mm is not None else None
        return float(predicted.oversize_pct) if predicted.oversize_pct is not None else None
    predicted = result.basis.predicted_vibration or []
    values = [item.ppv_mm_s for item in predicted if item.ppv_mm_s is not None]
    return max(values) if values else None


def _compute_empirical(design: BlastDesign, model_type: str) -> float | None:
    if model_type in {MODEL_KUZRAM_RESIDUAL, MODEL_OVERSIZE_RESIDUAL}:
        from simulation.fragmentation.engine import predict_design

        try:
            payload = predict_design(design, model="kuzram")
        except ValueError:
            return None
        site = payload.get("site") or {}
        prediction = site.get("prediction") or {}
        key = "x50_mm" if model_type == MODEL_KUZRAM_RESIDUAL else "oversize_pct"
        value = prediction.get(key)
        return float(value) if value is not None else None
    from design.vibration import predict_design as predict_ppv_design

    try:
        payload = predict_ppv_design(design)
    except ValueError:
        return None
    values = [row.get("ppv_mm_s") for row in payload.get("predictions") or [] if row.get("ppv_mm_s") is not None]
    return max(float(item) for item in values) if values else None
