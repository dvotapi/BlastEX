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
from intelligence.explainability.explain import explain_estimator
from intelligence.explainability.types import empty_explanation
from intelligence.uncertainty.assess import assess_vector, unavailable
from intelligence.uncertainty.types import PredictionAssessment, UncertaintyInterval


def _target_as_assessment(item: TargetPrediction) -> PredictionAssessment:
    uncertainty = item.uncertainty or UncertaintyInterval.none().to_dict()
    return PredictionAssessment(
        prediction=item.prediction if item.prediction is not None else item.value,
        uncertainty=UncertaintyInterval(
            std=uncertainty.get("std"),
            lower=uncertainty.get("lower"),
            upper=uncertainty.get("upper"),
            method=str(uncertainty.get("method") or "none"),
        ),
        confidence=item.confidence,
        similarity_score=item.similarity_score,
        applicability_warning=item.applicability_warning,
        comparable_count=item.comparable_count,
        in_domain=item.in_domain,
        sample_count=item.sample_count,
        extrapolated_features=list(item.extrapolated_features),
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
    result = OutcomePrediction(
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
    per_target_metrics = (model.metrics or {}).get("targets") or {}
    for name, item in predictions.items():
        target_rmse = (per_target_metrics.get(name) or {}).get("rmse")
        if target_rmse is None and name == primary:
            target_rmse = (model.metrics or {}).get("rmse")
        assessment = assess_vector(
            prediction=item.value,
            vector=vector,
            feature_names=model.feature_names,
            feature_ranges=model.feature_ranges,
            training_matrix=model.training_matrix,
            estimator=model.estimators.get(name),
            rmse=float(target_rmse) if target_rmse is not None else None,
            clamp=lambda value, target=name: clamp_predicted(target, value),
            X=X,
        )
        item.apply_assessment(assessment)
        item.value = float(assessment.prediction) if assessment.prediction is not None else item.value
        item.apply_explanation(
            explain_estimator(
                estimator=estimator,
                vector=vector,
                feature_names=model.feature_names,
                training_matrix=model.training_matrix,
                predict_fn=lambda matrix, est=estimator: algo.predict(est, matrix),
                clamp=lambda value, target=name: clamp_predicted(target, value),
                target_name=name,
                target_label=item.label,
                unit=item.unit,
            )
        )
    result.apply_assessment(_target_as_assessment(predictions[primary]))
    result.predicted = predictions[primary].value
    result.apply_explanation(predictions[primary].explanation)
    return result


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
    result = OutcomePrediction(
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
    result.apply_assessment(
        unavailable(reason=reason or "Прогноз исхода не применён: интервал ML недоступен.")
    )
    result.apply_explanation(empty_explanation(target_name=result.primary_target, unit=result.unit))
    return result


def features_from_design(design: BlastDesign, *, site_id: str) -> dict[str, Any]:
    return extract_features(design, site_id=site_id)


def flatten_from_design(design: BlastDesign, *, site_id: str) -> dict[str, float | None]:
    return flatten_features(features_from_design(design, site_id=site_id))
