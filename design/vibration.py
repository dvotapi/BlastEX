"""Calibrated site vibration (phase BDX-007).

Site law is always ``PPV = K × SD^n``. The meaning of SD is stored on the
model and is never converted silently: a cube-root law cannot be applied as
if it were square-root, and ``Q^{1/3}/R`` is not the same as ``R/Q^{1/3}``.

Predicted PPV and measured PPV are separate entities. Event-based MIC is
taken from ``design.analysis.charge_per_delay`` — this module does not
reimplement the sliding window.
"""
from __future__ import annotations

import math
from typing import Any

from design.analysis import charge_per_delay
from design.models import (
    ROLE_MEASURED,
    ROLE_PREDICTED,
    BlastDesign,
    Receptor,
    VibrationMeasurement,
    VibrationModel,
    default_vibration_model,
)
from design.timing import resolve_network

# SD = Q^{1/3} / R  — the form already used by estimate_ppv (n typically +1.6).
CONVENTION_Q_CUBE_OVER_R = "q_cube_over_r"
# SD = R / Q^{1/3}
CONVENTION_R_OVER_Q_CUBE = "r_over_q_cube"
# SD = Q^{1/2} / R
CONVENTION_Q_SQRT_OVER_R = "q_sqrt_over_r"
# SD = R / Q^{1/2}  — USBM-style square-root scaled distance.
CONVENTION_R_OVER_Q_SQRT = "r_over_q_sqrt"

SCALED_DISTANCE_CONVENTIONS = (
    CONVENTION_Q_CUBE_OVER_R,
    CONVENTION_R_OVER_Q_CUBE,
    CONVENTION_Q_SQRT_OVER_R,
    CONVENTION_R_OVER_Q_SQRT,
)

CONVENTION_LABELS = {
    CONVENTION_Q_CUBE_OVER_R: "Q⅓ / R",
    CONVENTION_R_OVER_Q_CUBE: "R / Q⅓",
    CONVENTION_Q_SQRT_OVER_R: "√Q / R",
    CONVENTION_R_OVER_Q_SQRT: "R / √Q",
}

CONVENTION_FORMULAS = {
    CONVENTION_Q_CUBE_OVER_R: "SD = Q^(1/3) / R",
    CONVENTION_R_OVER_Q_CUBE: "SD = R / Q^(1/3)",
    CONVENTION_Q_SQRT_OVER_R: "SD = Q^(1/2) / R",
    CONVENTION_R_OVER_Q_SQRT: "SD = R / Q^(1/2)",
}

DEFAULT_MIC_WINDOW_MS = 8.0


class ScaledDistanceMismatchError(ValueError):
    """Raised when two site laws or a law and a measurement disagree on SD."""


def list_conventions() -> list[dict[str, str]]:
    return [
        {
            "id": key,
            "label": CONVENTION_LABELS[key],
            "formula": CONVENTION_FORMULAS[key],
        }
        for key in SCALED_DISTANCE_CONVENTIONS
    ]


def normalize_convention(value: Any, default: str = CONVENTION_Q_CUBE_OVER_R) -> str:
    text = str(value or default).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "cube": CONVENTION_Q_CUBE_OVER_R,
        "cube_root": CONVENTION_Q_CUBE_OVER_R,
        "q13_over_r": CONVENTION_Q_CUBE_OVER_R,
        "cis": CONVENTION_Q_CUBE_OVER_R,
        "r_over_q13": CONVENTION_R_OVER_Q_CUBE,
        "cube_root_r": CONVENTION_R_OVER_Q_CUBE,
        "square": CONVENTION_R_OVER_Q_SQRT,
        "square_root": CONVENTION_R_OVER_Q_SQRT,
        "usbm": CONVENTION_R_OVER_Q_SQRT,
        "r_over_sqrt_q": CONVENTION_R_OVER_Q_SQRT,
        "sqrt_q_over_r": CONVENTION_Q_SQRT_OVER_R,
    }
    if text in SCALED_DISTANCE_CONVENTIONS:
        return text
    if text in aliases:
        return aliases[text]
    raise ValueError(
        f"Неизвестная конвенция приведённого расстояния: {value}. "
        f"Доступны: {', '.join(SCALED_DISTANCE_CONVENTIONS)}."
    )


