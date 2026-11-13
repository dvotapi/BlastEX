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
from dataclasses import dataclass, field
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
from api.services.cad_situation_service import block_situation_refs, source_situation
from api.services.situation_layers import SITUATION_CACHE, design_situation
from api.services.drilling_passport_prefill import drilling_condition, prefill, previous_of_site
from cost.v2.repository import EconomicsRepository, EconomicsRepositoryError
from design import persistence as design_persistence
from design.drilling_passport import DEFAULT_WORK_ORDER, has_errors, passport_context, warning_codes, work_order_texts
from design.drilling_passport_repository import (
    DrillingPassportConflictError,
    DrillingPassportNotFoundError,
    PostgresDrillingPassportRepository,
)
from design.mass_blast import content_sha256
from design.export_survey import (
    DWG_DISABLED_WARNING,
    STAKEOUT_EXTENSIONS,
    DwgExport,
    ascii_name,
    holes_dwg,
    holes_dxf,
    StakeoutError,
    stakeout_file,
    stakeout_issue,
    stakeout_profile,
    stakeout_snapshot,
)
from design.reporting.drill.archive import build_zip
from design.reporting.drill.coords_pdf import render_coords_pdf
from design.reporting.drill.coords_xlsx import render_coords_xlsx
from design.reporting.drill.pdf import render_passport_pdf
from design.models import BlastDesign, BlockContour


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
    # Профили файла выноса GNSS (PR 5): встроенные, справочника и профиль объекта.
    stakeout: dict[str, Any] = field(default_factory=lambda: stakeout_snapshot({}, None))
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
    if rig is not None:
        condition = drilling_condition(snapshot, rig_code, site_code)
        if not condition or not condition.get("tech_speed_m_per_h"):
            issues.append(
                _warning(
                    "drilling_norm_missing",
                    f"Нет норматива бурения станка «{rig.name or rig_code}» в «Условиях бурения»: плановое окончание "
                    "бурения не рассчитано — проверьте дату.",
                    "drilling_end",
                )
            )
    site_stakeout = str((site.payload or {}).get("stakeout_profile_code") or "") if site else ""
    stakeout_records = {
        item.code: {"name": item.name, **dict(item.payload or {})}
        for item in snapshot.active_items("stakeout_profiles")
    }
    stakeout = stakeout_snapshot(stakeout_records, site_stakeout or None)
    if site_stakeout and stakeout["default"] != site_stakeout:
        issues.append(
            _warning(
                "stakeout_profile_not_found",
                f"Профиль файла выноса «{site_stakeout}» объекта не найден в справочнике: "
                "файл для приёмника — CSV «точка, север, восток, отметка, описание».",
                "site_code",
            )
        )
    return _References(
        site=dict(site.payload) if site else None,
        rig=dict(rig.payload) if rig else None,
        profile=dict(profile.payload) if profile else None,
        profile_code=profile_code if profile else "",
        stakeout=stakeout,
        revision_id=snapshot.revision_id,
        issues=tuple(issues),
    )


def _default_site_code(economics_repository: EconomicsRepository | None, organization_id: str, snapshot) -> str:
    if economics_repository is None:
        return ""
    return resolve_site_code(snapshot, active_work_object_name(economics_repository, organization_id))


def _apply_site_profile(payload: dict[str, Any], explicit: set[str], snapshot) -> None:
    """Профиль паспорта объекта и «Порядок работ» нового паспорта (PR 6).

    Тексты порядка работ постоянны из паспорта в паспорт: берутся из профиля
    (явно заданный в запросе, иначе профиль объекта), пустое поле профиля или
    нет профиля — текст формы по умолчанию. Заданное в запросе не меняется.
    """

    code = str(payload.get("profile_code") or "")
    if "profile_code" not in explicit and not code and snapshot is not None:
        site = snapshot.item("sites", str(payload.get("site_code") or "")) if payload.get("site_code") else None
        code = str(((site.payload or {}) if site else {}).get("drill_passport_profile_code") or "")
    profile = snapshot.item("drill_passport_profiles", code) if code and snapshot is not None else None
    if "profile_code" not in explicit:
        payload["profile_code"] = code if profile is not None else ""
    texts = work_order_texts(dict(profile.payload or {}) if profile is not None else None)
    for key in DEFAULT_WORK_ORDER:
        if key not in explicit:
            payload[key] = texts[key]


# Имя контура по умолчанию (`BlockContour.name`): не номер блока.
DEFAULT_CONTOUR_NAME = BlockContour().name
_BLOCK_NUMBER = re.compile(r"^\s*блок\s*№?\s*(.+?)\s*$", re.IGNORECASE)


