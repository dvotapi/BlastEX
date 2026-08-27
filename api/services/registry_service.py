"""Human-gated registry promotions. Never trains. Never auto-deploys."""
from __future__ import annotations

from api.exceptions import (
    ImmutableRegistryError,
    InvalidRegistryError,
    RegistryIsolationError,
    RegistryNotFoundError,
)
from api.schemas.registry import (
    RegistryFamilySchema,
    RegistryLineageSchema,
    RegistryListResponse,
    RegistryMetaResponse,
    RegistryPromoteRequest,
    RegistryRecordSchema,
    RegistryStatusSchema,
    RegistryTransitionSchema,
)
from intelligence.learning.isolation import CrossTenantError, IsolationError
from intelligence.registry.catalog import RegistryNotFoundError as StoreNotFound
from intelligence.registry.lifecycle import InvalidPromotionError
from intelligence.registry.persistence import (
    ImmutableRegistryError as StoreImmutable,
    get_record,
    list_records,
    promote,
)
from intelligence.registry.types import listed_families, listed_statuses, normalize_family, normalize_status


def _record_schema(record) -> RegistryRecordSchema:
    payload = record.to_dict()
    payload["lineage"] = RegistryLineageSchema(**payload.get("lineage") or {})
    payload["transitions"] = [
        RegistryTransitionSchema(**item) for item in payload.get("transitions") or []
    ]
    payload["auto_deployed"] = False
    return RegistryRecordSchema(**payload)


def _translate_store(exc: Exception) -> Exception:
    if isinstance(exc, StoreNotFound):
        return RegistryNotFoundError(str(exc))
    if isinstance(exc, StoreImmutable):
        return ImmutableRegistryError(str(exc))
    if isinstance(exc, CrossTenantError):
        return RegistryIsolationError(str(exc))
    if isinstance(exc, IsolationError):
        return RegistryIsolationError(str(exc))
    if isinstance(exc, InvalidPromotionError):
        return InvalidRegistryError(str(exc))
    if isinstance(exc, ValueError):
        return InvalidRegistryError(str(exc))
    return exc


def catalog_meta() -> RegistryMetaResponse:
    return RegistryMetaResponse(
        families=[RegistryFamilySchema(**item) for item in listed_families()],
        statuses=[RegistryStatusSchema(**item) for item in listed_statuses()],
        auto_deployed=False,
    )


def list_registry_models(
    team_id: str,
    *,
    family: str = "",
    status: str = "",
    site_id: str = "",
) -> RegistryListResponse:
    wanted_family = ""
    wanted_status = ""
    if family.strip():
        try:
            wanted_family = normalize_family(family)
        except ValueError as exc:
            raise InvalidRegistryError(str(exc)) from exc
    if status.strip():
        try:
            wanted_status = normalize_status(status)
        except ValueError as exc:
            raise InvalidRegistryError(str(exc)) from exc
    try:
        items = list_records(
            team_id, family=wanted_family, status=wanted_status, site_id=site_id.strip()
        )
    except Exception as exc:
        raise _translate_store(exc) from exc
    return RegistryListResponse(
        items=[_record_schema(item) for item in items],
        auto_deployed=False,
    )


def get_registry_model(team_id: str, family: str, model_id: str) -> RegistryRecordSchema:
    try:
        record = get_record(team_id, family, model_id)
    except Exception as exc:
        raise _translate_store(exc) from exc
    return _record_schema(record)


def promote_registry_model(
    team_id: str,
    family: str,
    model_id: str,
    request: RegistryPromoteRequest,
    *,
    actor: str,
) -> RegistryRecordSchema:
    try:
        record = promote(
            team_id,
            family,
            model_id,
            to_status=request.to_status,
            actor=actor,
            confirm=request.confirm,
            note=request.note,
        )
    except Exception as exc:
        raise _translate_store(exc) from exc
    if record.auto_deployed:
        raise InvalidRegistryError("Реестр не допускает автодеплой модели.")
    return _record_schema(record)