def require_same_convention(left: str, right: str, *, context: str) -> str:
    """Refuse to mix two scaled-distance definitions."""
    a = normalize_convention(left)
    b = normalize_convention(right)
    if a != b:
        raise ScaledDistanceMismatchError(
            f"Нельзя смешивать конвенции приведённого расстояния ({context}): "
            f"{a} ({CONVENTION_FORMULAS[a]}) и {b} ({CONVENTION_FORMULAS[b]})."
        )
    return a


def scaled_distance(mic_kg: float, distance_m: float, convention: str) -> float:
    """Return SD for the named convention. Never remaps to another convention."""
    convention = normalize_convention(convention)
    if mic_kg <= 0 or distance_m <= 0:
        return 0.0
    cube = mic_kg ** (1.0 / 3.0)
    sqrt = math.sqrt(mic_kg)
    if convention == CONVENTION_Q_CUBE_OVER_R:
        return cube / distance_m
    if convention == CONVENTION_R_OVER_Q_CUBE:
        return distance_m / cube
    if convention == CONVENTION_Q_SQRT_OVER_R:
        return sqrt / distance_m
    return distance_m / sqrt


def predict_ppv(mic_kg: float, distance_m: float, model: VibrationModel) -> float:
    """PPV = K × SD^n using the model's own scaled-distance convention."""
    if mic_kg <= 0 or distance_m <= 0:
        return 0.0
    convention = normalize_convention(model.scaled_distance)
    sd = scaled_distance(mic_kg, distance_m, convention)
    if sd <= 0:
        return 0.0
    return float(model.k) * (sd ** float(model.n))


def receptor_distance_m(receptor: Receptor, holes: list, hole_ids: list[str] | None = None) -> tuple[float, str]:
    """3D distance from the receptor to the nearest hole (optionally a MIC subset)."""
    allowed = set(hole_ids) if hole_ids else None
    best_d = 0.0
    best_id = ""
    for hole in holes:
        if not getattr(hole, "enabled", True):
            continue
        if allowed is not None and hole.id not in allowed:
            continue
        dx = receptor.location.x - hole.collar.x
        dy = receptor.location.y - hole.collar.y
        dz = receptor.location.z - hole.collar.z
        distance = math.sqrt(dx * dx + dy * dy + dz * dz)
        if not best_id or distance < best_d:
            best_d = distance
            best_id = hole.id
    return (best_d, best_id)


def attach_receptor(design: BlastDesign, receptor: Receptor) -> Receptor:
    """Upsert a receptor on the design. Kind must be a known receptor type."""
    if not receptor.id:
        used = {item.id for item in design.receptors}
        index = len(design.receptors) + 1
        while f"R-{index}" in used:
            index += 1
        receptor.id = f"R-{index}"
    kind = receptor.kind if receptor.kind in {
        "building",
        "pipeline",
        "crusher",
        "highwall",
        "power_line",
        "monitoring_station",
    } else "building"
    receptor.kind = kind
    for index, existing in enumerate(design.receptors):
        if existing.id == receptor.id:
            design.receptors[index] = receptor
            return receptor
    design.receptors.append(receptor)
    return receptor


def attach_measurement(design: BlastDesign, measurement: VibrationMeasurement) -> VibrationMeasurement:
    """Store a measured PPV. Role is forced to measured; never written as predicted."""
    measurement.role = ROLE_MEASURED
    if measurement.scaled_distance:
        measurement.scaled_distance = normalize_convention(measurement.scaled_distance)
    if not measurement.id:
        used = {item.id for item in design.vibration_measurements}
        index = len(design.vibration_measurements) + 1
        while f"VM-{index}" in used:
            index += 1
        measurement.id = f"VM-{index}"
    if measurement.receptor_id and measurement.receptor_id not in {r.id for r in design.receptors}:
        raise ValueError(f"Рецептор «{measurement.receptor_id}» не найден на площадке.")
    for index, existing in enumerate(design.vibration_measurements):
        if existing.id == measurement.id:
            design.vibration_measurements[index] = measurement
            return measurement
    design.vibration_measurements.append(measurement)
    return measurement


def resolve_site_model(design: BlastDesign, model_id: str = "") -> VibrationModel:
    if design.vibration_models:
        if model_id:
            for model in design.vibration_models:
                if model.id == model_id:
                    return model
            raise ValueError(f"Модель сейсмики «{model_id}» не найдена.")
        return design.vibration_models[0]
    if model_id:
        raise ValueError(f"Модель сейсмики «{model_id}» не найдена.")
    return default_vibration_model()


