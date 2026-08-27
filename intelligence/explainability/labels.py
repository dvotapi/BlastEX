"""Russian / English feature labels for driver lists and recommendation text."""
from __future__ import annotations

from intelligence.uncertainty.labels import feature_label, feature_unit, format_number

FEATURE_LABELS_EN: dict[str, str] = {
    "GEOLOGY.mean_density_kg_m3": "Density",
    "GEOLOGY.mean_ucs_mpa": "UCS",
    "GEOLOGY.mean_rqd_pct": "RQD",
    "GEOMETRY.mean_spacing_m": "Spacing",
    "GEOMETRY.mean_burden_m": "Burden",
    "GEOMETRY.mean_diameter_mm": "Diameter",
    "GEOMETRY.mean_depth_m": "Depth",
    "GEOMETRY.mean_subdrill_m": "Subdrill",
    "CHARGING.mean_charge_kg": "Charge mass",
    "CHARGING.mean_powder_factor_kg_m3": "Powder Factor",
    "CHARGING.mean_stemming_m": "Stemming",
    "TIMING.mean_delay_ms": "Delay",
    "EXECUTION.mean_collar_offset_m": "Collar offset",
    "EXECUTION.fired_coverage": "Fired coverage",
    "ENVIRONMENT.wet_hole_fraction": "Wet-hole fraction",
    "ENVIRONMENT.nearest_receptor_distance_m": "Receptor distance",
    "ENVIRONMENT.vibration_model_k": "Vibration k",
    "ENVIRONMENT.vibration_model_n": "Vibration n",
    "baseline": "Engineering baseline",
}

_SHORT_EN: dict[str, str] = {
    "mean_density_kg_m3": "Density",
    "mean_ucs_mpa": "UCS",
    "mean_rqd_pct": "RQD",
    "mean_spacing_m": "Spacing",
    "mean_burden_m": "Burden",
    "mean_diameter_mm": "Diameter",
    "mean_depth_m": "Depth",
    "mean_subdrill_m": "Subdrill",
    "mean_charge_kg": "Charge mass",
    "mean_powder_factor_kg_m3": "Powder Factor",
    "mean_stemming_m": "Stemming",
    "mean_delay_ms": "Delay",
    "mean_collar_offset_m": "Collar offset",
    "fired_coverage": "Fired coverage",
    "wet_hole_fraction": "Wet-hole fraction",
    "nearest_receptor_distance_m": "Receptor distance",
    "vibration_model_k": "Vibration k",
    "vibration_model_n": "Vibration n",
}


def feature_label_en(name: str) -> str:
    if name in FEATURE_LABELS_EN:
        return FEATURE_LABELS_EN[name]
    short = str(name).split(".")[-1]
    if short in _SHORT_EN:
        return _SHORT_EN[short]
    return short.replace("_", " ")


def format_share_pct(value: float) -> str:
    rounded = int(round(float(value)))
    if rounded < 0:
        rounded = 0
    return f"{rounded}%"


def format_signed_delta(value: float, *, digits: int) -> str:
    factor = 10 ** max(0, int(digits))
    rounded = round(float(value) * factor) / factor if digits > 0 else float(round(value))
    if abs(rounded) < 0.5 / factor:
        rounded = 0.0
    if digits <= 0:
        body = str(int(abs(rounded)))
    else:
        body = f"{abs(rounded):.{digits}f}".replace(".", ",")
        body = body.rstrip("0").rstrip(",")
    if rounded < 0:
        return f"−{body}"
    if rounded > 0:
        return f"+{body}"
    return body if digits <= 0 else ("0" if not body else body)


def delta_digits(unit: str, delta: float) -> int:
    text = str(unit or "").strip().lower()
    magnitude = abs(float(delta))
    if text in {"", "0-1", "0–1"}:
        return 2
    if text in {"mm/s", "мм/с", "hz", "гц"}:
        return 2 if magnitude < 10 else 1
    if text in {"%", "pp"}:
        return 1 if magnitude < 10 else 0
    if magnitude >= 5:
        return 0
    return 1


def format_expected_delta(delta: float, unit: str) -> str:
    digits = delta_digits(unit, delta)
    signed = format_signed_delta(delta, digits=digits)
    mapped = {
        "mm": "мм",
        "mm/s": "мм/с",
        "Hz": "Гц",
        "hz": "Гц",
    }.get(str(unit or "").strip(), unit)
    suffix = f" {mapped}" if mapped else ""
    return f"{signed}{suffix}"
