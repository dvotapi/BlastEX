"""Новый проект МВ по форме ВМ.09.03 и подсказки окна проекта (TASK-018, PR 6).

Решение владельца 12.11.2026 (план PR 6, В2–В4): в окне создания вводятся
только дата и время взрыва и блоки; остальное заполняется само.

- Объект — заданный в запросе, иначе активный объект организации, иначе
  объект последнего проекта МВ организации. Наименование объекта и заказчик —
  из справочника объекта; блок и горизонт — по проекту блока (как у паспорта
  на бурение).
- Из прошлого проекта v2 того же объекта копируются только списки людей:
  роли распорядка, роли согласования с учётками, «Согласовано:».
- Отдельные поля (реквизиты, ВМ, тексты распорядка, № и дата проекта) не
  копируются: их значения по умолчанию — справочник объекта, проект блока,
  паспорт на бурение, прошлый проект, правила — считает
  `design/mass_blast_defaults.py` при каждой проверке (§14 плана PR 6).
- Не переносятся: даты и время, блоки, охраняемые объекты, посты и точки на
  плане, примечания к скважинам — место и день взрыва другие.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from api.services.cad_service import active_work_object_name, resolve_site_code
from api.services.drilling_passport_service import block_label
from cost.v2.repository import EconomicsRepository, EconomicsRepositoryError
from design.drilling_passport import floor_horizon
from design.models import BlastDesign

__all__ = ["new_project_payload", "previous_v2_project"]

# Сколько последних проектов организации просматривать в поисках прошлого проекта объекта.
PREVIOUS_LOOKUP_LIMIT = 30


def _snapshot(economics_repository: EconomicsRepository | None, organization_id: str):
    if economics_repository is None:
        return None
    try:
        return economics_repository.get_reference_snapshot(organization_id)
    except Exception:  # справочник недоступен — проект создаётся без него
        return None


def previous_v2_projects(
    repository, organization_id: str, site_code: str, *, exclude: str = "", before: str = ""
) -> list[dict[str, Any]]:
    """Прошлые проекты v2 того же объекта, от последнего созданного (до `before`, если задан), кроме `exclude`.

    Не «последний изменённый»: иначе значения по умолчанию старого черновика
    менялись бы от правок более поздних проектов, а проекты брали бы друг у друга.
    Список, а не один проект: поле, которое прошлый проект сам взял по
    умолчанию (в его payload оно пустое), ищется у проектов ещё раньше.
    """

    if not site_code:
        return []
    candidates = [
        item for item in repository.list_projects(organization_id)
        if str(item.get("site_code") or "") == site_code and item.get("id") != exclude
    ]
    found: list[dict[str, Any]] = []
    for summary in candidates[:PREVIOUS_LOOKUP_LIMIT]:
        project = repository.get_project(organization_id, summary["id"])
        if int(project.get("context_version") or 1) != 2:
            continue
        created = str(project.get("created_at") or "")
        if before and created and created >= before:
            continue
        found.append(project)
    found.sort(key=lambda project: str(project.get("created_at") or ""), reverse=True)
    return found


def previous_v2_project(
    repository, organization_id: str, site_code: str, *, exclude: str = "", before: str = ""
) -> dict[str, Any] | None:
    """Прошлый проект v2 того же объекта — последний созданный (см. `previous_v2_projects`)."""

    found = previous_v2_projects(repository, organization_id, site_code, exclude=exclude, before=before)
    return found[0] if found else None


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
    """Списки людей прошлого проекта объекта: роли распорядка и согласования (В3)."""

    previous = previous or {}
    return {
        "agreements": [dict(item) for item in (previous.get("requisites") or {}).get("agreements") or []],
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

    blocks = []
    for design in designs:
        label = block_label(design) or design.name
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
        # Реквизиты, тексты распорядка и ВМ — не копируются: их значения по умолчанию
        # (справочник, проект блока, паспорт на бурение, прошлый проект) считает
        # `design/mass_blast_defaults.py` при каждой проверке (§14 плана PR 6).
        "personnel": people["personnel"],
        "requisites": {"agreements": people["agreements"]} if people["agreements"] else None,
    }
