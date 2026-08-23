"""Apply a global prior or site-adapted model as a recommendation overlay."""
from __future__ import annotations

from typing import Any

import numpy as np

from design.models import BlastDesign
from intelligence.calibration.algorithms import get_algorithm
from intelligence.datasets.features import extract_features
from intelligence.explainability.explain import explain_estimator
from intelligence.explainability.types import empty_explanation
from intelligence.learning.types import (
    ADAPTATION_RESIDUAL,
    APPLIED_AS_OVERLAY,
    ROLE_RECOMMENDATION,
    STATUS_CANDIDATE,
    STATUS_PRODUCTION,
    LearnedModel,
    LearningPrediction,
    TargetContribution,
    normalize_model_type,
    spec_for,
)
from intelligence.outcomes.features import flatten_features, vectorize_features
from intelligence.outcomes.prediction import clamp_predicted
from intelligence.uncertainty.assess import assess_vector, unavailable
from intelligence.uncertainty.types import PredictionAssessment, UncertaintyInterval


def _target_as_assessment(item: TargetContribution) -> PredictionAssessment:
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


def _warnings_for(model: LearnedModel) -> list[str]:
    warnings: list[str] = []
    if model.status == STATUS_CANDIDATE:
        warnings.append("Модель в статусе candidate: рекомендация, не производственный расчёт.")
    if model.status != STATUS_PRODUCTION:
        warnings.append("Модель не утверждена как production и не подменяет инженерный проект.")
    if model.scope == "global":
        warnings.append("Глобальный prior не заменяет модель площадки без явной адаптации.")
    if model.prior_model_id:
        warnings.append(f"Площадочная модель стартовала от prior «{model.prior_model_id}».")
    warnings.append("ML не изменяет и не утверждает проект БВР — только слой рекомендации.")
    return warnings


def _predict_raw(estimator: Any, algorithm_name: str, X: np.ndarray) -> float:
    algo = get_algorithm(algorithm_name)
    return float(algo.predict(estimator, X)[0])


def apply_model(model: LearnedModel, *, features: dict[str, Any]) -> LearningPrediction:
    """Two-level point prediction; the design is untouched and not approved."""
    if not model.estimators:
        raise ValueError("Артефакт модели не загружен.")
    algo = get_algorithm(model.algorithm)
    vector = vectorize_features(features, model.feature_names)
    X = np.asarray([vector], dtype=float)
    spec = spec_for(model.model_type)
    predictions: dict[str, TargetContribution] = {}
    residual_mode = model.adaptation == ADAPTATION_RESIDUAL and bool(model.prior_estimators)

    for target in spec["targets"]:
        name = target["name"]
        estimator = model.estimators.get(name)
        if estimator is None:
            continue
        raw = _predict_raw(estimator, algo.name, X)
        global_value: float | None = None
        residual_value: float | None = None
        if residual_mode:
            prior_est = model.prior_estimators.get(name)
            if prior_est is not None:
                global_value = _predict_raw(prior_est, algo.name, X)
                residual_value = raw
                raw = global_value + residual_value
            else:
                global_value = None
                residual_value = None
        predictions[name] = TargetContribution(
            target_name=name,
            value=clamp_predicted(name, raw),
            unit=target["unit"],
            label=target["label"],
            model_type=model.model_type,
            global_value=None if global_value is None else clamp_predicted(name, global_value),
            residual_value=residual_value,
            prediction_applied=True,
        )

    if not predictions:
        raise ValueError("В артефакте нет обученных целей для прогноза.")
    primary = model.primary_target if model.primary_target in predictions else next(iter(predictions))
    primary_pred = predictions[primary]
    result = LearningPrediction(
        predicted=primary_pred.value,
        predictions=predictions,
        model_id=model.model_id,
        team_id=model.team_id,
        site_id=model.site_id,
        scope=model.scope,
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
        auto_approved=False,
        warnings=_warnings_for(model),
        role=ROLE_RECOMMENDATION,
        prior_model_id=model.prior_model_id,
        adaptation=model.adaptation,
    )
    per_target_metrics = (model.metrics or {}).get("targets") or {}
    for name, item in predictions.items():
        estimator = model.estimators.get(name)
        target_rmse = (per_target_metrics.get(name) or {}).get("rmse")
        if target_rmse is None and name == primary:
            target_rmse = (model.metrics or {}).get("rmse")
        assessment = assess_vector(
            prediction=item.value,
            vector=vector,
            feature_names=model.feature_names,
            feature_ranges=model.feature_ranges,
            training_matrix=model.training_matrix,
            estimator=estimator,
            rmse=float(target_rmse) if target_rmse is not None else None,
            clamp=lambda value, target=name: clamp_predicted(target, value),
            X=X,
        )
        item.apply_assessment(assessment)
        item.value = float(assessment.prediction) if assessment.prediction is not None else item.value
        explain_est = model.prior_estimators.get(name) if residual_mode else estimator
        item.apply_explanation(
            explain_estimator(
                estimator=explain_est or estimator,
                vector=vector,
                feature_names=model.feature_names,
                training_matrix=model.training_matrix,
                predict_fn=lambda matrix, est=explain_est or estimator: algo.predict(est, matrix),
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
    team_id: str = "",
    site_id: str = "",
    scope: str = "",
    reason: str = "",
) -> LearningPrediction:
    spec = spec_for(model_type)
    warnings = ["Прогноз обучения не применён: нет выбранной модели."]
    if reason:
        warnings.insert(0, reason)
    warnings.append("ML не изменяет и не утверждает проект БВР — только слой рекомендации.")
    result = LearningPrediction(
        predicted=None,
        predictions={},
        model_id="",
        team_id=team_id,
        site_id=site_id,
        scope=scope,
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
        auto_approved=False,
        warnings=warnings,
        role=ROLE_RECOMMENDATION,
    )
    result.apply_assessment(
        unavailable(reason=reason or "Прогноз обучения не применён: интервал ML недоступен.")
    )
    result.apply_explanation(empty_explanation(target_name=result.primary_target, unit=result.unit))
    return result


def features_from_design(design: BlastDesign, *, site_id: str) -> dict[str, Any]:
    return extract_features(design, site_id=site_id)


def flatten_from_design(design: BlastDesign, *, site_id: str) -> dict[str, float | None]:
    return flatten_features(features_from_design(design, site_id=site_id))
