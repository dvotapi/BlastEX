"""Apply a specialised outcome model as a recommendation overlay.

The result never writes back onto a design and never treats a candidate
model as silent production.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from design.models import BlastDesign
from intelligence.calibration.algorithms import get_algorithm
from intelligence.datasets.features import extract_features
from intelligence.outcomes.features import flatten_features, vectorize_features
from intelligence.outcomes.types import (
    APPLIED_AS_OVERLAY,
    ROLE_RECOMMENDATION,
    STATUS_CANDIDATE,
    STATUS_PRODUCTION,
    TARGET_OVERSIZE,
    TARGET_TOE_RISK,
    OutcomeModel,
    OutcomePrediction,
    TargetPrediction,
    normalize_model_type,
    spec_for,
)


def clamp_predicted(target_name: str, value: float) -> float:
    if target_name == TARGET_OVERSIZE:
        return float(min(100.0, max(0.0, value)))
    if target_name == TARGET_TOE_RISK:
        return float(min(1.0, max(0.0, value)))
    return float(max(0.0, value))


def _warnings_for(model: OutcomeModel) -> list[str]:
    warnings: list[str] = []
    if model.status == STATUS_CANDIDATE:
        warnings.append("Модель в статусе candidate: рекомендация, не производственный расчёт.")
    if model.status != STATUS_PRODUCTION:
        warnings.append("Модель исхода не утверждена как production и не подменяет инженерный проект.")
    warnings.append("ML не изменяет и не утверждает проект БВР — только слой рекомендации.")
    return warnings


def apply_model(
    model: OutcomeModel,
    *,
    features: dict[str, Any],
) -> OutcomePrediction:
    """Point prediction overlay; design is untouched."""
    if not model.estimators:
        raise ValueError("Артефакт модели не загружен.")
    algo = get_algorithm(model.algorithm)
    vector = vectorize_features(features, model.feature_names)
    X = np.asarray([vector], dtype=float)
    spec = spec_for(model.model_type)
    predictions: dict[str, TargetPrediction] = {}
    for target in spec["targets"]:
        name = target["name"]
        estimator = model.estimators.get(name)
        if estimator is None:
            continue
        raw = float(algo.predict(estimator, X)[0])
        predictions[name] = TargetPrediction(
            target_name=name,
            value=clamp_predicted(name, raw),
            unit=target["unit"],
            label=target["label"],
            model_type=model.model_type,
            prediction_applied=True,
        )
    if not predictions:
        raise ValueError("В артефакте нет обученных целей для прогноза.")
    primary = model.primary_target if model.primary_target in predictions else next(iter(predictions))
    primary_pred = predictions[primary]
    return OutcomePrediction(
        predicted=primary_pred.value,
        predictions=predictions,
        model_id=model.model_id,
        site_id=model.site_id,
        model_type=model.model_type,
        class_name=model.class_name or spec["class_name"],
        model_version=model.model_version,
        training_dataset_version=model.training_dataset_version,
        feature_schema_version=model.feature_schema_version,
        training_date=model.training_date,
        algorithm=model.algorithm,
        status=model.status,
        metrics=dict(model.metrics),
        primary_target=primary,
        unit=primary_pred.unit,
        applied_as=APPLIED_AS_OVERLAY,
        modifies_design=False,
        prediction_applied=True,
        warnings=_warnings_for(model),
        role=ROLE_RECOMMENDATION,
    )


def empty_prediction(
    *,
    model_type: str,
    site_id: str = "",
    reason: str = "",
) -> OutcomePrediction:
    spec = spec_for(model_type)
    warnings = ["Прогноз исхода не применён: нет выбранной специализированной модели."]
    if reason:
        warnings.insert(0, reason)
    warnings.append("ML не изменяет и не утверждает проект БВР — только слой рекомендации.")
    return OutcomePrediction(
        predicted=None,
        predictions={},
        model_id="",
        site_id=site_id,
        model_type=normalize_model_type(model_type),
        class_name=spec["class_name"],
        model_version=0,
        training_dataset_version=0,
        feature_schema_version="",
        training_date="",
        algorithm="",
        status="",
        metrics={},
        primary_target=spec["primary_target"],
        unit=spec["targets"][0]["unit"],
        applied_as=APPLIED_AS_OVERLAY,
        modifies_design=False,
        prediction_applied=False,
        warnings=warnings,
        role=ROLE_RECOMMENDATION,
    )


def features_from_design(design: BlastDesign, *, site_id: str) -> dict[str, Any]:
    return extract_features(design, site_id=site_id)


def flatten_from_design(design: BlastDesign, *, site_id: str) -> dict[str, float | None]:
    return flatten_features(features_from_design(design, site_id=site_id))