def _block_label(design: BlastDesign) -> str:
    """«Блок» нового паспорта: имя контура, если оно задано (не «Блок» по
    умолчанию), иначе номер из названия проекта («Блок 67» → «67»), иначе
    само название; не длиннее поля паспорта."""

    contour = (design.contour.name or "").strip()
    if contour and contour != DEFAULT_CONTOUR_NAME:
        label = contour
    else:
        name = (design.name or "").strip()
        match = _BLOCK_NUMBER.match(name)
        # Без номера в названии («Новый паспорт», «Блок») — поле пустым, а не
        # «блок № Новый паспорт» в шапке PDF.
        label = match.group(1) if match else (name if any(ch.isdigit() for ch in name) else "")
    return label[: TEXT_LIMITS["block"]]


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
    explicit = set(request.payload.model_fields_set) if request.payload is not None else set()
    snapshot = _snapshot(economics_repository, organization_id)
    if not payload["block"]:
        # Имя контура не ограничено, а блок паспорта — да: иначе черновик не
        # сохранить повторно (предел проверяется при записи).
        payload["block"] = _block_label(design)
    passports = list(repository.list_passports(organization_id, None))
    if not payload["site_code"] and "site_code" not in explicit:
        # Активный объект организации; не определился — объект последнего
        # паспорта организации (паспорта одного объекта идут подряд).
        payload["site_code"] = _default_site_code(economics_repository, organization_id, snapshot) or next(
            (str((item.get("payload") or {}).get("site_code") or "") for item in passports
             if (item.get("payload") or {}).get("site_code")),
            "",
        )
    _apply_site_profile(payload, explicit, snapshot)
    passport_date = request.passport_date or date.today().isoformat()
    # Остальные поля — справочники и прошлый паспорт того же объекта (PR 6).
    previous = previous_of_site(passports, str(payload.get("site_code") or ""))
    prefill(payload, explicit, snapshot=snapshot, design=design, previous=previous, passport_date=passport_date)
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
# Кэш слоёв ситуации — общий с проектом МВ (`situation_layers`); имя оставлено
# для тестов, которые его чистят.
_SITUATION_CACHE = SITUATION_CACHE


