"""Сервис паспорта на бурение: черновик, проверка, неизменяемая ревизия (TASK-015, PR 1).

Паспорт хранится только в PostgreSQL. Скважины берутся из сохранённого
`BlastDesign`, углы уступа и вылет оси — из опубликованной ревизии
справочников (объект и тип станка из payload паспорта). Расчёт — в
`design/drilling_passport.py`; здесь только сборка входов и хранение.
"""
from __future__ import annotations

import logging
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from threading import Lock
from typing import Any, Literal, Mapping

from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from api import config
from api.schemas.drilling_passport import (
    DrillingPassportCreateSchema,
    DrillingPassportPayload,
    DrillingPassportUpdateSchema,
    TEXT_LIMITS,
)
from api.services.cad_service import active_work_object_name, get_cad_repository, resolve_site_code
from api.services.cad_situation_service import source_situation
from cost.v2.repository import EconomicsRepository, EconomicsRepositoryError
from design import persistence as design_persistence
from design.drilling_passport import has_errors, passport_context, warning_codes
from design.drilling_passport_repository import (
    DrillingPassportConflictError,
    DrillingPassportNotFoundError,
    PostgresDrillingPassportRepository,
)
from design.mass_blast import content_sha256
from design.export_survey import DwgExport, holes_dwg, holes_dxf
from design.reporting.drill.pdf import render_passport_pdf
from design.models import BlastDesign
from design.spatial.cad.repository import CadSourceNotFound


logger = logging.getLogger(__name__)

# Длина колонки `drilling_passports.passport_no`.
PASSPORT_NO_MAX_LENGTH = 120


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


def _warning(code: str, message: str, path: str) -> dict[str, str]:
    return {"level": "warning", "code": code, "message": message, "path": path}


@dataclass(frozen=True)
class _References:
    """Записи справочников для паспорта; None — записи нет."""

    site: dict[str, Any] | None = None
    rig: dict[str, Any] | None = None
    profile: dict[str, Any] | None = None
    profile_code: str = ""
    revision_id: str | None = None
    issues: tuple[dict[str, str], ...] = ()


