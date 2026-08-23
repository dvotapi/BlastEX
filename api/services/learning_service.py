"""Train global priors and site adapters. Never auto-approves a design."""
from __future__ import annotations

from typing import Any

from design.models import BlastDesign
from api.exceptions import (
    DatasetNotFoundError,
    ImmutableDatasetError,
    ImmutableLearningError,
    InvalidLearningError,
    LearningIsolationError,
    LearningNotFoundError,
)
from api.schemas.calibration import AlgorithmListResponse
from api.schemas.design import BlastDesignSchema
from api.schemas.learning import (
    IsolationKeysSchema,
    LearningGlobalTrainRequest,
    LearningListResponse,
    LearningModelSchema,
    LearningPredictRequest,
    LearningPredictResponse,
    LearningProvenanceSchema,
    LearningSiteTrainRequest,
    LearningStatusRequest,
    LearningSummarySchema,
    LearningTargetPredictionSchema,
)
from api.schemas.outcomes import OutcomeModelTypeListResponse, OutcomeModelTypeSchema
from intelligence.calibration.algorithms import DEFAULT_ALGORITHM, available_algorithms
from intelligence.datasets import persistence as dataset_persistence
from intelligence.learning.isolation import CrossTenantError, IsolationError
from intelligence.learning.persistence import (
    ImmutableLearningError as StoreImmutable,
    LearningNotFoundError as StoreNotFound,
    existing_versions,
    latest_global,
    list_models,
    load_model,
    new_model_id,
    production_model,
    save_model,
    set_status,
)
from intelligence.learning.prediction import apply_model, empty_prediction, features_from_design
from intelligence.learning.training import next_model_version, train_global, train_site
from intelligence.learning.types import (
    SCOPE_GLOBAL,
    SCOPE_SITE,
    STATUS_CANDIDATE,
    listed_model_types,
    normalize_model_type,
    normalize_scope,
)


def _model_schema(model) -> LearningModelSchema:
    payload = model.to_dict()
    payload.pop("estimators", None)
    payload.pop("prior_estimators", None)
    payload.pop("training_matrix", None)
    payload["isolation"] = IsolationKeysSchema(**payload.get("isolation") or model.isolation.to_dict())
    payload["auto_approved"] = False
    return LearningModelSchema(**payload)


def _predict_schema(payload: dict[str, Any]) -> LearningPredictResponse:
    provenance = LearningProvenanceSchema(**payload.get("provenance") or {})
    predictions = {
        name: LearningTargetPredictionSchema(**item)
        for name, item in (payload.get("predictions") or {}).items()
    }
    data = dict(payload)
    data["provenance"] = provenance
    data["predictions"] = predictions
    data["isolation"] = IsolationKeysSchema(**(payload.get("isolation") or {}))
    data["modifies_design"] = False
    data["auto_approved"] = False
    data["applied_as"] = "recommendation_overlay"
    return LearningPredictResponse(**data)


def _translate_store(exc: Exception) -> Exception:
    if isinstance(exc, StoreNotFound):
        return LearningNotFoundError(str(exc))
    if isinstance(exc, StoreImmutable):
        return ImmutableLearningError(str(exc))
    if isinstance(exc, CrossTenantError):
        return LearningIsolationError(str(exc))
    if isinstance(exc, IsolationError):
        return LearningIsolationError(str(exc))
    if isinstance(exc, ValueError):
        return InvalidLearningError(str(exc))
    return exc


def list_algorithms() -> AlgorithmListResponse:
    return AlgorithmListResponse(items=available_algorithms(), default=DEFAULT_ALGORITHM)


def list_learning_types() -> OutcomeModelTypeListResponse:
    return OutcomeModelTypeListResponse(
        items=[OutcomeModelTypeSchema(**item) for item in listed_model_types()]
    )


def list_learning_models(
    team_id: str,
    *,
    model_type: str = "",
    scope: str = "",
    site_id: str = "",
) -> LearningListResponse:
    wanted_type = ""
    wanted_scope = ""
    if model_type.strip():
        try:
            wanted_type = normalize_model_type(model_type)
        except ValueError as exc:
            raise InvalidLearningError(str(exc)) from exc
    if scope.strip():
        try:
            wanted_scope = normalize_scope(scope)
        except ValueError as exc:
            raise InvalidLearningError(str(exc)) from exc
    items = list_models(team_id, model_type=wanted_type, scope=wanted_scope, site_id=site_id.strip())
    return LearningListResponse(
        items=[LearningSummarySchema(**item.__dict__) for item in items],
        auto_approved=False,
    )


def get_learning_model(team_id: str, model_id: str) -> LearningModelSchema:
    try:
        model = load_model(team_id, model_id)
    except Exception as exc:
        raise _translate_store(exc) from exc
    return _model_schema(model)