def _plan_situation(
    organization_id: str, design: BlastDesign, site_code: str = ""
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Ситуация TASK-013 для плана на стр. 4: версии из `contour.cad.situation`,
    без них — ситуация объекта (план карьера).

    Без ссылок база чертежей не читается. Удалённая версия или слой, не
    уместившийся в предел вершин, — предупреждение: план без них.
    """

    def log(source_id: str) -> None:
        if source_id:
            logger.exception("Ситуация %s не прочитана для плана паспорта на бурение", source_id)
        else:
            logger.exception("База чертежей недоступна для плана паспорта на бурение")

    # Только чтение: plan_geometry строит свои списки, кэш не меняется.
    layers, problems = design_situation(
        organization_id,
        block_situation_refs(get_cad_repository, organization_id, design.contour.cad, site_code)[0],
        repository_factory=lambda: get_cad_repository(),
        reader=lambda repository, org, source_id: source_situation(repository, org, source_id),
        on_error=log,
    )
    issues: list[dict[str, str]] = []
    for problem in problems:
        if problem.kind == "missing":
            issues.append(_warning("plan_situation_missing", f"Версия ситуации «{problem.title}» удалена — на плане её нет.", "plan"))
        elif problem.kind == "capped":
            issues.append(_warning(
                "plan_situation_capped",
                f"Ситуация «{problem.title}» слишком большая: на плане нет слоёв {', '.join(problem.layers[:5])}.",
                "plan",
            ))
        else:
            issues.append(_warning(
                "plan_situation_unavailable",
                f"Ситуация «{problem.title}» не прочитана (база чертежей недоступна или файл повреждён) — на плане её нет.",
                "plan",
            ))
    return layers, issues


def _context(
    passport: Mapping[str, Any], economics_repository: EconomicsRepository | None, organization_id: str
) -> dict[str, Any]:
    payload = dict(passport.get("payload") or {})
    design = _load_design(organization_id, str(passport["design_id"]))
    refs = _reference_inputs(economics_repository, organization_id, payload)
    situation, situation_issues = _plan_situation(organization_id, design, str(payload.get("site_code") or ""))
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
    context["stakeout"] = refs.stakeout
    problem = stakeout_issue(context)
    if problem:
        context["issues"].append(
            _warning("stakeout_names_invalid", f"Файл выноса для приёмника не сформируется. {problem}", "block")
        )
    context["reference_revision_id"] = refs.revision_id
    return context


def list_passports(
    repository: PostgresDrillingPassportRepository, organization_id: str, design_id: str
) -> list[dict[str, Any]]:
    """Паспорта проекта блока в организации, последний изменённый первым."""

    return list(repository.list_passports(organization_id, design_id))


def preview_pdf(
    repository: PostgresDrillingPassportRepository,
    economics_repository: EconomicsRepository | None,
    organization_id: str,
    passport_id: str,
) -> tuple[bytes, str]:
    """PDF текущего черновика с пометкой «черновик» — только предпросмотр (PR 6).

    Ревизия не выпускается; с ошибками проверки PDF не строится (422).
    """

    passport = repository.get_passport(organization_id, passport_id)
    context = _context(passport, economics_repository, organization_id)
    if has_errors(context["issues"]):
        messages = "; ".join(issue["message"] for issue in context["issues"] if issue["level"] == "error")
        raise ValueError(f"Предпросмотр недоступен: {messages}")
    return render_passport_pdf(context, draft=True), f"Паспорт на бурение {_file_stem(context)} черновик.pdf"


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

    DWG строится только при `BLASTEX_DWG_EXPORT_ENABLED`; без флага, а также
    когда его не удалось записать или сверить, отдаётся DXF с предупреждением
    (`DwgExport.warning`), имя — с расширением `.dxf`.
    """

    revision = repository.get_revision(organization_id, revision_id)
    context = revision["context"]
    number = int(revision["revision_no"])
    dxf = holes_dxf(context, revision_no=number)
    if fmt == "dwg" and config.dwg_export_enabled():
        key = (organization_id, revision_id, str(revision.get("content_sha256") or ""))
        exported = _cached_dwg(key, dxf)
    elif fmt == "dwg":
        # DWG выключен (LibreDWG 0.14 пишет R2000, который AutoCAD не открывает):
        # отдаём DXF с подсказкой.
        exported = DwgExport(dxf, "dxf", DWG_DISABLED_WARNING)
    else:
        exported = DwgExport(dxf, "dxf")
    return exported, f"Скважины {_file_stem(context)} rev{number}.{exported.format}"


STAKEOUT_MEDIA_TYPES = {"csv": "text/csv", "txt": "text/plain", "dxf": "image/vnd.dxf"}
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
STAKEOUT_MISSING_NOTE = "Файл выноса не сформирован.txt"


def _stakeout(context: Mapping[str, Any], revision_no: int, profile: str | None) -> tuple[bytes, str, str]:
    code, options = stakeout_profile(context, profile)
    data = stakeout_file(context, options)
    extension = STAKEOUT_EXTENSIONS[options["format"]]
    payload = (context.get("passport") or {}).get("payload") or {}
    # Имя тоже ASCII: файл копируют на контроллер (спека §5).
    parts = (
        ascii_name(str(payload.get("site_code") or "")),
        ascii_name(str(payload.get("block") or "")),
        ascii_name(_file_stem(context)),
        f"r{revision_no}",
        ascii_name(code),
    )
    return data, "_".join(part for part in parts if part) + f".{extension}", STAKEOUT_MEDIA_TYPES[extension]


def stakeout_export(
    repository: PostgresDrillingPassportRepository, organization_id: str, revision_id: str, profile: str | None
) -> tuple[bytes, str, str]:
    """Файл выноса для GNSS-приёмника (TASK-015, PR 5): данные, имя, тип — только из снимка.

    Профиль — из снимка ревизии; `None` — профиль объекта. Неизвестный
    профиль и повтор имён точек — `StakeoutError` (422).
    """

    revision = repository.get_revision(organization_id, revision_id)
    return _stakeout(revision["context"], int(revision["revision_no"]), profile)


def _coords(context: Mapping[str, Any], revision_no: int, fmt: Literal["pdf", "xlsx"]) -> tuple[bytes, str]:
    render = render_coords_pdf if fmt == "pdf" else render_coords_xlsx
    return render(context, revision_no=revision_no), f"Ведомость координат {_file_stem(context)} rev{revision_no}.{fmt}"


def coords_document(
    repository: PostgresDrillingPassportRepository, organization_id: str, revision_id: str, fmt: Literal["pdf", "xlsx"]
) -> tuple[bytes, str]:
    """Ведомость координат скважин (PDF по эталону v0.6 или XLSX маркшейдера) из снимка ревизии."""

    revision = repository.get_revision(organization_id, revision_id)
    return _coords(revision["context"], int(revision["revision_no"]), fmt)


def package_zip(
    repository: PostgresDrillingPassportRepository, organization_id: str, revision_id: str
) -> tuple[bytes, str]:
    """Всё вместе (спека §6): паспорт PDF, DXF скважин, файл выноса по профилю
    объекта, ведомость PDF и XLSX — те же байты, что у отдельных маршрутов."""

    revision = repository.get_revision(organization_id, revision_id)
    context = revision["context"]
    number = int(revision["revision_no"])
    stem = f"{_file_stem(context)} rev{number}"
    try:
        stakeout, stakeout_name, _ = _stakeout(context, number, None)
    except StakeoutError as exc:
        # Паспорт, чертёж и ведомость от имён точек не зависят: архив
        # выдаётся и без файла выноса — с причиной вместо него.
        stakeout_name, stakeout = STAKEOUT_MISSING_NOTE, f"{exc}\n".encode("utf-8")
    entries = [
        (f"Паспорт на бурение {stem}.pdf", render_passport_pdf(context, revision_no=number)),
        (f"Скважины {stem}.dxf", holes_dxf(context, revision_no=number)),
        (stakeout_name, stakeout),
    ]
    for kind in ("pdf", "xlsx"):
        data, name = _coords(context, number, kind)
        entries.append((name, data))
    return build_zip(entries), f"Паспорт на бурение {stem}.zip"


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