def _reference_inputs(
    economics_repository: EconomicsRepository | None, organization_id: str, payload: Mapping[str, Any]
) -> _References:
    """Объект, тип станка, профиль паспорта, ревизия справочников и предупреждения.

    Нет записи — None и предупреждение: справочник не прочитан или код из
    паспорта в нём не найден (а не «внесите величину в справочник»). Без
    профиля печатаются тексты формы по умолчанию.
    """

    site_code = str(payload.get("site_code") or "")
    rig_code = str(payload.get("rig_type_code") or "")
    profile_code = str(payload.get("profile_code") or "")
    snapshot = _snapshot(economics_repository, organization_id)
    if snapshot is None:
        return _References(issues=(
            _warning(
                "references_unavailable",
                "Справочники не прочитаны: углы α, γ и вылет e взяты только из паспорта и проекта, "
                "тексты паспорта — по умолчанию.",
                "site_code",
            ),
        ))
    site = snapshot.item("sites", site_code) if site_code else None
    rig = snapshot.item("equipment_types", rig_code) if rig_code else None
    profile = snapshot.item("drill_passport_profiles", profile_code) if profile_code else None
    issues: list[dict[str, str]] = []
    if site_code and site is None:
        issues.append(
            _warning("site_not_found", f"Объект с кодом «{site_code}» не найден в справочнике объектов.", "site_code")
        )
    if rig_code and rig is None:
        issues.append(
            _warning(
                "rig_type_not_found",
                f"Тип станка с кодом «{rig_code}» не найден в справочнике техники.",
                "rig_type_code",
            )
        )
    if profile_code and profile is None:
        issues.append(
            _warning(
                "drill_profile_not_found",
                f"Профиль паспорта «{profile_code}» не найден в справочнике: тексты мер безопасности "
                "и технологии бурения — по умолчанию.",
                "profile_code",
            )
        )
    return _References(
        site=dict(site.payload) if site else None,
        rig=dict(rig.payload) if rig else None,
        profile=dict(profile.payload) if profile else None,
        profile_code=profile_code if profile else "",
        revision_id=snapshot.revision_id,
        issues=tuple(issues),
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
        # Имя контура не ограничено, а блок паспорта — да: иначе черновик не
        # сохранить повторно (предел проверяется при записи).
        payload["block"] = (design.contour.name or design.name or "").strip()[: TEXT_LIMITS["block"]]
    if not payload["site_code"]:
        payload["site_code"] = _default_site_code(economics_repository, organization_id)
    passport_date = request.passport_date or date.today().isoformat()
    passport_no = request.passport_no or default_passport_no(payload["block"], passport_date)
    if len(passport_no) > PASSPORT_NO_MAX_LENGTH:
        raise ValueError(
            f"№ паспорта «{passport_no[:40]}…» длиннее {PASSPORT_NO_MAX_LENGTH} символов: задайте номер вручную."
        )
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


# Ситуация для плана: (организация, источник, версия) → слои и урезанные слои.
# Проверку паспорта фронт зовёт часто, а чтение и упрощение ситуации большого
# чертежа — секунды; переимпорт файла меняет `revision`, и ключ устаревает.
_SITUATION_CACHE: OrderedDict[tuple[str, str, int], tuple[list[dict[str, Any]], list[str]]] = OrderedDict()
_SITUATION_CACHE_SIZE = 8
_SITUATION_CACHE_LOCK = Lock()


def _situation_layers(repository, organization_id: str, source_id: str, revision: int):
    key = (organization_id, source_id, int(revision))
    with _SITUATION_CACHE_LOCK:
        if key in _SITUATION_CACHE:
            _SITUATION_CACHE.move_to_end(key)
            return _SITUATION_CACHE[key]
    geometry = source_situation(repository, organization_id, source_id)
    value = (
        [
            {"kind": layer.kind, "lines": [{"points": line.points, "closed": line.closed} for line in layer.lines]}
            for layer in geometry.layers
            if layer.lines
        ],
        [layer.name for layer in geometry.layers if layer.omitted],
    )
    with _SITUATION_CACHE_LOCK:
        _SITUATION_CACHE[key] = value
        while len(_SITUATION_CACHE) > _SITUATION_CACHE_SIZE:
            _SITUATION_CACHE.popitem(last=False)
    return value


def _plan_situation(organization_id: str, design: BlastDesign) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Ситуация TASK-013 для плана на стр. 4: версии из `contour.cad.situation`.

    Без ссылок база чертежей не читается. Удалённая версия или слой, не
    уместившийся в предел вершин, — предупреждение: план без них.
    """

    refs, seen = [], set()
    for ref in (design.contour.cad or {}).get("situation") or ():
        source_id = str(ref.get("source_id") or "")
        if source_id and source_id not in seen:
            seen.add(source_id)
            refs.append(ref)
    if not refs:
        return [], []
    layers: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    try:
        repository = get_cad_repository()
    except Exception:  # noqa: BLE001 — ситуация только фон плана: без неё паспорт выпускается
        logger.exception("База чертежей недоступна для плана паспорта на бурение")
        repository = None
    for ref in refs:
        title = str(ref.get("title") or ref["source_id"])
        unavailable = _warning(
            "plan_situation_unavailable",
            f"Ситуация «{title}» не прочитана (база чертежей недоступна или файл повреждён) — на плане её нет.",
            "plan",
        )
        if repository is None:
            issues.append(unavailable)
            continue
        source_id = str(ref["source_id"])
        try:
            record = repository.get_source(organization_id, source_id)
            if record is None:
                raise CadSourceNotFound(source_id)
            source_layers, capped = _situation_layers(repository, organization_id, source_id, record.revision)
        except CadSourceNotFound:
            issues.append(_warning("plan_situation_missing", f"Версия ситуации «{title}» удалена — на плане её нет.", "plan"))
            continue
        except Exception:  # noqa: BLE001 — повреждённый чертёж не должен ронять проверку паспорта
            logger.exception("Ситуация %s не прочитана для плана паспорта на бурение", source_id)
            issues.append(unavailable)
            continue
        if capped:
            issues.append(_warning(
                "plan_situation_capped",
                f"Ситуация «{title}» слишком большая: на плане нет слоёв {', '.join(capped[:5])}.",
                "plan",
            ))
        # Только чтение: plan_geometry строит свои списки, кэш не меняется.
        layers += source_layers
    return layers, issues


def _context(
    passport: Mapping[str, Any], economics_repository: EconomicsRepository | None, organization_id: str
) -> dict[str, Any]:
    payload = dict(passport.get("payload") or {})
    design = _load_design(organization_id, str(passport["design_id"]))
    refs = _reference_inputs(economics_repository, organization_id, payload)
    situation, situation_issues = _plan_situation(organization_id, design)
    context = passport_context(
        design, payload, refs.site, refs.rig, profile=refs.profile, profile_code=refs.profile_code,
        situation=situation,
    )
    context["issues"] = [*refs.issues, *context["issues"], *situation_issues]
    context["passport"] = {
        "passport_no": passport["passport_no"],
        "passport_date": passport["passport_date"],
        "payload": payload,
    }
    context["reference_revision_id"] = refs.revision_id
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
    if passport.get("status", "draft") != "draft":
        # До сравнения со снимком: иначе неизменённый паспорт обходил бы проверку.
        raise DrillingPassportConflictError("Ревизию можно выпустить только из черновика.")
    context = _context(passport, economics_repository, organization_id)
    if has_errors(context["issues"]):
        messages = "; ".join(issue["message"] for issue in context["issues"] if issue["level"] == "error")
        raise ValueError(f"Ревизию нельзя выпустить: {messages}")
    missing = [code for code in warning_codes(context["issues"]) if code not in set(acknowledged_warnings)]
    if missing:
        raise UnacknowledgedWarningsError(missing)
    digest = content_sha256(context)
    if passport.get("current_revision_id"):
        # Снимок не изменился — та же ревизия: один PDF — один номер.
        latest = repository.get_revision(organization_id, str(passport["current_revision_id"]))
        if latest.get("content_sha256") == digest:
            return latest
    return repository.create_revision(
        organization_id, actor, passport_id, expected_version, context["reference_revision_id"],
        context, digest,
    )


def passport_pdf(
    repository: PostgresDrillingPassportRepository, organization_id: str, revision_id: str
) -> tuple[bytes, str]:
    """PDF паспорта и имя файла — только из снимка ревизии, без черновика и справочников."""

    revision = repository.get_revision(organization_id, revision_id)
    context = revision["context"]
    pdf = render_passport_pdf(context, revision_no=int(revision["revision_no"]))
    return pdf, f"Паспорт на бурение {_file_stem(context)} rev{revision['revision_no']}.pdf"


def _file_stem(context: Mapping[str, Any]) -> str:
    """Номер паспорта для имени файла: без «/» и других запрещённых знаков."""

    number = str((context.get("passport") or {}).get("passport_no") or "")
    return re.sub(r'[\\/:*?"<>|]+', "-", number).strip(" .-") or "б-н"


# Готовые DWG ревизий: ревизия неизменяема, а dxf2dwg и обратная сверка —
# секунды. Ключ — организация, ревизия и хэш её снимка; откат на DXF не
# кэшируется (утилиту могут починить).
_DWG_CACHE: OrderedDict[tuple[str, str, str], DwgExport] = OrderedDict()
_DWG_CACHE_SIZE = 8
_DWG_CACHE_LOCK = Lock()


def _cached_dwg(key: tuple[str, str, str], dxf: bytes) -> DwgExport:
    with _DWG_CACHE_LOCK:
        if key in _DWG_CACHE:
            _DWG_CACHE.move_to_end(key)
            return _DWG_CACHE[key]
    exported = holes_dwg(dxf)
    if exported.format == "dwg":
        with _DWG_CACHE_LOCK:
            _DWG_CACHE[key] = exported
            while len(_DWG_CACHE) > _DWG_CACHE_SIZE:
                _DWG_CACHE.popitem(last=False)
    return exported


def holes_drawing(
    repository: PostgresDrillingPassportRepository,
    organization_id: str,
    revision_id: str,
    fmt: Literal["dxf", "dwg"],
) -> tuple[DwgExport, str]:
    """Чертёж скважин ревизии (TASK-015, PR 4) и имя файла — только из снимка.

    DWG, который не удалось записать или сверить, отдаётся как DXF с
    предупреждением (`DwgExport.warning`), имя — с расширением `.dxf`.
    """

    revision = repository.get_revision(organization_id, revision_id)
    context = revision["context"]
    number = int(revision["revision_no"])
    dxf = holes_dxf(context, revision_no=number)
    if fmt == "dwg":
        key = (organization_id, revision_id, str(revision.get("content_sha256") or ""))
        exported = _cached_dwg(key, dxf)
    else:
        exported = DwgExport(dxf, "dxf")
    return exported, f"Скважины {_file_stem(context)} rev{number}.{exported.format}"


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
