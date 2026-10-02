"""Baseline кусковатости текущей базой — для снимка датасета и калибровки.

Калибровка учится на разнице «замер − baseline» и потом накладывается на
прогноз текущей модели, поэтому baseline считается той же моделью, что и
прогноз сегодня, а не берётся из прогноза, сохранённого при взрыве: тот мог
быть посчитан старой формулой. Сохранённый прогноз остаётся в строке снимка
рядом как есть.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from design.models import BlastDesign
from simulation.fragmentation.base import settings_from_snapshot
from simulation.fragmentation.cunningham import KuzRamSettings
from simulation.fragmentation.engine import FRAGMENTATION_MODELS, predict_design, resolve_model
from simulation.fragmentation.models import MODEL_KUZRAM, FragmentationInputs, PredictedFragmentation
from simulation.fragmentation.regions import (
    DEFAULT_EXPLOSIVE_DENSITY_T_M3,
    DEFAULT_EXPLOSIVE_ENERGY_MJ_KG,
    DEFAULT_ROCK_DENSITY_T_M3,
    DEFAULT_ROCK_FISSURING,
    DEFAULT_ROCK_UCS_MPA,
    ExplosiveSpec,
    RockSpec,
)

BASELINE_MODEL = MODEL_KUZRAM


def stored_prediction(design: BlastDesign) -> PredictedFragmentation | None:
    """Прогноз, сохранённый в результате взрыва; None — его нет."""
    result = design.blast_result
    basis = getattr(result, "basis", None) if result is not None else None
    return getattr(basis, "predicted_fragmentation", None) if basis is not None else None


def baseline_settings(
    design: BlastDesign,
    fallback_settings: KuzRamSettings | None = None,
    fallback_source: Mapping[str, Any] | None = None,
) -> tuple[KuzRamSettings | None, dict[str, Any]]:
    """Снимок настроек сохранённого прогноза, иначе запасные (объект работ или умолчания)."""
    stored = stored_prediction(design)
    snapshot = stored.provenance.settings if stored is not None else {}
    if snapshot:
        return settings_from_snapshot(snapshot)
    return fallback_settings, dict(fallback_source or {})


def _positive(value: float, default: float) -> float:
    """Нулевая или отрицательная величина сохранённого прогноза — умолчание."""
    return value if value > 0 else default


def _specs(design: BlastDesign, inputs: FragmentationInputs) -> dict[str, Any]:
    """Порода и ВВ из входных величин сохранённого прогноза — то, что видел инженер."""
    kwargs: dict[str, Any] = {
        "default_rock": RockSpec(
            name=inputs.rock_name or design.rock_name or "порода",
            density_t_m3=_positive(inputs.rock_density_t_m3, DEFAULT_ROCK_DENSITY_T_M3),
            ucs_mpa=_positive(inputs.rock_ucs_mpa, DEFAULT_ROCK_UCS_MPA),
            fissuring_ff=_positive(inputs.rock_fissuring, DEFAULT_ROCK_FISSURING),
        ),
        "default_explosive": ExplosiveSpec(
            name=inputs.explosive_name or design.explosive_key or "ВВ",
            density_t_m3=_positive(inputs.explosive_density_t_m3, DEFAULT_EXPLOSIVE_DENSITY_T_M3),
            power_mj_kg=_positive(inputs.explosive_energy_mj_kg, DEFAULT_EXPLOSIVE_ENERGY_MJ_KG),
        ),
    }
    if inputs.lump_size_mm > 0:
        kwargs["lump_size_mm"] = inputs.lump_size_mm
    return kwargs


def fragmentation_baseline(
    design: BlastDesign,
    *,
    model: str = BASELINE_MODEL,
    fallback_settings: KuzRamSettings | None = None,
    fallback_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Baseline x50 и негабарита моделью model по паспорту взрыва.

    Не посчиталось — значения None и причина в baseline_warnings: один
    неполный взрыв не должен ронять сборку снимка.
    """
    model_id = resolve_model(model)
    out: dict[str, Any] = {
        "baseline_x50_mm": None,
        "baseline_oversize_pct": None,
        "baseline_model": model_id,
        "baseline_model_version": str(FRAGMENTATION_MODELS[model_id]["version"]),
        "baseline_settings": {},
        "baseline_warnings": [],
    }
    warnings: list[str] = []
    stored = stored_prediction(design)
    kwargs: dict[str, Any] = {}
    if stored is not None and stored.provenance.inputs:
        kwargs = _specs(design, FragmentationInputs.from_dict(stored.provenance.inputs))
    elif stored is not None:
        warnings.append("В сохранённом прогнозе нет входных величин: порода и ВВ для baseline — умолчания.")
    else:
        warnings.append("Сохранённого прогноза нет: порода и ВВ для baseline — умолчания.")
    settings, source = baseline_settings(design, fallback_settings, fallback_source)
    try:
        payload = predict_design(
            design,
            model=model_id,
            hole_oversize_coeff=(design.charge_rules or {}).get("hole_oversize_coeff"),
            settings=settings,
            settings_source=source,
            **kwargs,
        )
    except Exception as exc:  # noqa: BLE001 — снимок не должен падать из-за одного взрыва
        warnings.append(f"Baseline кусковатости не посчитан: {exc}")
        out["baseline_warnings"] = warnings
        return out
    site = (payload.get("site") or {}).get("prediction") or {}
    out["baseline_x50_mm"] = site.get("x50_mm")
    out["baseline_oversize_pct"] = site.get("oversize_pct")
    out["baseline_settings"] = dict(payload.get("settings") or {})
    out["baseline_warnings"] = warnings + [str(item) for item in payload.get("warnings") or []]
    return out
