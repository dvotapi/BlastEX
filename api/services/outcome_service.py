"""Train and apply specialised outcome models. Never auto-deploys to production."""
from __future__ import annotations

from typing import Any

from design.models import BlastDesign
from api.exceptions import (
    DatasetNotFoundError,
    ImmutableDatasetError,
    ImmutableOutcomeError,
    InvalidOutcomeError,
    OutcomeNotFoundError,
)
from api.schemas.calibration import AlgorithmListResponse
from api.schemas.outcomes import (
    OutcomeListResponse,
    OutcomeModelSchema,
    OutcomeModelTypeListResponse,
    OutcomeModelTypeSchema,
    OutcomePanelResponse,
    OutcomePredictAllRequest,
    OutcomePredictRequest,
    OutcomePredictResponse,
    OutcomeProvenanceSchema,
    OutcomeStatusRequest,
    OutcomeSummarySchema,
    OutcomeTargetPredictionSchema,
    OutcomeTrainRequest,
)
from intelligence.calibration.algorithms import DEFAULT_ALGORITHM, available_algorithms
from intelligence.datasets import persistence as dataset_persistence
from intelligence.outcomes.persistence import (
    ImmutableOutcomeError as StoreImmutable,
    OutcomeNotFoundError as StoreNotFound,
    existing_versions,
    list_models,
    load_model,
    new_model_id,
    production_model,
    save_model,
    set_status,
)
from intelligence.outcomes.prediction import apply_model, empty_prediction, features_from_design
from intelligence.outcomes.training import next_model_version, train_from_snapshot
from intelligence.outcomes.types import (
    MODEL_TYPES,
    STATUS_CANDIDATE,
    TARGET_FREQUENCY,
    TARGET_OVERSIZE,
    TARGET_PPV,
    TARGET_TOE_RISK,
    TARGET_X50,
    TARGET_X80,
    listed_model_types,
    normalize_model_type,
)


def _model_schema(model) -> OutcomeModelSchema:
    payload = model.to_dict()
    payload.pop("estimators", None)
    return OutcomeModelSchema(**payload)


def _predict_schema(payload: dict[str, Any]) -> OutcomePredictResponse:
    provenance = OutcomeProvenanceSchema(**payload.get("provenance") or {})
    predictions = {
        name: OutcomeTargetPredictionSchema(**item)
        for name, item in (payload.get("predictions") or {}).items()
    }
    data = dict(payload)
    data["provenance"] = provenance
    data["predictions"] = predictions
    data["modifies_design"] = False
    data["applied_as"] = "recommendation_overlay"
    return OutcomePredictResponse(**data)


def list_algorithms() -> AlgorithmListResponse:
    return AlgorithmListResponse(items=available_algorithms(), default=DEFAULT_ALGORITHM)


def list_outcome_types() -> OutcomeModelTypeListResponse:
    return OutcomeModelTypeListResponse(
        items=[OutcomeModelTypeSchema(**item) for item in listed_model_types()]
    )


def list_outcome_models(team_id: str, model_type: str = "") -> OutcomeListResponse:
    wanted = ""
    if model_type.strip():
        try:
            wanted = normalize_model_type(model_type)
        except ValueError as exc:
            raise InvalidOutcomeError(str(exc)) from exc
    items = list_models(team_id, model_type=wanted)
    return OutcomeListResponse(items=[OutcomeSummarySchema(**item.__dict__) for item in items])


def get_outcome_model(team_id: str, model_id: str) -> OutcomeModelSchema:
    try:
        model = load_model(team_id, model_id)
    except StoreNotFound as exc:
        raise OutcomeNotFoundError(model_id) from exc
    except StoreImmutable as exc:
        raise ImmutableOutcomeError(str(exc)) from exc
    return _model_schema(model)


def train_outcome(team_id: str, request: OutcomeTrainRequest) -> OutcomeModelSchema:
    dataset_id = request.dataset_id.strip()
    if not dataset_id:
        raise InvalidOutcomeError("Для обучения нужен dataset_id неизменяемого снимка.")
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
        raise InvalidOutcomeError(str(exc)) from exc
    except StoreImmutable as exc:
        raise ImmutableOutcomeError(str(exc)) from exc
    if saved.status != STATUS_CANDIDATE:
        raise InvalidOutcomeError("Новая модель должна сохраняться со статусом candidate.")
    return _model_schema(saved)


def update_status(team_id: str, model_id: str, request: OutcomeStatusRequest) -> OutcomeModelSchema:
    try:
        model = set_status(team_id, model_id, request.status)
    except StoreNotFound as exc:
        raise OutcomeNotFoundError(model_id) from exc
    except StoreImmutable as exc:
        raise ImmutableOutcomeError(str(exc)) from exc
    except ValueError as exc:
        raise InvalidOutcomeError(str(exc)) from exc
    return _model_schema(model)


