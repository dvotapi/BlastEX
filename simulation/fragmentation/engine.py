"""Прогноз кусковатости по проекту: реестр моделей и расчёт по регионам влияния.

Три модели (kuznetsov, kuzram, swebrec) считают на общей базе Каннингема
(simulation/fragmentation/base.py) и различаются только кривой. Прежние
формулы доступны под именами *_legacy.
"""
from __future__ import annotations

from typing import Any, Callable

from design.models import BlastDesign
from simulation.fragmentation import kuznetsov as kuznetsov_model
from simulation.fragmentation import kuzram as kuzram_model
from simulation.fragmentation import swebrec as swebrec_model
from simulation.fragmentation.cunningham import KuzRamSettings
from simulation.fragmentation.legacy import kuznetsov as kuznetsov_legacy
from simulation.fragmentation.legacy import kuzram as kuzram_legacy
from simulation.fragmentation.legacy import swebrec as swebrec_legacy
from simulation.fragmentation.maps import fragmentation_maps
from simulation.fragmentation.models import (
    LEGACY_MODEL_SUFFIX,
    MODEL_KUZNETSOV,
    MODEL_KUZRAM,
    MODEL_SWEBREC,
    ROLE_MEASURED,
    ROLE_PREDICTED,
    Calibration,
    DesignedFragmentationTarget,
    FragmentationInputs,
    MeasuredFragmentation,
    PredictedFragmentation,
)
from simulation.fragmentation.regions import (
    DEFAULT_EXPLOSIVE_DENSITY_T_M3,
    DEFAULT_EXPLOSIVE_ENERGY_MJ_KG,
    DEFAULT_ROCK_DENSITY_T_M3,
    DEFAULT_ROCK_FISSURING,
    DEFAULT_ROCK_UCS_MPA,
    ExplosiveSpec,
    InfluenceRegion,
    RockSpec,
    collect_regions,
)

PredictFn = Callable[[FragmentationInputs, Calibration | None, KuzRamSettings | None], PredictedFragmentation]
LegacyPredictFn = Callable[[FragmentationInputs, Calibration | None], PredictedFragmentation]


def _ignoring_settings(predict: LegacyPredictFn) -> PredictFn:
    """Старые модели настроек Каннингема не знают и считают ровно как до PR 2."""

    def run(
        inputs: FragmentationInputs,
        calibration: Calibration | None,
        settings: KuzRamSettings | None,
    ) -> PredictedFragmentation:
        return predict(inputs, calibration)

    return run


# (модуль, подпись, распределение, предиктор, старая ли модель). Версию и
# идентификатор реестр читает из модуля — тот же источник, что у provenance.
_MODELS = (
    (kuznetsov_model, "Кузнецов", "rosin_rammler", kuznetsov_model.predict_kuznetsov, False),
    (kuzram_model, "Kuz-Ram", "rosin_rammler", kuzram_model.predict_kuzram, False),
    (swebrec_model, "Swebrec", "swebrec", swebrec_model.predict_swebrec, False),
    (kuznetsov_legacy, "Кузнецов (старая)", "rosin_rammler", _ignoring_settings(kuznetsov_legacy.predict_kuznetsov), True),
    (kuzram_legacy, "Kuz-Ram (старая)", "rosin_rammler", _ignoring_settings(kuzram_legacy.predict_kuzram), True),
    (swebrec_legacy, "Swebrec (старая)", "swebrec", _ignoring_settings(swebrec_legacy.predict_swebrec), True),
)

FRAGMENTATION_MODELS: dict[str, dict[str, Any]] = {
    module.MODEL_ID: {
        "id": module.MODEL_ID,
        "version": module.MODEL_VERSION,
        "label": label,
        "distribution": distribution,
        "legacy": legacy,
    }
    for module, label, distribution, _predict, legacy in _MODELS
}

_PREDICTORS: dict[str, PredictFn] = {module.MODEL_ID: predict for module, _l, _d, predict, _legacy in _MODELS}

_ALIASES = {
    "kuz": MODEL_KUZNETSOV,
    "kuznetcov": MODEL_KUZNETSOV,
    "kuznetsov": MODEL_KUZNETSOV,
    "kuzram": MODEL_KUZRAM,
    "kuz_ram": MODEL_KUZRAM,
    "swebrec": MODEL_SWEBREC,
    "swebeck": MODEL_SWEBREC,
}


def list_models() -> list[dict[str, Any]]:
    return [dict(item) for item in FRAGMENTATION_MODELS.values()]


