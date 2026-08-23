"""Russian labels for feature-range applicability warnings."""
from __future__ import annotations

FEATURE_LABELS_RU: dict[str, str] = {
    "GEOLOGY.mean_density_kg_m3": "плотность",
    "GEOLOGY.mean_ucs_mpa": "UCS",
    "GEOLOGY.mean_rqd_pct": "RQD",
    "GEOMETRY.mean_spacing_m": "расстояние между скважинами",
    "GEOMETRY.mean_burden_m": "ЛНС",
    "GEOMETRY.mean_diameter_mm": "диаметр",
    "GEOMETRY.mean_depth_m": "глубина",
    "GEOMETRY.mean_subdrill_m": "перебур",
    "CHARGING.mean_charge_kg": "масса заряда",
    "CHARGING.mean_powder_factor_kg_m3": "удельный расход",
    "CHARGING.mean_stemming_m": "забойка",
    "TIMING.mean_delay_ms": "замедление",
    "EXECUTION.mean_collar_offset_m": "смещение устья",
    "EXECUTION.fired_coverage": "доля подорванных скважин",
    "ENVIRONMENT.wet_hole_fraction": "доля обводнённых скважин",
    "ENVIRONMENT.nearest_receptor_distance_m": "расстояние до ресивера",
    "ENVIRONMENT.vibration_model_k": "коэффициент k сейсмики",
    "ENVIRONMENT.vibration_model_n": "показатель n сейсмики",
    "baseline": "инженерный базис",
}

FEATURE_UNITS_RU: dict[str, str] = {
    "GEOLOGY.mean_density_kg_m3": "кг/м³",
    "GEOLOGY.mean_ucs_mpa": "МПа",
    "GEOLOGY.mean_rqd_pct": "%",
    "GEOMETRY.mean_spacing_m": "м",
    "GEOMETRY.mean_burden_m": "м",
    "GEOMETRY.mean_diameter_mm": "мм",
    "GEOMETRY.mean_depth_m": "м",
    "GEOMETRY.mean_subdrill_m": "м",
    "CHARGING.mean_charge_kg": "кг",
    "CHARGING.mean_powder_factor_kg_m3": "кг/м³",
    "CHARGING.mean_stemming_m": "м",
    "TIMING.mean_delay_ms": "мс",
    "EXECUTION.mean_collar_offset_m": "м",
    "ENVIRONMENT.nearest_receptor_distance_m": "м",
    "baseline": "",
}

_SHORT_LABELS: dict[str, str] = {
    "mean_density_kg_m3": "плотность",
    "mean_ucs_mpa": "UCS",
    "mean_rqd_pct": "RQD",
    "mean_spacing_m": "расстояние между скважинами",
    "mean_burden_m": "ЛНС",
    "mean_diameter_mm": "диаметр",
    "mean_depth_m": "глубина",
    "mean_subdrill_m": "перебур",
    "mean_charge_kg": "масса заряда",
    "mean_powder_factor_kg_m3": "удельный расход",
    "mean_stemming_m": "забойка",
    "mean_delay_ms": "замедление",
    "mean_collar_offset_m": "смещение устья",
    "fired_coverage": "доля подорванных скважин",
    "wet_hole_fraction": "доля обводнённых скважин",
    "nearest_receptor_distance_m": "расстояние до ресивера",
    "vibration_model_k": "коэффициент k сейсмики",
    "vibration_model_n": "показатель n сейсмики",
}


def feature_label(name: str) -> str:
    if name in FEATURE_LABELS_RU:
        return FEATURE_LABELS_RU[name]
    short = str(name).split(".")[-1]
    return _SHORT_LABELS.get(short, short.replace("_", " "))


def feature_unit(name: str) -> str:
    if name in FEATURE_UNITS_RU:
        return FEATURE_UNITS_RU[name]
    short = str(name).split(".")[-1]
    for key, unit in FEATURE_UNITS_RU.items():
        if key.endswith(short):
            return unit
    return ""


def format_number(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")
