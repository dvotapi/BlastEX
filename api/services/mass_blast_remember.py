"""«Запомнить для объекта» (TASK-018, PR 6, §14, В8).

Поле объекта, заполненное в проекте МВ или в слое дня взрыва, пишется в запись
«Проект МВ: реквизиты объекта» новой ревизией справочника — тем же путём, что
публикация из раздела «Справочники» (общие проверки и ограничения журнала).
Какое поле проекта в какое поле справочника — знает только сервер
(`design.mass_blast_defaults.SITE_FIELDS`): окно полей справочника не знает.
Писать может только администратор или редактор справочников.
"""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Mapping, Sequence

from cost.v2.models import ReferenceItem
from cost.v2.repository import EconomicsRepository
from cost.v2.references import has_validation_errors
from design.mass_blast_defaults import SITE_FIELDS, remember_values

__all__ = ["remember_for_site", "rememberable"]

SECTION = "mass_blast_sites"


def rememberable(site: Mapping[str, Any] | None, *, layer_kind: str = "") -> dict[str, Any]:
    """Поля, которые можно запомнить: путь проекта (или поле слоя) → значение в справочнике (None — пусто)."""

    site = site or {}
    result: dict[str, Any] = {}
    for path, key in SITE_FIELDS.items():
        kind, _, name = path.partition(":") if ":" in path else ("", "", path)
        if (kind or "") != layer_kind:
            continue
        value = site.get(key)
        result[name] = None if value in (None, "") else value
    return result


def _record_code(site_code: str, taken: set[str]) -> str:
    base = "MBS_" + re.sub(r"[^A-Za-z0-9_]", "_", site_code).upper()
    code, number = base, 2
    while code in taken:
        code, number = f"{base}_{number}", number + 1
    return code


def remember_for_site(
    economics_repository: EconomicsRepository,
    organization_id: str,
    actor: str,
    project: Mapping[str, Any],
    paths: Sequence[str],
    *,
    layer: Mapping[str, Any] | None = None,
    issues_of=None,
) -> dict[str, Any]:
    """Записать поля объекта в справочник; `issues_of(sections)` — проверка публикации."""

    if not paths:
        raise ValueError("Не выбрано ни одного поля, которое нужно запомнить.")
    values = remember_values(
        project, paths, layer_kind=str((layer or {}).get("kind") or ""), layer_payload=(layer or {}).get("payload"),
    )
    site_code = str(project.get("site_code") or "")
    snapshot = economics_repository.get_reference_snapshot(organization_id)
    sections: dict[str, list[ReferenceItem]] = {name: list(items) for name, items in snapshot.sections.items()}
    records = sections.setdefault(SECTION, [])
    index = next(
        (i for i, item in enumerate(records) if item.is_active and str(item.payload.get("site_code") or "") == site_code),
        None,
    )
    if index is None:
        site = snapshot.item("sites", site_code)
        record = ReferenceItem(
            code=_record_code(site_code, {item.code for item in records}),
            name=(site.name if site is not None else "") or str(project.get("object_name") or site_code),
            payload={"site_code": site_code, **values},
            source="mass_blast_project",
        )
        records.append(record)
    else:
        current = records[index]
        records[index] = replace(current, payload={**current.payload, **values}, revision=current.revision + 1)
    if issues_of is not None:
        issues = issues_of(sections)
        if has_validation_errors(issues):
            messages = "; ".join(str(getattr(issue, "message", issue)) for issue in issues if getattr(issue, "level", "") == "error")
            raise ValueError(f"Справочник не принял значения: {messages}")
    name = str(project.get("name") or "")
    published = economics_repository.publish_references(
        organization_id, actor, snapshot.revision_id, sections,
        comment=f"Из проекта МВ «{name}»: запомнено для объекта {site_code}",
    )
    return {"revision_id": published.revision_id, "fields": sorted(values)}
