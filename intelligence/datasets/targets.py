"""Target groups extracted from a recorded BlastResult.

Targets stay measured. Predicted / designed values are copied only as
comparison context, never as the training label.
"""
from __future__ import annotations

from typing import Any

from design.blast_result import BlastResult
from design.models import ROLE_DESIGNED, ROLE_MEASURED, ROLE_PREDICTED

TARGET_GROUPS = (
    "FRAGMENTATION",
    "VIBRATION",
    "BLAST",
    "PERFORMANCE",
    "ECONOMICS",
)


def _has_number(*values: Any) -> bool:
    return any(value is not None and value != "" for value in values)


def extract_fragmentation_targets(result: BlastResult | None) -> dict[str, Any]:
    measured = result.fragmentation if result else None
    predicted = result.basis.predicted_fragmentation if result and result.basis else None
    designed = result.basis.designed_fragmentation if result and result.basis else None
    return {
        "group": "FRAGMENTATION",
        "role": ROLE_MEASURED,
        "x20_mm": measured.x20_mm if measured else None,
        "x50_mm": measured.x50_mm if measured else None,
        "x80_mm": measured.x80_mm if measured else None,
        "oversize_pct": measured.oversize_pct if measured else None,
        "source": measured.source if measured else "",
        "method": measured.method if measured else "",
        "predicted_x50_mm": predicted.x50_mm if predicted else None,
        "predicted_oversize_pct": predicted.oversize_pct if predicted else None,
        "designed_lump_size_mm": designed.lump_size_mm if designed else None,
        "designed_max_oversize_pct": designed.max_oversize_pct if designed else None,
        "predicted_role": ROLE_PREDICTED if predicted else "",
        "designed_role": ROLE_DESIGNED if designed else "",
    }


def extract_vibration_targets(result: BlastResult | None) -> dict[str, Any]:
    measured = result.vibration if result else None
    measurements = list(measured.measurements) if measured else []
    ppv_values = [item.ppv_mm_s for item in measurements if item.ppv_mm_s is not None]
    if measured and measured.ppv_mm_s is not None:
        ppv_values.append(measured.ppv_mm_s)
    freq_values = [item.frequency_hz for item in measurements if item.frequency_hz is not None]
    if measured and measured.frequency_hz is not None:
        freq_values.append(measured.frequency_hz)
    predicted = result.basis.predicted_vibration if result and result.basis else []
    predicted_ppv = max((item.ppv_mm_s for item in predicted), default=None)
    return {
        "group": "VIBRATION",
        "role": ROLE_MEASURED,
        "ppv_mm_s": measured.ppv_mm_s if measured else None,
        "frequency_hz": measured.frequency_hz if measured else None,
        "receptor_id": measured.receptor_id if measured else "",
        "measurement_count": len(measurements),
        "max_ppv_mm_s": max(ppv_values) if ppv_values else None,
        "max_frequency_hz": max(freq_values) if freq_values else None,
        "source": measured.source if measured else "",
        "method": measured.method if measured else "",
        "predicted_max_ppv_mm_s": predicted_ppv,
        "predicted_role": ROLE_PREDICTED if predicted else "",
    }


def extract_blast_targets(result: BlastResult | None) -> dict[str, Any]:
    muck = result.muckpile if result else None
    backbreak = result.backbreak if result else None
    toe = result.toe_condition if result else None
    flyrock = result.flyrock_observations if result else []
    max_range = max((item.max_range_m for item in flyrock if item.max_range_m is not None), default=None)
    count = sum((item.count or 0) for item in flyrock)
    return {
        "group": "BLAST",
        "role": ROLE_MEASURED,
        "muckpile_length_m": muck.length_m if muck else None,
        "muckpile_width_m": muck.width_m if muck else None,
        "muckpile_height_m": muck.height_m if muck else None,
        "muckpile_volume_m3": muck.volume_m3 if muck else None,
        "muckpile_throw_m": muck.throw_m if muck else None,
        "backbreak_max_m": backbreak.max_m if backbreak else None,
        "backbreak_mean_m": backbreak.mean_m if backbreak else None,
        "crest_loss_m": backbreak.crest_loss_m if backbreak else None,
        "toe_condition": toe.condition if toe else "",
        "leftover_height_m": toe.leftover_height_m if toe else None,
        "flyrock_max_range_m": max_range,
        "flyrock_count": count if flyrock else None,
    }


def extract_performance_targets(result: BlastResult | None, *, fired_coverage: float | None = None) -> dict[str, Any]:
    secondary = result.secondary_breaking if result else None
    frag = result.fragmentation if result else None
    designed = result.basis.designed_fragmentation if result and result.basis else None
    oversize_gap = None
    if frag and frag.oversize_pct is not None and designed and designed.max_oversize_pct is not None:
        oversize_gap = round(float(frag.oversize_pct) - float(designed.max_oversize_pct), 3)
    return {
        "group": "PERFORMANCE",
        "role": ROLE_MEASURED,
        "secondary_breaking_volume_m3": secondary.volume_m3 if secondary else None,
        "secondary_breaking_hours": secondary.hours if secondary else None,
        "secondary_breaking_method": secondary.method if secondary else "",
        "oversize_minus_designed_pct": oversize_gap,
        "leftover_height_m": result.toe_condition.leftover_height_m if result and result.toe_condition else None,
        "fired_coverage": fired_coverage,
    }


def extract_economics_targets(result: BlastResult | None) -> dict[str, Any]:
    actual = result.cost_actual if result else None
    planned = result.basis.planned_cost if result and result.basis else None
    return {
        "group": "ECONOMICS",
        "role": ROLE_MEASURED,
        "total_amount_rub": actual.total_amount_rub if actual else None,
        "cost_per_m3": actual.cost_per_m3 if actual else None,
        "variable_total_rub": actual.variable_total_rub if actual else None,
        "labor_total_rub": actual.labor_total_rub if actual else None,
        "fixed_total_rub": actual.fixed_total_rub if actual else None,
        "secondary_breaking_rub": actual.secondary_breaking_rub if actual else None,
        "planned_total_amount_rub": planned.total_amount_rub if planned else None,
        "planned_cost_per_m3": planned.cost_per_m3 if planned else None,
        "planned_role": ROLE_DESIGNED if planned else "",
    }


def extract_targets(
    result: BlastResult | None,
    *,
    fired_coverage: float | None = None,
) -> dict[str, dict[str, Any]]:
    return {
        "FRAGMENTATION": extract_fragmentation_targets(result),
        "VIBRATION": extract_vibration_targets(result),
        "BLAST": extract_blast_targets(result),
        "PERFORMANCE": extract_performance_targets(result, fired_coverage=fired_coverage),
        "ECONOMICS": extract_economics_targets(result),
    }


def target_group_has_values(group: dict[str, Any]) -> bool:
    skip = {"group", "role", "source", "method", "receptor_id", "predicted_role", "designed_role", "planned_role", "secondary_breaking_method", "toe_condition"}
    return _has_number(*(value for key, value in group.items() if key not in skip and not str(key).endswith("_role")))
