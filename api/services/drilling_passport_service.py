"""Сервис паспорта на бурение: черновик, проверка, неизменяемая ревизия (TASK-015, PR 1).

Паспорт хранится только в PostgreSQL. Скважины берутся из сохранённого
`BlastDesign`, углы уступа и вылет оси — из опубликованной ревизии
справочников (объект и тип станка из payload паспорта). Расчёт — в
`design/drilling_passport.py`; здесь только сборка входов и хранение.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Any, Mapping

from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from api import config
from api.schemas.drilling_passport import (
    DrillingPassportCreateSchema,
    DrillingPassportPayload,
    DrillingPassportUpdateSchema,
)
from api.services.cad_service import active_work_object_name, resolve_site_code
from cost.v2.repository import EconomicsRepository, EconomicsRepositoryError
from design import persistence as design_persistence
from design.drilling_passport import has_errors, passport_context, warning_codes
from design.drilling_passport_repository import (
    DrillingPassportConflictError,
    DrillingPassportNotFoundError,
    PostgresDrillingPassportRepository,
)
from design.mass_blast import content_sha256
from design.models import BlastDesign


class UnacknowledgedWarningsError(RuntimeError):
    """Предупреждения проверки не отмечены «просмотрено»."""

    def __init__(self, codes: list[str]) -> None:
        super().__init__("Отметьте предупреждения проверки как просмотренные: " + ", ".join(codes))
        self.codes = codes


@lru_cache(maxsize=4)
def _postgres_repository(database_url: str) -> PostgresDrillingPassportRepository:
    return PostgresDrillingPassportRepository(database_url)


def get_drilling_passport_repository() -> PostgresDrillingPassportRepository:
    return _postgres_repository(config.database_url())


def _load_design(organization_id: str, design_id: str) -> BlastDesign:
    try:
        return design_persistence.load_design(organization_id, design_id)
    except design_persistence.DesignNotFoundError as exc:
        raise DrillingPassportNotFoundError(f"Проект блока {design_id} не найден в организации.") from exc


def _snapshot(economics_repository: EconomicsRepository | None, organization_id: str):
    if economics_repository is None:
        return None
    try:
        return economics_repository.get_reference_snapshot(organization_id)
    except (EconomicsRepositoryError, SQLAlchemyError):
        return None


def _reference_inputs(
    economics_repository: EconomicsRepository | None, organization_id: str, payload: Mapping[str, Any]
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None]:
    """Запись объекта, запись типа станка и ревизия справочников; нет — None."""

    snapshot = _snapshot(economics_repository, organization_id)
    if snapshot is None:
        return None, None, None
    site = snapshot.item("sites", str(payload.get("site_code") or ""))
    rig = snapshot.item("equipment_types", str(payload.get("rig_type_code") or ""))
    return (
        dict(site.payload) if site else None,
        dict(rig.payload) if rig else None,
        snapshot.revision_id,
    )


def _default_site_code(economics_repository: EconomicsRepository | None, organization_id: str) -> str:
    if economics_repository is None:
        return ""
    snapshot = _snapshot(economics_repository, organization_id)
    return resolve_site_code(snapshot, active_work_object_name(economics_repository, organization_id))


def default_passport_no(block: str, passport_date: str) -> str:
    """№ паспорта по умолчанию: «{блок}-{гг}/Б»."""

    return f"{block}-{passport_date[2:4]}/Б"


def create_passport(
    repository: PostgresDrillingPassportRepository,
    economics_repository: EconomicsRepository | None,
    organization_id: str,
    actor: str,
    request: DrillingPassportCreateSchema,
) -> dict[str, Any]:
    design = _load_design(organization_id, request.design_id)
    payload = (request.payload or DrillingPassportPayload()).model_dump()
    if not payload["block"]:
        payload["block"] = design.contour.name or design.name
    if not payload["site_code"]:
        payload["site_code"] = _default_site_code(economics_repository, organization_id)
    passport_date = request.passport_date or date.today().isoformat()
    passport_no = request.passport_no or default_passport_no(payload["block"], passport_date)
    return repository.create_passport(organization_id, actor, design.design_id, passport_no, passport_date, payload)


def update_passport(
    repository: PostgresDrillingPassportRepository,
    organization_id: str,
    actor: str,
    passport_id: str,
    request: DrillingPassportUpdateSchema,
) -> dict[str, Any]:
    return repository.update_passport(
        organization_id, actor, passport_id, request.passport_no, request.passport_date,
        request.payload.model_dump(), request.expected_version,
    )


def _context(
    passport: Mapping[str, Any], economics_repository: EconomicsRepository | None, organization_id: str
) -> dict[str, Any]:
    payload = dict(passport.get("payload") or {})
    design = _load_design(organization_id, str(passport["design_id"]))
    site, rig, reference_revision_id = _reference_inputs(economics_repository, organization_id, payload)
    context = passport_context(design, payload, site, rig)
    context["passport"] = {
        "passport_no": passport["passport_no"],
        "passport_date": passport["passport_date"],
        "payload": payload,
    }
    context["reference_revision_id"] = reference_revision_id
    return context


def validate_passport(
    repository: PostgresDrillingPassportRepository,
    economics_repository: EconomicsRepository | None,
    organization_id: str,
    passport_id: str,
) -> dict[str, Any]:
    context = _context(repository.get_passport(organization_id, passport_id), economics_repository, organization_id)
    return {
        "valid": not has_errors(context["issues"]),
        "issues": context["issues"],
        "summary": context["summary"],
        "first_row_check": context["first_row_check"],
        "inputs": context["inputs"],
        "provenance": context["provenance"],
    }


def create_revision(
    repository: PostgresDrillingPassportRepository,
    economics_repository: EconomicsRepository | None,
    organization_id: str,
    actor: str,
    passport_id: str,
    expected_version: int,
    acknowledged_warnings: list[str],
) -> dict[str, Any]:
    passport = repository.get_passport(organization_id, passport_id)
    if passport["version"] != expected_version:
        raise DrillingPassportConflictError("Паспорт изменён другим пользователем. Обновите данные перед выпуском ревизии.")
    context = _context(passport, economics_repository, organization_id)
    if has_errors(context["issues"]):
        messages = "; ".join(issue["message"] for issue in context["issues"] if issue["level"] == "error")
        raise ValueError(f"Ревизию нельзя выпустить: {messages}")
    missing = [code for code in warning_codes(context["issues"]) if code not in set(acknowledged_warnings)]
    if missing:
        raise UnacknowledgedWarningsError(missing)
    return repository.create_revision(
        organization_id, actor, passport_id, expected_version, context["reference_revision_id"],
        context, content_sha256(context),
    )


def repository_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DrillingPassportNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, UnacknowledgedWarningsError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "unacknowledged_warnings": exc.codes},
        )
    if isinstance(exc, DrillingPassportConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Паспорта на бурение временно недоступны: {exc}",
    )
