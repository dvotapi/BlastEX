"""Предметная модель проекта массового взрыва.

Модуль намеренно не пересчитывает сетку, заряд или тайминг. Он строит
воспроизводимый документный контекст из уже рассчитанного :class:`BlastDesign`
и фиксирует происхождение каждого технического значения.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Literal

from design.analysis import charge_per_delay
from design.geometry import block_volume
from design.lifecycle import designed_sha256
from design.models import BlastDesign, HoleLoad, is_explosive_deck_kind
from design.timing import resolve_network


MASS_BLAST_FORMULA_VERSION = "mass-blast-v1"
PROJECT_STATUSES = ("draft", "in_review", "approved", "executed", "closed")
FIELD_SOURCES = ("DESIGN", "TECHNICAL_PASSPORT", "REFERENCE", "CALCULATED", "MANUAL_OVERRIDE")


def canonical_json(value: Any) -> str:
    """Stable JSON representation used in immutable revision hashes."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def content_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ValidationIssue:
    level: Literal["error", "warning"]
    code: str
    message: str
    path: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"level": self.level, "code": self.code, "message": self.message, "path": self.path}


@dataclass(frozen=True)
class ProjectBlock:
    design_id: str
    design_revision: int
    design_sha256: str
    technical_passport_id: str | None
    code: str
    horizon: str
    object_name: str
    snapshot: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "design_id": self.design_id,
            "design_revision": self.design_revision,
            "design_sha256": self.design_sha256,
            "technical_passport_id": self.technical_passport_id,
            "code": self.code,
            "horizon": self.horizon,
            "object_name": self.object_name,
            "snapshot": self.snapshot,
        }


def _load_by_hole(design: BlastDesign) -> dict[str, HoleLoad]:
    return {item.hole_id: item for item in design.loads}


def _deck_mass(load: HoleLoad) -> float:
    return sum(deck.mass_kg for deck in load.decks if is_explosive_deck_kind(deck.kind))


def _stemming_length(load: HoleLoad) -> float:
    return sum(max(0.0, deck.to_m - deck.from_m) for deck in load.decks if deck.kind == "stemming")


def block_from_design(
    design: BlastDesign,
    *,
    code: str = "",
    horizon: str = "",
    technical_passport_id: str | None = None,
) -> ProjectBlock:
    """Freeze the technical source for one block without mutating it."""

    enabled_holes = [hole for hole in design.holes if hole.enabled]
    loads = _load_by_hole(design)
    hole_rows: list[dict[str, Any]] = []
    for hole in enabled_holes:
        load = loads.get(hole.id)
        primer_items = list(load.primer_items) if load else []
        charge_kg = _deck_mass(load) if load else 0.0
        hole_rows.append(
            {
                "hole_id": hole.id,
                "row": hole.row,
                "col": hole.col,
                "kind": hole.kind,
                "diameter_mm": round(hole.diameter_mm, 3),
                "collar": hole.collar.to_dict(),
                "toe": hole.toe.to_dict(),
                "depth_m": round(hole.length_m, 3),
                "subdrill_m": round(hole.subdrill_m, 3),
                "bench_height_m": round(hole.bench_height_m, 3),
                "watered": bool(hole.water_intervals),
                "charge_kg": round(charge_kg, 3),
                "charge_product": next((deck.product or deck.explosive_key for deck in (load.decks if load else []) if is_explosive_deck_kind(deck.kind)), design.explosive_key),
                "stemming_m": round(_stemming_length(load), 3) if load else 0.0,
                "primer_count": len(primer_items) if primer_items else len(load.primers) if load else 0,
                "primer_products": sorted({item.product for item in primer_items if item.product}),
                "source": "DESIGN",
            }
        )

    volume = block_volume(design.contour, design.surfaces)
    total_charge = sum(row["charge_kg"] for row in hole_rows)
    drilling_m = sum(row["depth_m"] for row in hole_rows)
    primer_count = sum(int(row["primer_count"]) for row in hole_rows)
    network = resolve_network(design.network, enabled_holes, design.loads)
    mic = charge_per_delay(network.times_ms, design.loads, events=network.events)
    snapshot = {
        "formula_version": MASS_BLAST_FORMULA_VERSION,
        "design_name": design.name,
        "explosive_key": design.explosive_key,
        "contour": design.contour.to_dict(),
        "holes": hole_rows,
        "network": design.network.to_dict(),
        "totals": {
            "hole_count": len(hole_rows),
            "block_volume_m3": round(volume, 3),
            "drilling_m": round(drilling_m, 3),
            "explosive_mass_kg": round(total_charge, 3),
            "specific_q_kg_m3": round(total_charge / volume, 6) if volume > 0 else 0.0,
            "primer_count": primer_count,
            "surface_connector_count": len(design.network.connectors),
            "starter_count": len(design.network.starters),
            "max_charge_per_delay_kg": round(float(mic.get("mic_kg", 0.0)), 3),
        },
        "lineage": {
            "technical": "DESIGN",
            "formula_version": MASS_BLAST_FORMULA_VERSION,
        },
    }
    return ProjectBlock(
        design_id=design.design_id,
        design_revision=design.revision,
        design_sha256=design.designed_sha256 or designed_sha256(design),
        technical_passport_id=technical_passport_id,
        code=code or design.contour.name or design.name,
        horizon=horizon,
        object_name=design.name,
        snapshot=snapshot,
    )


