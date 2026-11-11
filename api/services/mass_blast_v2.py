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
from api.services.cad_situation_service import source_situation
from api.services.situation_layers import design_situation, situation_refs
from cost.v2.repository import EconomicsRepository
from design import persistence as design_persistence
from design.mass_blast import ProjectBlock
from design.mass_blast_context import BlockSource, ContextReferences, build_document_context_v2
from design.models import BlastDesign

__all__ = ["context_v2", "load_block_designs", "V2_PAYLOAD_KEYS"]

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


def _situation(organization_id: str, designs: Sequence[BlastDesign]) -> tuple[list[dict[str, Any]], list[dict[str, str]], bool]:
    refs: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for design in designs:
        for ref in situation_refs(design.contour.cad):
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


def context_v2(
    organization_id: str,
    payload: Mapping[str, Any],
    blocks: Sequence[ProjectBlock],
    economics_repository: EconomicsRepository,
    reference_revision_id: str | None,
) -> tuple[dict[str, Any], list[str]]:
    """Контекст v2 и сообщения об изменившихся источниках блоков."""

    designs, stale = load_block_designs(organization_id, blocks)
    snapshot = economics_repository.get_reference_snapshot(organization_id, reference_revision_id or None)
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
    layers, situation_issues, has_refs = _situation(organization_id, designs)
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
