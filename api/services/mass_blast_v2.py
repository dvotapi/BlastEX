"""Сборка входов документного контекста v2 проекта МВ (TASK-018, PR 2).

Читает то, что чистому `design.mass_blast_context` не положено: проекты
блоков (`design.persistence`), справочник той ревизии, на которой выпускается
проект (`reference_revision_id`), и ситуацию карьера TASK-013. Расчёт и
проверки — в `design/`.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Sequence

from api.services.cad_service import get_cad_repository
from api.services.cad_situation_service import block_situation_refs, source_situation
from api.services.situation_layers import design_situation
from cost.v2.repository import EconomicsRepository
from design import persistence as design_persistence
from design.mass_blast import ProjectBlock
from design.mass_blast_context import BlockSource, ContextReferences, build_document_context_v2
from design.mass_blast_defaults import DefaultsInputs, fill_empty, project_defaults
from design.reporting.brand import ORGANIZATION
from design.models import BlastDesign

__all__ = ["context_v2", "defaults_v2", "load_block_designs", "V2_PAYLOAD_KEYS"]

logger = logging.getLogger(__name__)

# Ключи payload, которые есть только у проекта v2: у проекта v1 они не хранятся.
V2_PAYLOAD_KEYS = (
    "context_version",
    "requisites",
    "explosives",
    "schedule",
    "personnel",
    "protected_objects",
    "safety_overrides",
    "layout_points",
)


def load_block_designs(organization_id: str, blocks: Sequence[ProjectBlock]) -> tuple[list[BlastDesign], list[str]]:
    """Проекты блоков и сообщения о блоках, проект которых изменился после снимка."""

    designs: list[BlastDesign] = []
    stale: list[str] = []
    for block in blocks:
        try:
            design = design_persistence.load_design(organization_id, block.design_id)
        except design_persistence.DesignNotFoundError as exc:
            raise ValueError(f"Источник блока {block.design_id} больше недоступен. Обновите черновик.") from exc
        if design.designed_sha256 != block.design_sha256:
            stale.append(
                f"Источник блока «{block.code or block.design_id}» изменился после добавления в проект. "
                "Вернитесь в черновик, обновите технический снимок и создайте новую ревизию."
            )
        designs.append(design)
    return designs, stale


def _site_record(snapshot: Any, section: str, site_code: str) -> Mapping[str, Any] | None:
    for item in snapshot.active_items(section):
        if str(item.payload.get("site_code") or "") == site_code:
            return dict(item.payload)
    return None


def _rock(snapshot: Any, rock_name: str) -> Mapping[str, Any] | None:
    wanted = (rock_name or "").strip().casefold()
    if not wanted:
        return None
    for item in snapshot.active_items("rocks"):
        if item.name.strip().casefold() == wanted:
            return dict(item.payload)
    return None


def _situation(
    organization_id: str, designs: Sequence[BlastDesign], site_code: str = ""
) -> tuple[list[dict[str, Any]], list[dict[str, str]], bool]:
    """Ситуация проекта МВ: ссылки блоков, у блока без ссылок — ситуация объекта (план карьера)."""

    refs: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    site_refs: dict = {}
    for design in designs:
        block_refs, _ = block_situation_refs(
            get_cad_repository, organization_id, design.contour.cad, site_code, site_refs=site_refs
        )
        for ref in block_refs:
            if ref["source_id"] not in seen:
                seen.add(str(ref["source_id"]))
                refs.append(ref)

    def log(source_id: str) -> None:
        logger.exception("Ситуация %s не прочитана для охраняемых объектов проекта МВ", source_id or "—")

    layers, problems = design_situation(
        organization_id,
        refs,
        repository_factory=lambda: get_cad_repository(),
        reader=lambda repository, org, source_id: source_situation(repository, org, source_id),
        on_error=log,
    )
    issues: list[dict[str, str]] = []
    for problem in problems:
        if problem.kind == "missing":
            message = f"Версия ситуации «{problem.title}» удалена: её охраняемые объекты не учтены."
            code = "situation_source_missing"
        elif problem.kind == "capped":
            message = f"Ситуация «{problem.title}» слишком большая: не учтены слои {', '.join(problem.layers[:5])}."
            code = "situation_capped"
        else:
            message = f"Ситуация «{problem.title}» не прочитана: её охраняемые объекты не учтены."
            code = "situation_unavailable"
        issues.append({"level": "warning", "code": code, "message": message, "path": "protected_objects"})
    return layers, issues, bool(refs)


def _drill_passports(organization_id: str, designs: Sequence[BlastDesign]) -> list[dict[str, Any] | None]:
    """Последний изменённый паспорт на бурение каждого блока (его payload) или None."""

    try:
        from api.services.drilling_passport_service import get_drilling_passport_repository

        repository = get_drilling_passport_repository()
        result: list[dict[str, Any] | None] = []
        for design in designs:
            passports = list(repository.list_passports(organization_id, design.design_id))
            result.append(dict(passports[0].get("payload") or {}) if passports else None)
        return result
    except Exception:  # noqa: BLE001 — паспорт даёт только умолчания: без него проект считается
        logger.warning("Паспорта на бурение блоков проекта МВ не прочитаны", exc_info=True)
        return [None for _ in designs]


def _customer_name(snapshot: Any, site_code: str) -> str:
    from api.services.drilling_passport_prefill import _customer

    item = snapshot.item("sites", site_code) if site_code else None
    return _customer(snapshot, dict(item.payload or {})) if item is not None else ""


def defaults_v2(
    organization_id: str,
    payload: Mapping[str, Any],
    designs: Sequence[BlastDesign],
    snapshot: Any,
    *,
    previous: Sequence[Mapping[str, Any]] = (),
    created_on: str = "",
    author: str = "",
) -> dict[str, dict[str, Any]]:
    """Значения по умолчанию полей проекта (В1–В5): справочник объекта, проект блока,
    паспорт на бурение, прошлый проект объекта, правила."""

    site_code = str(payload.get("site_code") or "")
    inputs = DefaultsInputs(
        designs=list(designs),
        site=_site_record(snapshot, "mass_blast_sites", site_code) or {},
        customer_name=_customer_name(snapshot, site_code),
        drill_passports=_drill_passports(organization_id, designs),
        previous=previous,
        organization=ORGANIZATION,
        created_on=created_on,
    )
    defaults = project_defaults(payload, inputs)
    # «Составил» без источника — тот, кто создал проект (В4): ФИО учётки, без должности.
    if author and "requisites.made_by.name" not in defaults:
        defaults["requisites.made_by.name"] = {"value": author, "source": "RULE"}
    return defaults


def context_v2(
    organization_id: str,
    payload: Mapping[str, Any],
    blocks: Sequence[ProjectBlock],
    economics_repository: EconomicsRepository,
    reference_revision_id: str | None,
    *,
    previous: Sequence[Mapping[str, Any]] = (),
    created_on: str = "",
    author: str = "",
    defaults_out: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Контекст v2 и сообщения об изменившихся источниках блоков.

    Пустые поля проекта заполняются значениями по умолчанию (§14 плана PR 6):
    документы печатают то же, что окно показывает в полях. Сами значения —
    в `defaults_out` (для окна).
    """

    designs, stale = load_block_designs(organization_id, blocks)
    snapshot = economics_repository.get_reference_snapshot(organization_id, reference_revision_id or None)
    defaults = defaults_v2(
        organization_id, payload, designs, snapshot, previous=previous, created_on=created_on, author=author,
    )
    if defaults_out is not None:
        defaults_out.update(defaults)
    payload = fill_empty(payload, defaults)
    site_code = str(payload.get("site_code") or "")
    site_safety = _site_record(snapshot, "blast_safety", site_code)
    site = _site_record(snapshot, "mass_blast_sites", site_code)
    issues: list[dict[str, str]] = []
    profile = None
    profile_code = str((site or {}).get("profile_code") or "")
    if profile_code:
        item = snapshot.item("mass_blast_profiles", profile_code)
        if item is None or not item.is_active:
            issues.append(
                {
                    "level": "warning",
                    "code": "mass_blast_profile_missing",
                    "message": f"Профиль документов {profile_code} не найден: тексты распорядка — по форме ВМ.09.03.",
                    "path": "requisites",
                }
            )
        else:
            profile = dict(item.payload)
    if site is None:
        issues.append(
            {
                "level": "warning",
                "code": "mass_blast_site_missing",
                "message": "У объекта нет записи «Проект МВ: реквизиты объекта»: ТП, q по ТП и подписанты — только из проекта.",
                "path": "requisites",
            }
        )
    materials = list(snapshot.active_items("materials"))
    sources = [
        BlockSource(design=design, site_safety=site_safety, rock=_rock(snapshot, design.rock_name), materials=materials)
        for design in designs
    ]
    layers, situation_issues, has_refs = _situation(organization_id, designs, site_code)
    references = ContextReferences(
        site=site,
        profile=profile,
        situation_layers=layers,
        situation_issues=situation_issues,
        has_situation_refs=has_refs,
        issues=issues,
    )
    context = build_document_context_v2(payload, blocks, sources, references)
    context["project"]["reference_revision_id"] = snapshot.revision_id
    return context, stale