def aggregate_blocks(blocks: Iterable[ProjectBlock]) -> dict[str, Any]:
    rows = list(blocks)
    totals = {
        "block_count": len(rows),
        "hole_count": 0,
        "block_volume_m3": 0.0,
        "drilling_m": 0.0,
        "explosive_mass_kg": 0.0,
        "primer_count": 0,
        "surface_connector_count": 0,
        "starter_count": 0,
        "max_charge_per_delay_kg": 0.0,
    }
    for block in rows:
        source = block.snapshot.get("totals", {})
        for key in ("hole_count", "primer_count", "surface_connector_count", "starter_count"):
            totals[key] += int(source.get(key, 0) or 0)
        for key in ("block_volume_m3", "drilling_m", "explosive_mass_kg"):
            totals[key] += float(source.get(key, 0) or 0)
        totals["max_charge_per_delay_kg"] = max(
            totals["max_charge_per_delay_kg"], float(source.get("max_charge_per_delay_kg", 0) or 0)
        )
    totals["specific_q_kg_m3"] = (
        totals["explosive_mass_kg"] / totals["block_volume_m3"] if totals["block_volume_m3"] else 0.0
    )
    for key, value in list(totals.items()):
        if isinstance(value, float):
            totals[key] = round(value, 6)
    return totals


def build_document_context(payload: dict[str, Any], blocks: Iterable[ProjectBlock]) -> dict[str, Any]:
    """Create the single source passed to preview, PDF and XLSX renderers."""

    materialized = list(blocks)
    return {
        "document_context_version": 1,
        "formula_version": MASS_BLAST_FORMULA_VERSION,
        "project": {
            "name": str(payload.get("name", "")),
            "site_code": str(payload.get("site_code", "")),
            "object_name": str(payload.get("object_name", "")),
            "customer_code": str(payload.get("customer_code", "")),
            "blast_date": str(payload.get("blast_date", "")),
            "blast_time": str(payload.get("blast_time", "")),
            "document_profile_code": str(payload.get("document_profile_code", "STANDARD")),
            "reference_revision_id": str(payload.get("reference_revision_id", "")),
        },
        "blocks": [block.to_dict() for block in materialized],
        "totals": aggregate_blocks(materialized),
        "responsibilities": list(payload.get("responsibilities") or []),
        "safety_plan": dict(payload.get("safety_plan") or {}),
        "charging_schedule": list(payload.get("charging_schedule") or []),
        "signal_plan": dict(payload.get("signal_plan") or {}),
        "guard_posts": list(payload.get("guard_posts") or []),
        "notifications": list(payload.get("notifications") or []),
        "attachments": list(payload.get("attachments") or []),
    }