def _design_from_request(design: BlastDesignSchema | None) -> BlastDesign | None:
    if design is None:
        return None
    return BlastDesign.from_dict(design.model_dump())


def _resolve_features(
    *,
    features: dict[str, Any] | None,
    design: BlastDesign | None,
    site_id: str,
) -> dict[str, Any]:
    if features:
        return dict(features)
    if design is not None:
        return features_from_design(design, site_id=site_id or "unknown")
    raise InvalidOutcomeError("Для прогноза исхода нужны признаки или паспорт БВР.")


def _predict_with_model(
    team_id: str,
    *,
    model_type: str,
    model_id: str,
    site_id: str,
    use_production: bool,
    features: dict[str, Any],
) -> OutcomePredictResponse:
    model = None
    try:
        if model_id.strip():
            model = load_model(team_id, model_id.strip())
        elif use_production:
            if not site_id:
                raise InvalidOutcomeError("Для производственной модели нужен site_id.")
            model = production_model(team_id, site_id, model_type)
    except StoreNotFound as exc:
        raise OutcomeNotFoundError(model_id) from exc
    except StoreImmutable as exc:
        raise ImmutableOutcomeError(str(exc)) from exc

    if model is None:
        reason = "Нет выбранной модели исхода."
        if use_production:
            reason = f"Нет production-модели «{model_type}» для площадки «{site_id}»."
        payload = empty_prediction(model_type=model_type, site_id=site_id, reason=reason)
        return _predict_schema(payload.to_dict())

    if site_id and model.site_id != site_id:
        raise InvalidOutcomeError("site_id запроса не совпадает с площадкой модели.")
    if model.model_type != model_type:
        raise InvalidOutcomeError("Тип модели не совпадает с запросом прогноза.")

    try:
        prediction = apply_model(model, features=features)
    except ValueError as exc:
        raise InvalidOutcomeError(str(exc)) from exc
    payload = prediction.to_dict()
    payload["modifies_design"] = False
    return _predict_schema(payload)


def predict_outcome(team_id: str, request: OutcomePredictRequest) -> OutcomePredictResponse:
    try:
        model_type = normalize_model_type(request.model_type)
    except ValueError as exc:
        raise InvalidOutcomeError(str(exc)) from exc

    design = _design_from_request(request.design)
    site_id = request.site_id.strip()
    if not site_id and design is not None:
        site_id = str((request.features or {}).get("SITE", {}).get("site_id") or "")
    features = _resolve_features(features=request.features, design=design, site_id=site_id)
    return _predict_with_model(
        team_id,
        model_type=model_type,
        model_id=request.model_id,
        site_id=site_id,
        use_production=request.use_production,
        features=features,
    )


def _panel_target(prediction: OutcomePredictResponse, name: str) -> OutcomeTargetPredictionSchema | None:
    item = prediction.predictions.get(name)
    if item is None or not prediction.prediction_applied:
        return OutcomeTargetPredictionSchema(
            target_name=name,
            value=None,
            unit="",
            label="",
            model_type=prediction.model_type,
            prediction_applied=False,
        )
    return item


def predict_panel(team_id: str, request: OutcomePredictAllRequest) -> OutcomePanelResponse:
    design = _design_from_request(request.design)
    site_id = request.site_id.strip()
    if not site_id and design is not None:
        site_id = str((request.features or {}).get("SITE", {}).get("site_id") or "")
    features = _resolve_features(features=request.features, design=design, site_id=site_id)

    models: dict[str, OutcomePredictResponse] = {}
    warnings: list[str] = ["ML не изменяет и не утверждает проект БВР — только слой рекомендации."]
    for model_type in MODEL_TYPES:
        override_id = str(request.model_ids.get(model_type) or "").strip()
        prediction = _predict_with_model(
            team_id,
            model_type=model_type,
            model_id=override_id,
            site_id=site_id,
            use_production=request.use_production and not override_id,
            features=features,
        )
        models[model_type] = prediction
        if prediction.warnings:
            warnings.extend(prediction.warnings[:1])

    fragmentation = models["fragmentation"]
    vibration = models["vibration"]
    oversize = models["oversize"]
    toe = models["toe_risk"]
    return OutcomePanelResponse(
        applied_as="recommendation_overlay",
        modifies_design=False,
        role="recommendation_overlay",
        x50_mm=_panel_target(fragmentation, TARGET_X50),
        x80_mm=_panel_target(fragmentation, TARGET_X80),
        oversize_pct=_panel_target(oversize, TARGET_OVERSIZE),
        ppv=_panel_target(vibration, TARGET_PPV),
        frequency_hz=_panel_target(vibration, TARGET_FREQUENCY),
        toe_risk=_panel_target(toe, TARGET_TOE_RISK),
        models=models,
        warnings=list(dict.fromkeys(warnings)),
    )
