"""Completeness and provenance checks before a blast becomes a training sample.

A closed blast is a frozen engineering record: designed geometry + execution
+ measured BlastResult. Incomplete or unprovenanced records stay out.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from design.models import (
    ROLE_EXECUTED,
    ROLE_MEASURED,
    BlastDesign,
    DataProvenance,
)

from intelligence.datasets.features import FEATURE_GROUPS
from intelligence.datasets.targets import TARGET_GROUPS, target_group_has_values

REQUIRED_FEATURE_KEYS = {
    "SITE": ("site_id", "design_id"),
    "GEOLOGY": ("domain_count",),
    "GEOMETRY": ("enabled_hole_count", "mean_depth_m"),
    "CHARGING": ("charged_hole_count",),
    "TIMING": ("system",),
    "EXECUTION": ("as_drilled_count", "as_charged_count", "as_fired_count"),
    "ENVIRONMENT": ("receptor_count",),
}

REQUIRED_TARGET_KEYS = {
    "FRAGMENTATION": ("x20_mm", "x50_mm", "x80_mm", "oversize_pct"),
    "VIBRATION": ("ppv_mm_s", "frequency_hz", "max_ppv_mm_s"),
    "BLAST": (
        "muckpile_volume_m3",
        "backbreak_max_m",
        "toe_condition",
        "leftover_height_m",
        "flyrock_max_range_m",
    ),
    "PERFORMANCE": (
        "secondary_breaking_volume_m3",
        "secondary_breaking_hours",
        "oversize_minus_designed_pct",
        "leftover_height_m",
        "fired_coverage",
    ),
    "ECONOMICS": ("total_amount_rub", "cost_per_m3"),
}


@dataclass
class SampleValidation:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    closed: bool = False
    complete_target_groups: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "closed": self.closed,
            "reasons": list(self.reasons),
            "complete_target_groups": list(self.complete_target_groups),
        }


def _provenance_ready(item: DataProvenance | None, *, expected_role: str, label: str) -> list[str]:
    if item is None:
        return [f"{label}: нет происхождения."]
    reasons: list[str] = []
    if not (item.source or item.method or item.timestamp):
        reasons.append(f"{label}: происхождение пустое (source/method/timestamp).")
    if item.role and item.role != expected_role:
        reasons.append(f"{label}: роль «{item.role}» вместо «{expected_role}».")
    return reasons


def is_closed_blast(design: BlastDesign) -> tuple[bool, list[str]]:
    """Closed = designed holes + execution records + measured BlastResult."""
    reasons: list[str] = []
    if not design.design_id:
        reasons.append("У паспорта нет design_id.")
    enabled = [hole for hole in design.holes if hole.enabled]
    if not enabled:
        reasons.append("Нет включённых проектных скважин.")
    result = design.blast_result
    if result is None:
        reasons.append("Нет записанного BlastResult.")
    else:
        if not (result.recorded_at or result.provenance.timestamp):
            reasons.append("У BlastResult нет времени записи.")
        if result.role != ROLE_MEASURED:
            reasons.append("BlastResult должен иметь role=measured.")
        reasons.extend(_provenance_ready(result.provenance, expected_role=ROLE_MEASURED, label="BlastResult"))
    has_execution = bool(design.as_drilled_holes or design.as_charged_holes or design.as_fired_holes)
    if not has_execution:
        reasons.append("Нет записей исполнения (as-drilled / as-charged / as-fired).")
    else:
        for item in design.as_drilled_holes:
            reasons.extend(_provenance_ready(item.provenance, expected_role=ROLE_EXECUTED, label="as-drilled"))
            if item.role != ROLE_EXECUTED:
                reasons.append("Запись бурения должна иметь role=executed.")
        for item in design.as_charged_holes:
            reasons.extend(_provenance_ready(item.provenance, expected_role=ROLE_EXECUTED, label="as-charged"))
            if item.role != ROLE_EXECUTED:
                reasons.append("Запись заряжания должна иметь role=executed.")
        for item in design.as_fired_holes:
            reasons.extend(_provenance_ready(item.provenance, expected_role=ROLE_EXECUTED, label="as-fired"))
            if item.role != ROLE_EXECUTED:
                reasons.append("Запись взрыва должна иметь role=executed.")
    return not reasons, reasons


def _missing_group_keys(group: dict[str, Any] | None, required: Iterable[str], label: str) -> list[str]:
    if not group:
        return [f"Нет группы {label}."]
    missing = [key for key in required if key not in group]
    if missing:
        return [f"В группе {label} нет полей: {', '.join(missing)}."]
    return []


def validate_sample(
    *,
    design: BlastDesign,
    features: dict[str, dict[str, Any]],
    targets: dict[str, dict[str, Any]],
    provenance: dict[str, Any],
    site_id: str,
) -> SampleValidation:
    """Reject a sample that is not closed, incomplete, or missing provenance."""
    closed, reasons = is_closed_blast(design)
    if site_id == "":
        reasons.append("site_id пустой.")
    if not provenance.get("source_blast_id"):
        reasons.append("В происхождении образца нет source_blast_id.")
    if not provenance.get("feature_schema_version"):
        reasons.append("В происхождении образца нет feature_schema_version.")
    if provenance.get("site_id") != site_id:
        reasons.append("site_id в происхождении не совпадает со снимком.")
    if provenance.get("source_blast_id") and provenance.get("source_blast_id") != design.design_id:
        reasons.append("source_blast_id не совпадает с design_id паспорта.")

    for name in FEATURE_GROUPS:
        reasons.extend(_missing_group_keys(features.get(name), REQUIRED_FEATURE_KEYS[name], name))
    geometry = features.get("GEOMETRY") or {}
    if int(geometry.get("enabled_hole_count") or 0) < 1:
        reasons.append("GEOMETRY: нет включённых скважин.")
    charging = features.get("CHARGING") or {}
    if charging.get("total_charge_kg") in (None, "") and int(charging.get("charged_hole_count") or 0) < 1:
        reasons.append("CHARGING: нет проектного заряда.")
    execution = features.get("EXECUTION") or {}
    if (
        int(execution.get("as_drilled_count") or 0)
        + int(execution.get("as_charged_count") or 0)
        + int(execution.get("as_fired_count") or 0)
        < 1
    ):
        reasons.append("EXECUTION: нет фактических записей.")

    for name in TARGET_GROUPS:
        reasons.extend(_missing_group_keys(targets.get(name), REQUIRED_TARGET_KEYS[name], name))

    complete_targets = [name for name in TARGET_GROUPS if target_group_has_values(targets.get(name) or {})]
    if not complete_targets:
        reasons.append("Нет ни одной заполненной целевой группы (FRAGMENTATION / VIBRATION / BLAST / PERFORMANCE / ECONOMICS).")

    unique_reasons = list(dict.fromkeys(reasons))
    return SampleValidation(
        ok=not unique_reasons,
        reasons=unique_reasons,
        closed=closed,
        complete_target_groups=complete_targets,
    )
