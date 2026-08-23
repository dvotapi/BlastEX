"""Train and apply residual calibration. Never auto-deploys to production."""
from __future__ import annotations

from typing import Any

from design.models import BlastDesign
from api.exceptions import (
    CalibrationNotFoundError,
    DatasetNotFoundError,
    ImmutableCalibrationError,
    ImmutableDatasetError,
    InvalidCalibrationError,
)
from api.schemas.calibration import (
    AlgorithmListResponse,
    CalibrationListResponse,
    CalibrationModelSchema,
    CalibrationPredictRequest,
    CalibrationPredictResponse,
    CalibrationProvenanceSchema,
    CalibrationStatusRequest,
    CalibrationSummarySchema,
    CalibrationTrainRequest,
)
from intelligence.calibration.algorithms import DEFAULT_ALGORITHM, available_algorithms
from intelligence.calibration.persistence import (
    CalibrationNotFoundError as StoreNotFound,
    ImmutableCalibrationError as StoreImmutable,
)
from intelligence.calibration.persistence import (
    existing_versions,
    list_models,
    load_model,
    new_model_id,
    production_model,
    save_model,
    set_status,
)
from intelligence.calibration.prediction import (
    apply_residual,
    baseline_without_model,
    empirical_baseline,
    features_from_design,
)
from intelligence.calibration.training import next_model_version, train_from_snapshot
from intelligence.calibration.types import STATUS_CANDIDATE, normalize_model_type
from intelligence.datasets import persistence as dataset_persistence


def _model_schema(model) -> CalibrationModelSchema:
    payload = model.to_dict()
    payload.pop("estimator", None)
    payload.pop("training_matrix", None)
    return CalibrationModelSchema(**payload)


def _predict_schema(payload: dict[str, Any]) -> CalibrationPredictResponse:
    provenance = CalibrationProvenanceSchema(**payload.get("provenance") or {})
    data = dict(payload)
    data["provenance"] = provenance
    data["modifies_design"] = False
    data["applied_as"] = "recommendation_overlay"
    return CalibrationPredictResponse(**data)


def list_algorithms() -> AlgorithmListResponse:
    return AlgorithmListResponse(items=available_algorithms(), default=DEFAULT_ALGORITHM)


def list_calibration_models(team_id: str) -> CalibrationListResponse:
    items = list_models(team_id)
    return CalibrationListResponse(
        items=[CalibrationSummarySchema(**item.__dict__) for item in items]
    )


def get_calibration_model(team_id: str, model_id: str) -> CalibrationModelSchema:
    try:
        model = load_model(team_id, model_id)
    except StoreNotFound as exc:
        raise CalibrationNotFoundError(model_id) from exc
    except StoreImmutable as exc:
        raise ImmutableCalibrationError(str(exc)) from exc
    return _model_schema(model)


def train_calibration(team_id: str, request: CalibrationTrainRequest) -> CalibrationModelSchema:
    dataset_id = request.dataset_id.strip()
    if not dataset_id:
        raise InvalidCalibrationError("Для обучения нужен dataset_id неизменяемого снимка.")
    try:
        snapshot = dataset_persistence.load_snapshot(team_id, dataset_id)
    except dataset_persistence.DatasetNotFoundError as exc:
        raise DatasetNotFoundError(dataset_id) from exc
    except dataset_persistence.ImmutableDatasetError as exc:
        raise ImmutableDatasetError(str(exc)) from exc

    try:
        model_type = normalize_model_type(request.model_type)
        site_id = (request.site_id or snapshot.site_id).strip()
        model = train_from_snapshot(
            snapshot,
            model_type=model_type,
            algorithm=request.algorithm or DEFAULT_ALGORITHM,
            model_id=new_model_id(),
            model_version=next_model_version(existing_versions(team_id, site_id, model_type)),
            site_id=site_id,
        )
        saved = save_model(team_id, model)
    except ValueError as exc:
        raise InvalidCalibrationError(str(exc)) from exc
    except StoreImmutable as exc:
        raise ImmutableCalibrationError(str(exc)) from exc
    if saved.status != STATUS_CANDIDATE:
        raise InvalidCalibrationError("Новая модель должна сохраняться со статусом candidate.")
    return _model_schema(saved)


def update_status(team_id: str, model_id: str, request: CalibrationStatusRequest) -> CalibrationModelSchema:
    try:
        model = set_status(team_id, model_id, request.status)
    except StoreNotFound as exc:
        raise CalibrationNotFoundError(model_id) from exc
    except StoreImmutable as exc:
        raise ImmutableCalibrationError(str(exc)) from exc
    except ValueError as exc:
        raise InvalidCalibrationError(str(exc)) from exc
    return _model_schema(model)


def _design_from_request(request: CalibrationPredictRequest) -> BlastDesign | None:
    if request.design is None:
        return None
    return BlastDesign.from_dict(request.design.model_dump())


def predict_calibration(team_id: str, request: CalibrationPredictRequest) -> CalibrationPredictResponse:
    try:
        model_type = normalize_model_type(request.model_type)
    except ValueError as exc:
        raise InvalidCalibrationError(str(exc)) from exc

    design = _design_from_request(request)
    site_id = request.site_id.strip()
    if not site_id and design is not None:
        site_id = str((request.features or {}).get("SITE", {}).get("site_id") or "")
    if not site_id and design is not None:
        site_id = ""

    baseline = request.baseline
    baseline_source = "provided" if baseline is not None else ""
    if baseline is None and design is not None:
        baseline, baseline_source = empirical_baseline(design, model_type)
    if baseline is None:
        raise InvalidCalibrationError(
            "Для прогноза калибровки нужен baseline (Kuz-Ram / PPV) или паспорт с эмпирическим прогнозом."
        )

    features: dict[str, Any] = dict(request.features or {})
    if not features and design is not None:
        features = features_from_design(design, site_id=site_id or "unknown")

    model = None
    try:
        if request.model_id.strip():
            model = load_model(team_id, request.model_id.strip())
        elif request.use_production:
            if not site_id:
                raise InvalidCalibrationError("Для производственной модели нужен site_id.")
            model = production_model(team_id, site_id, model_type)
    except StoreNotFound as exc:
        raise CalibrationNotFoundError(request.model_id) from exc
    except StoreImmutable as exc:
        raise ImmutableCalibrationError(str(exc)) from exc

    if model is None:
        reason = "Нет выбранной модели калибровки."
        if request.use_production:
            reason = f"Нет production-модели «{model_type}» для площадки «{site_id}»."
        payload = baseline_without_model(
            baseline=float(baseline),
            model_type=model_type,
            site_id=site_id,
            baseline_source=baseline_source,
            reason=reason,
        )
        return _predict_schema(payload.to_dict())

    if site_id and model.site_id != site_id:
        raise InvalidCalibrationError("site_id запроса не совпадает с площадкой модели.")
    if model.model_type != model_type:
        raise InvalidCalibrationError("Тип модели не совпадает с запросом прогноза.")

    try:
        prediction = apply_residual(
            model,
            features=features,
            baseline=float(baseline),
            baseline_source=baseline_source,
        )
    except ValueError as exc:
        raise InvalidCalibrationError(str(exc)) from exc
    payload = prediction.to_dict()
    payload["modifies_design"] = False
    return _predict_schema(payload)