def resolve_model(model: str) -> str:
    """Имя модели из запроса → идентификатор реестра; пусто — kuzram."""
    key = str(model or MODEL_KUZRAM).strip().lower().replace("kuz-ram", "kuzram")
    legacy = key.endswith(LEGACY_MODEL_SUFFIX)
    base = key[: -len(LEGACY_MODEL_SUFFIX)] if legacy else key
    model_id = _ALIASES.get(base)
    if model_id is None:
        raise ValueError(f"Неизвестная модель дробления: {model}. Доступны: {', '.join(FRAGMENTATION_MODELS)}.")
    return model_id + LEGACY_MODEL_SUFFIX if legacy else model_id


def is_legacy_model(model: str) -> bool:
    """Модель считает прежними формулами (до перевода на Каннингема)."""
    return bool(FRAGMENTATION_MODELS[resolve_model(model)]["legacy"])


def predict_region(
    inputs: FragmentationInputs,
    model: str = MODEL_KUZRAM,
    calibration: Calibration | None = None,
    settings: KuzRamSettings | None = None,
) -> PredictedFragmentation:
    """Predict one region. Always returns role=predicted."""
    predictor = _PREDICTORS[resolve_model(model)]
    prediction = predictor(inputs, calibration, settings)
    prediction.role = ROLE_PREDICTED
    return prediction


def _region_payload(region: InfluenceRegion, prediction: PredictedFragmentation) -> dict[str, Any]:
    return {
        "id": region.id,
        "kind": region.kind,
        "hole_ids": list(region.hole_ids),
        "x": region.x,
        "y": region.y,
        "hole_kind": region.hole_kind,
        "inputs": region.inputs.to_dict(),
        "prediction": prediction.to_dict(),
        "warnings": list(region.warnings),
    }


def predict_design(
    design: BlastDesign,
    *,
    model: str = MODEL_KUZRAM,
    lump_size_mm: float = 400.0,
    max_oversize_pct: float = 5.0,
    calibration: Calibration | None = None,
    default_rock: RockSpec | None = None,
    default_explosive: ExplosiveSpec | None = None,
    explosives: dict[str, ExplosiveSpec] | None = None,
    hole_oversize_coeff: float | None = None,
    measured: list[MeasuredFragmentation] | None = None,
    settings: KuzRamSettings | None = None,
) -> dict[str, Any]:
    """Site / hole / domain predictions plus a heatmap payload.

    ``measured`` is echoed back unchanged. The engine never writes measured rows.
    """
    model_id = resolve_model(model)
    if lump_size_mm <= 0:
        raise ValueError("Кондиционный размер куска должен быть больше нуля, мм.")
    calibration = calibration or Calibration()
    rock = default_rock or RockSpec(
        name=design.rock_name or "порода",
        density_t_m3=DEFAULT_ROCK_DENSITY_T_M3,
        ucs_mpa=DEFAULT_ROCK_UCS_MPA,
        fissuring_ff=DEFAULT_ROCK_FISSURING,
    )
    explosive = default_explosive or ExplosiveSpec(
        name=design.explosive_key or "ВВ",
        density_t_m3=DEFAULT_EXPLOSIVE_DENSITY_T_M3,
        power_mj_kg=DEFAULT_EXPLOSIVE_ENERGY_MJ_KG,
    )
    holes, domains, site_region, warnings = collect_regions(
        design,
        lump_size_mm=lump_size_mm,
        default_rock=rock,
        default_explosive=explosive,
        explosives=explosives,
        hole_oversize_coeff=hole_oversize_coeff,
    )
    if site_region is None:
        raise ValueError("Недостаточно данных для прогноза дробления: нет скважин с массой заряда и сеткой.")

    hole_rows = [_region_payload(region, predict_region(region.inputs, model_id, calibration, settings)) for region in holes]
    domain_rows = [_region_payload(region, predict_region(region.inputs, model_id, calibration, settings)) for region in domains]
    site_prediction = predict_region(site_region.inputs, model_id, calibration, settings)
    measured_rows = [item.to_dict() for item in (measured or [])]
    if any(row.get("role") != ROLE_MEASURED for row in measured_rows):
        raise ValueError("Измеренная кусковатость должна иметь role=measured.")

    target = DesignedFragmentationTarget(lump_size_mm=lump_size_mm, max_oversize_pct=max_oversize_pct)
    maps = fragmentation_maps(hole_rows)
    return {
        "model": model_id,
        "model_version": FRAGMENTATION_MODELS[model_id]["version"],
        "target": target.to_dict(),
        "site": _region_payload(site_region, site_prediction),
        "holes": hole_rows,
        "regions": domain_rows,
        "maps": maps,
        "warnings": warnings,
        "measured": measured_rows,
        "calibration": calibration.to_dict(),
    }