def _load_snapshots(team_id: str, dataset_ids: list[str]):
    if not dataset_ids:
        raise InvalidLearningError("Для обучения нужны dataset_id неизменяемых снимков.")
    snapshots = []
    for raw_id in dataset_ids:
        dataset_id = str(raw_id or "").strip()
        if not dataset_id:
            raise InvalidLearningError("Для обучения нужен dataset_id неизменяемого снимка.")
        try:
            snapshots.append(dataset_persistence.load_snapshot(team_id, dataset_id))
        except dataset_persistence.DatasetNotFoundError as exc:
            raise DatasetNotFoundError(dataset_id) from exc
        except dataset_persistence.ImmutableDatasetError as exc:
            raise ImmutableDatasetError(str(exc)) from exc
    return snapshots


def train_global_model(team_id: str, request: LearningGlobalTrainRequest) -> LearningModelSchema:
    snapshots = _load_snapshots(team_id, request.dataset_ids)
    try:
        model_type = normalize_model_type(request.model_type)
        model = train_global(
            snapshots,
            team_id=team_id,
            model_type=model_type,
            algorithm=request.algorithm or DEFAULT_ALGORITHM,
            model_id=new_model_id(),
            model_version=next_model_version(
                existing_versions(team_id, scope=SCOPE_GLOBAL, site_id="*", model_type=model_type)
            ),
        )
        saved = save_model(team_id, model)
    except Exception as exc:
        raise _translate_store(exc) from exc
    if saved.status != STATUS_CANDIDATE:
        raise InvalidLearningError("Новая модель должна сохраняться со статусом candidate.")
    return _model_schema(saved)


def train_site_model(team_id: str, request: LearningSiteTrainRequest) -> LearningModelSchema:
    site_id = request.site_id.strip()
    if not site_id:
        raise InvalidLearningError("Для адаптации площадки нужен site_id.")
    snapshots = _load_snapshots(team_id, request.dataset_ids)
    try:
        model_type = normalize_model_type(request.model_type)
        prior = None
        prior_id = request.prior_model_id.strip()
        if prior_id:
            prior = load_model(team_id, prior_id)
        else:
            prior = latest_global(team_id, model_type)
        model = train_site(
            snapshots,
            team_id=team_id,
            site_id=site_id,
            model_type=model_type,
            algorithm=request.algorithm or DEFAULT_ALGORITHM,
            model_id=new_model_id(),
            model_version=next_model_version(
                existing_versions(team_id, scope=SCOPE_SITE, site_id=site_id, model_type=model_type)
            ),
            prior=prior,
        )
        saved = save_model(team_id, model)
    except Exception as exc:
        raise _translate_store(exc) from exc
    if saved.status != STATUS_CANDIDATE:
        raise InvalidLearningError("Новая модель должна сохраняться со статусом candidate.")
    return _model_schema(saved)


def update_status(team_id: str, model_id: str, request: LearningStatusRequest) -> LearningModelSchema:
    try:
        model = set_status(team_id, model_id, request.status)
    except Exception as exc:
        raise _translate_store(exc) from exc
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
    raise InvalidLearningError("Для прогноза нужны признаки или паспорт БВР.")


def predict_learning(team_id: str, request: LearningPredictRequest) -> LearningPredictResponse:
    try:
        model_type = normalize_model_type(request.model_type)
        scope = normalize_scope(request.scope) if request.scope.strip() else ""
    except ValueError as exc:
        raise InvalidLearningError(str(exc)) from exc

    design = _design_from_request(request.design)
    site_id = request.site_id.strip()
    if not site_id and design is not None:
        site_id = str((request.features or {}).get("SITE", {}).get("site_id") or "")
    features = _resolve_features(features=request.features, design=design, site_id=site_id)

    model = None
    try:
        if request.model_id.strip():
            model = load_model(team_id, request.model_id.strip())
        elif request.use_production:
            wanted_scope = scope or (SCOPE_SITE if site_id else SCOPE_GLOBAL)
            model = production_model(
                team_id,
                model_type=model_type,
                scope=wanted_scope,
                site_id=site_id if wanted_scope == SCOPE_SITE else "",
            )
    except Exception as exc:
        raise _translate_store(exc) from exc

    if model is None:
        reason = "Нет выбранной модели обучения."
        if request.use_production:
            reason = f"Нет production-модели «{model_type}» для запрошенного уровня/площадки."
        payload = empty_prediction(
            model_type=model_type, team_id=team_id, site_id=site_id, scope=scope, reason=reason
        )
        return _predict_schema(payload.to_dict())

    if site_id and model.scope == SCOPE_SITE and model.site_id != site_id:
        raise LearningIsolationError("site_id запроса не совпадает с площадкой модели.")
    if model.model_type != model_type:
        raise InvalidLearningError("Тип модели не совпадает с запросом прогноза.")
    if scope and model.scope != scope:
        raise InvalidLearningError("Уровень модели не совпадает с запросом прогноза.")

    try:
        prediction = apply_model(model, features=features)
    except ValueError as exc:
        raise InvalidLearningError(str(exc)) from exc
    payload = prediction.to_dict()
    payload["modifies_design"] = False
    payload["auto_approved"] = False
    return _predict_schema(payload)
