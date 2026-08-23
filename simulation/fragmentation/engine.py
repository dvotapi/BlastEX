"""Run a named fragmentation model on a blast design or a single region."""
from __future__ import annotations

from typing import Any, Callable

from design.models import BlastDesign
from simulation.fragmentation.kuznetsov import MODEL_ID as KUZNETSOV_ID
from simulation.fragmentation.kuznetsov import MODEL_VERSION as KUZNETSOV_VERSION
from simulation.fragmentation.kuznetsov import predict_kuznetsov
from simulation.fragmentation.kuzram import MODEL_ID as KUZRAM_ID
from simulation.fragmentation.kuzram import MODEL_VERSION as KUZRAM_VERSION
from simulation.fragmentation.kuzram import predict_kuzram
from simulation.fragmentation.maps import fragmentation_maps
from simulation.fragmentation.models import (
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
from simulation.fragmentation.swebrec import MODEL_ID as SWEBREC_ID
from simulation.fragmentation.swebrec import MODEL_VERSION as SWEBREC_VERSION
from simulation.fragmentation.swebrec import predict_swebrec

PredictFn = Callable[[FragmentationInputs, Calibration | None], PredictedFragmentation]

FRAGMENTATION_MODELS: dict[str, dict[str, str]] = {
    KUZNETSOV_ID: {
        "id": KUZNETSOV_ID,
        "version": KUZNETSOV_VERSION,
        "label": "Кузнецов",
        "distribution": "rosin_rammler",
    },
    KUZRAM_ID: {
        "id": KUZRAM_ID,
        "version": KUZRAM_VERSION,
        "label": "Kuz-Ram",
        "distribution": "rosin_rammler",
    },
    SWEBREC_ID: {
        "id": SWEBREC_ID,
        "version": SWEBREC_VERSION,
        "label": "Swebrec",
        "distribution": "swebrec",
    },
}

_PREDICTORS: dict[str, PredictFn] = {
    KUZNETSOV_ID: predict_kuznetsov,
    KUZRAM_ID: predict_kuzram,
    SWEBREC_ID: predict_swebrec,
}


def list_models() -> list[dict[str, str]]:
    return [dict(item) for item in FRAGMENTATION_MODELS.values()]


def resolve_model(model: str) -> str:
    key = str(model or KUZRAM_ID).strip().lower().replace("kuz-ram", "kuzram")
    if key in {"kuz", "kuznetcov", "kuznetsov"}:
        return KUZNETSOV_ID
    if key in {"kuzram", "kuz_ram"}:
        return KUZRAM_ID
    if key in {"swebrec", "swebeck"}:
        return SWEBREC_ID
    raise ValueError(f"Неизвестная модель дробления: {model}. Доступны: kuznetsov, kuzram, swebrec.")


def predict_region(
    inputs: FragmentationInputs,
    model: str = KUZRAM_ID,
    calibration: Calibration | None = None,
) -> PredictedFragmentation:
    """Predict one region. Always returns role=predicted."""
    predictor = _PREDICTORS[resolve_model(model)]
    prediction = predictor(inputs, calibration)
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
    model: str = KUZRAM_ID,
    lump_size_mm: float = 400.0,
    max_oversize_pct: float = 5.0,
    calibration: Calibration | None = None,
    default_rock: RockSpec | None = None,
    default_explosive: ExplosiveSpec | None = None,
    explosives: dict[str, ExplosiveSpec] | None = None,
    hole_oversize_coeff: float | None = None,
    measured: list[MeasuredFragmentation] | None = None,
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

    hole_rows = [_region_payload(region, predict_region(region.inputs, model_id, calibration)) for region in holes]
    domain_rows = [_region_payload(region, predict_region(region.inputs, model_id, calibration)) for region in domains]
    site_prediction = predict_region(site_region.inputs, model_id, calibration)
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
