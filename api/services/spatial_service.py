"""Hole-level spatial ML. Predicted overlay only — never writes the passport."""
from __future__ import annotations

from typing import Any

from design.models import BlastDesign
from api.exceptions import (
    DatasetNotFoundError,
    ImmutableDatasetError,
    ImmutableSpatialError,
    InvalidSpatialError,
    SpatialIsolationError,
    SpatialNotFoundError,
)
from api.schemas.calibration import AlgorithmListResponse
from api.schemas.spatial import (
    SpatialHoleSchema,
    SpatialListResponse,
    SpatialMetaResponse,
    SpatialMetricSchema,
    SpatialModelSchema,
    SpatialNeighborhoodSchema,
    SpatialPredictRequest,
    SpatialPredictResponse,
    SpatialProvenanceSchema,
    SpatialStatusRequest,
    SpatialSummarySchema,
    SpatialTrainRequest,
)
from intelligence.calibration.algorithms import DEFAULT_ALGORITHM, available_algorithms
from intelligence.datasets import persistence as dataset_persistence
from intelligence.learning.isolation import CrossTenantError, IsolationError
from intelligence.spatial.persistence import (
    ImmutableSpatialError as StoreImmutable,
    InvalidSpatialError as StoreInvalid,
    SpatialNotFoundError as StoreNotFound,
    existing_versions,
    list_models,
    load_model,
    new_model_id,
    production_model,
    save_model,
    set_status,
)
from intelligence.spatial.prediction import apply_model, empty_overlay
from intelligence.spatial.training import next_model_version, train_from_snapshot
from intelligence.spatial.types import (
    APPLIED_AS_OVERLAY,
    DATA_ROLES,
    ROLE_PREDICTED,
    listed_map_metrics,
    listed_metrics,
)


def _model_schema(model) -> SpatialModelSchema:
    payload = model.to_dict()
    payload.pop("estimators", None)
    return SpatialModelSchema(**payload)


def _predict_schema(payload: dict[str, Any]) -> SpatialPredictResponse:
    holes = [SpatialHoleSchema(**item) for item in payload.get("holes") or []]
    neighborhoods = [SpatialNeighborhoodSchema(**item) for item in payload.get("neighborhoods") or []]
    provenance = SpatialProvenanceSchema(**(payload.get("provenance") or {}))
    data = dict(payload)
    data["holes"] = holes
    data["neighborhoods"] = neighborhoods
    data["provenance"] = provenance
    data["modifies_design"] = False
    data["applied_as"] = APPLIED_AS_OVERLAY
    data["role"] = ROLE_PREDICTED
    data["data_roles"] = dict(data.get("data_roles") or DATA_ROLES)
    return SpatialPredictResponse(**data)


def _translate(exc: Exception) -> Exception:
    if isinstance(exc, StoreNotFound):
        return SpatialNotFoundError(str(exc))
    if isinstance(exc, StoreImmutable):
        return ImmutableSpatialError(str(exc))
    if isinstance(exc, StoreInvalid):
        return InvalidSpatialError(str(exc))
    if isinstance(exc, CrossTenantError):
        return SpatialIsolationError(str(exc))
    if isinstance(exc, IsolationError):
        return SpatialIsolationError(str(exc))
    if isinstance(exc, dataset_persistence.DatasetNotFoundError):
        return DatasetNotFoundError(str(exc))
    if isinstance(exc, dataset_persistence.ImmutableDatasetError):
        return ImmutableDatasetError(str(exc))
    if isinstance(exc, ValueError):
        return InvalidSpatialError(str(exc))
    return exc


def catalog_meta() -> SpatialMetaResponse:
    return SpatialMetaResponse(
        metrics=[SpatialMetricSchema(**item) for item in listed_metrics()],
        map_metrics=[SpatialMetricSchema(**item) for item in listed_map_metrics()],
        data_roles=dict(DATA_ROLES),
        applied_as=APPLIED_AS_OVERLAY,
        modifies_design=False,
        role=ROLE_PREDICTED,
    )