def event_mic(design: BlastDesign, window_ms: float = DEFAULT_MIC_WINDOW_MS) -> dict[str, Any]:
    """Event-based MIC with a configurable window. Reuses charge_per_delay."""
    if window_ms <= 0:
        raise ValueError("Окно MIC должно быть больше нуля.")
    enabled = [h for h in design.holes if h.enabled]
    result = resolve_network(design.network, enabled, design.loads)
    return charge_per_delay(result.times_ms, design.loads, window_ms=window_ms, events=result.events)


def _measurements_for_receptor(
    measurements: list[VibrationMeasurement],
    receptor_id: str,
    model: VibrationModel,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return measured rows. PPV values stay comparable; SD is only shown when conventions match."""
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    model_conv = normalize_convention(model.scaled_distance)
    for item in measurements:
        if item.receptor_id != receptor_id:
            continue
        payload = item.to_dict()
        payload["role"] = ROLE_MEASURED
        if item.scaled_distance:
            try:
                require_same_convention(
                    model_conv,
                    item.scaled_distance,
                    context=f"измерение {item.id} / модель {model.id}",
                )
                payload["scaled_distance_compatible"] = True
            except ScaledDistanceMismatchError as exc:
                payload["scaled_distance_compatible"] = False
                warnings.append(str(exc))
        else:
            payload["scaled_distance_compatible"] = None
        rows.append(payload)
    return rows, warnings


def predict_design(
    design: BlastDesign,
    *,
    model_id: str = "",
    mic_window_ms: float = DEFAULT_MIC_WINDOW_MS,
    measurements: list[VibrationMeasurement] | None = None,
) -> dict[str, Any]:
    """Predict PPV at every receptor from event-based MIC and the site law."""
    model = resolve_site_model(design, model_id)
    convention = normalize_convention(model.scaled_distance)
    mic = event_mic(design, window_ms=mic_window_ms)
    enabled = [h for h in design.holes if h.enabled]
    stored = list(design.vibration_measurements)
    extra = list(measurements or [])
    all_measured = stored + [item for item in extra if item.id not in {m.id for m in stored}]

    predictions: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not design.receptors:
        warnings.append("На площадке нет рецепторов — прогноз PPV не к чему привязать.")

    for receptor in design.receptors:
        distance_m, nearest_id = receptor_distance_m(receptor, enabled, mic.get("hole_ids") or None)
        if distance_m <= 0 and not nearest_id:
            distance_m, nearest_id = receptor_distance_m(receptor, enabled)
        ppv = predict_ppv(float(mic["mic_kg"]), distance_m, model)
        sd = scaled_distance(float(mic["mic_kg"]), distance_m, convention)
        measured_rows, measure_warnings = _measurements_for_receptor(all_measured, receptor.id, model)
        warnings.extend(measure_warnings)
        limit = receptor.ppv_limit_mm_s
        predictions.append(
            {
                "receptor_id": receptor.id,
                "receptor_name": receptor.name,
                "receptor_kind": receptor.kind,
                "role": ROLE_PREDICTED,
                "ppv_mm_s": round(ppv, 4),
                "distance_m": round(distance_m, 3),
                "nearest_hole_id": nearest_id,
                "mic_kg": mic["mic_kg"],
                "mic_window_ms": mic_window_ms,
                "mic_hole_ids": list(mic.get("hole_ids") or []),
                "scaled_distance": convention,
                "scaled_distance_value": round(sd, 6),
                "scaled_distance_formula": CONVENTION_FORMULAS[convention],
                "k": model.k,
                "n": model.n,
                "model_id": model.id,
                "ppv_limit_mm_s": limit,
                "exceeds_limit": bool(limit is not None and ppv > limit),
                "measured": measured_rows,
            }
        )

    echoed = []
    for item in all_measured:
        row = item.to_dict()
        row["role"] = ROLE_MEASURED
        echoed.append(row)

    return {
        "model": model.to_dict(),
        "convention": convention,
        "convention_formula": CONVENTION_FORMULAS[convention],
        "mic": mic,
        "mic_window_ms": mic_window_ms,
        "predictions": predictions,
        "measured": echoed,
        "warnings": warnings,
        "receptor_count": len(design.receptors),
    }
