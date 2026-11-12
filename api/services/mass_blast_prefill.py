"""Новый проект МВ по форме ВМ.09.03 и подсказки окна проекта (TASK-018, PR 6).

Решение владельца 12.11.2026 (план PR 6, В2–В4): в окне создания вводятся
только дата и время взрыва и блоки; остальное заполняется само.

- Объект — заданный в запросе, иначе активный объект организации, иначе
  объект последнего проекта МВ организации. Наименование объекта и заказчик —
  из справочника объекта; блок и горизонт — по проекту блока (как у паспорта
  на бурение).
- Из прошлого проекта v2 того же объекта переходят люди (составил, проверил,
  подписанты, согласования, маркшейдер, персонал, роли согласования с
  учётками) и постоянные тексты распорядка (`SCHEDULE_FROM_PREVIOUS`).
- Не переносятся: № и дата проекта, даты и время, блоки, охраняемые объекты,
  посты и точки на плане, примечания к скважинам — место и день взрыва другие.
- Реквизиты из записи «Проект МВ: реквизиты объекта» в проект не копируются:
  контекст сам берёт их из справочника, когда поле проекта пустое.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from api.services.cad_service import active_work_object_name, resolve_site_code
from api.services.drilling_passport_prefill import _customer
from api.services.drilling_passport_service import _block_label
from cost.v2.repository import EconomicsRepository, EconomicsRepositoryError
from design.drilling_passport import floor_horizon
from design.models import BlastDesign

__all__ = [
    "REQUISITES_FROM_PREVIOUS",
    "SCHEDULE_FROM_PREVIOUS",
    "new_project_payload",
    "previous_v2_project",
]

# Реквизиты, которые переходят из прошлого проекта того же объекта (люди и стороны).
REQUISITES_FROM_PREVIOUS = (
    "tp_basis", "made_by", "checked_by", "customer_name", "contractor_name",
    "customer_approver", "contractor_approver", "agreements", "surveyor_name", "drilled_by",
)
# Постоянные тексты распорядка (В3): место станции, укрытия и сбора, сирена,
# транспорт ВМ, средства очистки, порядок заряжания и монтажа, мероприятия.
SCHEDULE_FROM_PREVIOUS = (
    "charging_order", "network_order", "station", "shelter", "gather", "exit_route",
    "siren", "measures", "transport", "cleaning",
)
# Сколько последних проектов организации просматривать в поисках прошлого проекта объекта.
PREVIOUS_LOOKUP_LIMIT = 30


def _snapshot(economics_repository: EconomicsRepository | None, organization_id: str):
    if economics_repository is None:
        return None
    try:
        return economics_repository.get_reference_snapshot(organization_id)
    except Exception:  # справочник недоступен — проект создаётся без него
        return None


def previous_v2_project(
    repository, organization_id: str, site_code: str, *, exclude: str = ""
) -> dict[str, Any] | None:
    """Последний изменённый проект v2 того же объекта (кроме `exclude`)."""

    if not site_code:
        return None
    candidates = [
        item for item in repository.list_projects(organization_id)
        if str(item.get("site_code") or "") == site_code and item.get("id") != exclude
    ]
    for summary in candidates[:PREVIOUS_LOOKUP_LIMIT]:
        project = repository.get_project(organization_id, summary["id"])
        if int(project.get("context_version") or 1) == 2:
            return project
    return None


def _site_code(
    requested: str,
    economics_repository: EconomicsRepository | None,
    organization_id: str,
    snapshot,
    projects: Iterable[Mapping[str, Any]],
) -> str:
    if requested:
        return requested
    if economics_repository is not None and snapshot is not None:
        try:
            code = resolve_site_code(snapshot, active_work_object_name(economics_repository, organization_id))
        except EconomicsRepositoryError:
            code = ""
        if code:
            return code
    return next((str(item.get("site_code") or "") for item in projects if item.get("site_code")), "")


def _people(previous: Mapping[str, Any] | None) -> dict[str, Any]:
    previous = previous or {}
    requisites = {
        key: value for key, value in (previous.get("requisites") or {}).items()
        if key in REQUISITES_FROM_PREVIOUS and value not in (None, "", [], {})
    }
    schedule = {
        key: value for key, value in (previous.get("schedule") or {}).items()
        if key in SCHEDULE_FROM_PREVIOUS and value
    }
    return {
        "requisites": requisites,
        "schedule": schedule,
        "personnel": [dict(item) for item in previous.get("personnel") or []],
        "responsibilities": [dict(item) for item in previous.get("responsibilities") or []],
    }


def new_project_payload(
    repository,
    economics_repository: EconomicsRepository | None,
    organization_id: str,
    designs: list[BlastDesign],
    *,
    blast_date: str,
    blast_time: str,
    site_code: str = "",
) -> dict[str, Any]:
    """Payload нового проекта v2 (`MassBlastProjectInputSchema`) по проектам блоков."""

    if not designs:
        raise ValueError("Выберите хотя бы один блок проекта.")
    snapshot = _snapshot(economics_repository, organization_id)
    projects = list(repository.list_projects(organization_id))
    code = _site_code(site_code, economics_repository, organization_id, snapshot, projects)
    if not code:
        raise ValueError(
            "Не определён объект проекта: выберите активный объект работ (или заведите объект в справочнике)."
        )
    site_item = snapshot.item("sites", code) if snapshot is not None else None
    object_name = str(site_item.name or "") if site_item is not None else ""
    previous = previous_v2_project(repository, organization_id, code)
    people = _people(previous)
    object_name = object_name or str((previous or {}).get("object_name") or "") or code
    customer = _customer(snapshot, dict(site_item.payload or {})) if site_item is not None else ""
    requisites = dict(people["requisites"])
    if customer and not requisites.get("customer_name"):
        requisites["customer_name"] = customer

    blocks = []
    for design in designs:
        label = _block_label(design) or design.name
        blocks.append({"design_id": design.design_id, "code": label[:120], "horizon": floor_horizon(design)})
    labels = ", ".join(block["code"] for block in blocks if block["code"])
    name = f"Массовый взрыв — блок {labels}" if len(blocks) == 1 else f"Массовый взрыв — блоки {labels}"

    return {
        "name": name[:300],
        "site_code": code,
        "object_name": object_name[:300],
        "customer_code": str((dict(site_item.payload or {}) if site_item is not None else {}).get("customer_code") or ""),
        "blast_date": blast_date,
        "blast_time": blast_time,
        "document_profile_code": str((previous or {}).get("document_profile_code") or "STANDARD"),
        "blocks": blocks,
        "responsibilities": people["responsibilities"],
        "safety_plan": {},
        "charging_schedule": [],
        "signal_plan": dict((previous or {}).get("signal_plan") or {}),
        "guard_posts": [],
        "notifications": [],
        "context_version": 2,
        "requisites": requisites,
        "schedule": people["schedule"],
        "personnel": people["personnel"],
    }