def list_algorithms() -> AlgorithmListResponse:
    return AlgorithmListResponse(items=available_algorithms(), default=DEFAULT_ALGORITHM)


def list_spatial_models(team_id: str, *, site_id: str = "") -> SpatialListResponse:
    try:
        items = list_models(team_id, site_id=site_id.strip())
    except Exception as exc:
        raise _translate(exc) from exc
    return SpatialListResponse(
        items=[SpatialSummarySchema(**item.__dict__) for item in items],
        modifies_design=False,
    )


def get_spatial_model(team_id: str, model_id: str) -> SpatialModelSchema:
    try:
        model = load_model(team_id, model_id)
    except Exception as exc:
        raise _translate(exc) from exc
    return _model_schema(model)


def train_spatial(team_id: str, request: SpatialTrainRequest) -> SpatialModelSchema:
    try:
        snapshot = dataset_persistence.load_snapshot(team_id, request.dataset_id.strip())
        if not snapshot.immutable:
            raise InvalidSpatialError("Обучение разрешено только по неизменяемому снимку датасета.")
        site_id = request.site_id.strip() or snapshot.site_id
        model = train_from_snapshot(
            snapshot,
            team_id=team_id,
            algorithm=request.algorithm or DEFAULT_ALGORITHM,
            model_id=new_model_id(),
            model_version=next_model_version(existing_versions(team_id, site_id)),
            site_id=site_id,
            neighbor_k=int(request.neighbor_k or 4),
        )
        saved = save_model(team_id, model)
    except Exception as exc:
        raise _translate(exc) from exc
    if saved.status != "candidate":
        raise InvalidSpatialError("Только что обученная пространственная модель должна остаться candidate.")
    return _model_schema(saved)


def update_status(team_id: str, model_id: str, request: SpatialStatusRequest) -> SpatialModelSchema:
    try:
        model = set_status(team_id, model_id, request.status)
    except Exception as exc:
        raise _translate(exc) from exc
    return _model_schema(model)


def predict_spatial(team_id: str, request: SpatialPredictRequest) -> SpatialPredictResponse:
    design = BlastDesign.from_dict(request.design.model_dump())
    before = (
        [hole.to_dict() for hole in design.holes],
        [load.to_dict() for load in design.loads],
    )
    site_id = request.site_id.strip()
    model = None
    try:
        if request.model_id.strip():
            model = load_model(team_id, request.model_id.strip())
        elif request.use_production:
            if not site_id:
                raise InvalidSpatialError("Для производственной модели нужен site_id.")
            model = production_model(team_id, site_id)
    except Exception as exc:
        raise _translate(exc) from exc
    if model is None and request.model_id.strip():
        raise SpatialNotFoundError(f"Пространственная модель «{request.model_id}» не найдена.")
    if model is None and request.use_production:
        payload = empty_overlay(
            site_id=site_id,
            reason=f"Нет production-модели скважинного уровня для площадки «{site_id}».",
        )
        return _predict_schema(payload.to_dict())
    if model is not None and site_id and model.site_id and model.site_id != site_id:
        raise InvalidSpatialError("site_id запроса не совпадает с площадкой модели.")
    try:
        overlay = apply_model(
            design,
            model=model,
            site_id=site_id or (model.site_id if model else ""),
            block=request.block,
            neighbor_k=request.neighbor_k,
        )
    except Exception as exc:
        raise _translate(exc) from exc
    after = (
        [hole.to_dict() for hole in design.holes],
        [load.to_dict() for load in design.loads],
    )
    if after != before:
        raise InvalidSpatialError("Пространственный прогноз не должен менять проектные скважины или заряды.")
    if overlay.modifies_design:
        raise InvalidSpatialError("Слой predicted не может изменять проект.")
    return _predict_schema(overlay.to_dict())