def validate_project_context(context: dict[str, Any], *, require_attachments: bool = False) -> list[ValidationIssue]:
    """Validate release readiness; warnings never silently become approvals."""

    project = context.get("project", {})
    issues: list[ValidationIssue] = []
    for field, label in (("name", "Наименование проекта"), ("site_code", "Объект работ"), ("object_name", "Наименование объекта"), ("blast_date", "Дата взрыва")):
        if not str(project.get(field, "")).strip():
            issues.append(ValidationIssue("error", "required", f"Заполните поле «{label}».", f"project.{field}"))
    blast_date = str(project.get("blast_date", ""))
    if blast_date:
        try:
            date.fromisoformat(blast_date)
        except ValueError:
            issues.append(ValidationIssue("error", "date", "Дата взрыва должна быть в формате ГГГГ-ММ-ДД.", "project.blast_date"))

    blocks = list(context.get("blocks") or [])
    if not blocks:
        issues.append(ValidationIssue("error", "blocks_required", "Добавьте хотя бы один технический блок.", "blocks"))
    seen_holes: set[str] = set()
    for index, block in enumerate(blocks):
        if not block.get("design_id") or not block.get("design_sha256"):
            issues.append(ValidationIssue("error", "design_source", "Для блока отсутствует неизменяемый источник BlastDesign.", f"blocks[{index}]"))
        snapshot = block.get("snapshot") or {}
        holes = snapshot.get("holes") or []
        if not holes:
            issues.append(ValidationIssue("error", "holes_required", "В блоке нет активных скважин.", f"blocks[{index}].snapshot.holes"))
        for hole in holes:
            key = f"{block.get('design_id', index)}:{hole.get('hole_id', '')}"
            if key in seen_holes:
                issues.append(ValidationIssue("error", "duplicate_hole", "Скважина повторяется в составе массового взрыва.", f"blocks[{index}]"))
            seen_holes.add(key)

    roles = {str(item.get("role_code", "")).strip() for item in context.get("responsibilities") or []}
    for code, label in (("blast_manager", "ответственный руководитель взрывных работ"), ("explosives_supervisor", "ответственный за хранение/выдачу ВМ")):
        if code not in roles:
            issues.append(ValidationIssue("error", "responsibility_required", f"Назначьте: {label}.", "responsibilities"))

    safety = context.get("safety_plan") or {}
    if float(safety.get("danger_zone_radius_m", 0) or 0) <= 0:
        issues.append(ValidationIssue("error", "danger_zone", "Укажите радиус опасной зоны, м.", "safety_plan.danger_zone_radius_m"))
    if not str((context.get("signal_plan") or {}).get("profile_code", "")).strip():
        issues.append(ValidationIssue("error", "signal_profile", "Выберите профиль сигналов.", "signal_plan.profile_code"))
    if not context.get("guard_posts"):
        issues.append(ValidationIssue("error", "guard_posts", "Добавьте минимум один пост охраны.", "guard_posts"))
    if not context.get("notifications"):
        issues.append(ValidationIssue("warning", "notification", "Не указан получатель уведомления.", "notifications"))
    if require_attachments and not context.get("attachments"):
        issues.append(ValidationIssue("error", "attachments", "Для выбранного профиля требуется графическое приложение.", "attachments"))

    totals = context.get("totals") or {}
    if float(totals.get("block_volume_m3", 0) or 0) <= 0:
        issues.append(ValidationIssue("error", "volume", "Объём взрываемой горной массы должен быть больше нуля.", "totals.block_volume_m3"))
    if float(totals.get("explosive_mass_kg", 0) or 0) <= 0:
        issues.append(ValidationIssue("warning", "explosive_mass", "Масса ВМ равна нулю: проверьте заряжание источника.", "totals.explosive_mass_kg"))
    return issues


def has_blocking_issues(issues: Iterable[ValidationIssue]) -> bool:
    return any(item.level == "error" for item in issues)
