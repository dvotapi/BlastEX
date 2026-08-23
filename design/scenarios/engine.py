"""Build and evaluate a design overlay without touching the approved passport.

The overlay is a deep copy. Pattern, charge and initiation are regenerated on
the copy only. Fragmentation, vibration and cost engines are reused as-is.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from Blast import ExplosiveProperties
from cost.explosive_data import DEFAULT_EXPLOSIVE_KEY, DEFAULT_EXPLOSIVES
from design.analysis import charge_per_delay, estimate_ppv, summary as design_summary
from design.charging import apply_charge_rules
from design.models import BlastDesign, HoleLoad, Receptor, is_explosive_deck_kind
from design.pattern import generate_pattern
from design.scenarios.types import (
    SOURCE_ENGINEERING,
    ScenarioOutcomes,
    ScenarioParams,
)
from design.timing import TimingExprError, build_template_network, resolve_network

DEFAULT_EXPLOSIVE = ExplosiveProperties("Гранулит-РП", 0.85, 3.76)


class InvalidScenarioParamsError(ValueError):
    """Raised when overlay knobs cannot be applied."""


def clone_design(design: BlastDesign) -> BlastDesign:
    """Independent copy. Mutations on the result never alias the original."""
    return BlastDesign.from_dict(design.to_dict())


def holes_loads_payload(design: BlastDesign) -> dict[str, Any]:
    return {
        "holes": [hole.to_dict() for hole in design.holes],
        "loads": [load.to_dict() for load in design.loads],
    }


def revision_sha256(design: BlastDesign) -> str:
    payload = holes_loads_payload(design)
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def resolve_explosive(design: BlastDesign) -> ExplosiveProperties:
    key = (design.explosive_key or "").strip()
    for item in DEFAULT_EXPLOSIVES:
        if key in {item.key, item.name, item.label}:
            return item.properties
    if not key:
        for item in DEFAULT_EXPLOSIVES:
            if item.key == DEFAULT_EXPLOSIVE_KEY:
                return item.properties
    return DEFAULT_EXPLOSIVE


def _assert_known_explosive(key: str) -> None:
    for item in DEFAULT_EXPLOSIVES:
        if key in {item.key, item.name, item.label}:
            return
    raise InvalidScenarioParamsError(f"Неизвестное ВВ «{key}».")


def _positive(value: float | None, label: str) -> None:
    if value is None:
        return
    if float(value) <= 0:
        raise InvalidScenarioParamsError(f"Параметр «{label}» должен быть больше нуля.")


def validate_params(params: ScenarioParams) -> None:
    _positive(params.diameter_mm, "диаметр")
    _positive(params.spacing_a_m, "шаг")
    _positive(params.burden_b_m, "ЛНС")
    _positive(params.powder_factor_kg_m3, "удельный расход")
    _positive(params.lump_size_mm, "кондиционный размер")
    _positive(params.mic_window_ms, "окно MIC")
    if params.stemming_m is not None and float(params.stemming_m) < 0:
        raise InvalidScenarioParamsError("Забойка не может быть отрицательной.")
    if params.subdrill_m is not None and float(params.subdrill_m) < 0:
        raise InvalidScenarioParamsError("Перебур не может быть отрицательным.")
    if params.inclination_deg is not None:
        angle = float(params.inclination_deg)
        if angle < 0 or angle > 45:
            raise InvalidScenarioParamsError("Наклон скважины задаётся от вертикали в диапазоне 0–45°.")
    if params.delay_interval_ms is not None and float(params.delay_interval_ms) <= 0:
        raise InvalidScenarioParamsError("Замедление должно быть больше нуля (мс).")
    if params.explosive_key is not None and not str(params.explosive_key).strip():
        raise InvalidScenarioParamsError("Тип ВВ не может быть пустым.")
    if params.explosive_key:
        _assert_known_explosive(str(params.explosive_key).strip())


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def resolved_geometry(design: BlastDesign, params: ScenarioParams) -> dict[str, float | None]:
    pattern = dict(design.pattern_params or {})
    enabled = [hole for hole in design.holes if hole.enabled]
    spacing = params.spacing_a_m
    if spacing is None:
        spacing = pattern.get("spacing_a_m")
    burden = params.burden_b_m
    if burden is None:
        burden = pattern.get("burden_b_m")
    diameter = params.diameter_mm
    if diameter is None:
        diameter = pattern.get("diameter_mm")
        if diameter is None:
            diameter = _mean([hole.diameter_mm for hole in enabled])
    return {
        "spacing_a_m": float(spacing) if spacing not in (None, "") else None,
        "burden_b_m": float(burden) if burden not in (None, "") else None,
        "diameter_mm": float(diameter) if diameter not in (None, "") else None,
    }


def apply_params(design: BlastDesign, params: ScenarioParams) -> BlastDesign:
    """Return a new overlay design. The argument is left unchanged."""
    validate_params(params)
    overlay = clone_design(design)
    geometry = resolved_geometry(overlay, params)
    pattern = dict(overlay.pattern_params or {})
    if geometry["spacing_a_m"] is not None:
        pattern["spacing_a_m"] = geometry["spacing_a_m"]
    if geometry["burden_b_m"] is not None:
        pattern["burden_b_m"] = geometry["burden_b_m"]
    if geometry["diameter_mm"] is not None:
        pattern["diameter_mm"] = geometry["diameter_mm"]
    if params.subdrill_m is not None:
        pattern["subdrill_m"] = float(params.subdrill_m)
    if params.inclination_deg is not None:
        pattern["angle_deg"] = float(params.inclination_deg)
    if params.pattern:
        pattern["pattern"] = params.pattern
    overlay.pattern_params = pattern

    if params.explosive_key:
        overlay.explosive_key = str(params.explosive_key).strip()

    regenerate_grid = any(
        value is not None
        for value in (
            params.diameter_mm,
            params.spacing_a_m,
            params.burden_b_m,
            params.subdrill_m,
            params.pattern,
            params.inclination_deg,
        )
    )
    if regenerate_grid and len(overlay.contour.vertices) >= 3:
        overlay.holes = generate_pattern(
            overlay.contour,
            pattern,
            overlay.holes,
            overlay.surfaces,
            overlay.domains,
        )
    else:
        if geometry["diameter_mm"] is not None:
            diameter = float(geometry["diameter_mm"])
            for hole in overlay.holes:
                hole.diameter_mm = diameter
        if params.inclination_deg is not None:
            from design.editing import apply_inclination

            angle = float(params.inclination_deg)
            overlay.holes = [apply_inclination(hole, angle) for hole in overlay.holes]

    rules = dict(overlay.charge_rules or {})
    if geometry["spacing_a_m"] is not None:
        rules["grid_a_m"] = geometry["spacing_a_m"]
    if geometry["burden_b_m"] is not None:
        rules["grid_b_m"] = geometry["burden_b_m"]
    if params.stemming_m is not None:
        rules["stemming_m"] = float(params.stemming_m)
    if params.powder_factor_kg_m3 is not None:
        rules["target_pf"] = float(params.powder_factor_kg_m3)
    overlay.charge_rules = rules

    rebuild_charges = (
        regenerate_grid
        or params.stemming_m is not None
        or params.powder_factor_kg_m3 is not None
        or params.explosive_key is not None
    )
    if overlay.holes and (rebuild_charges or not overlay.loads):
        explosive = resolve_explosive(overlay)
        overlay.loads = apply_charge_rules(
            overlay.holes,
            rules,
            explosive,
            contour=overlay.contour,
        )
        if params.powder_factor_kg_m3 is not None:
            _scale_loads_to_powder_factor(overlay.loads, float(params.powder_factor_kg_m3))
        _rebuild_network(overlay, params.delay_interval_ms)
    elif params.delay_interval_ms is not None and overlay.holes:
        _rebuild_network(overlay, params.delay_interval_ms)

    return overlay


def _scale_loads_to_powder_factor(loads: list[HoleLoad], powder_factor: float) -> None:
    for load in loads:
        volume = float(load.influence_volume_m3 or 0.0)
        if volume <= 0 or load.total_charge_kg <= 0:
            continue
        target_mass = powder_factor * volume
        scale = target_mass / load.total_charge_kg
        for deck in load.decks:
            if is_explosive_deck_kind(deck.kind):
                deck.mass_kg = float(deck.mass_kg) * scale
        load.total_charge_kg = sum(
            deck.mass_kg for deck in load.decks if is_explosive_deck_kind(deck.kind)
        )
        load.specific_q_kg_m3 = load.total_charge_kg / volume if volume > 0 else 0.0


def _rebuild_network(overlay: BlastDesign, delay_interval_ms: float | None = None) -> None:
    timing_params = dict(overlay.network.timing_params or {})
    scheme = str(timing_params.get("scheme") or "row")
    if "system" not in timing_params:
        timing_params["system"] = overlay.network.system or "nonel"
    if delay_interval_ms is not None:
        timing_params["interval_ms"] = float(delay_interval_ms)
    try:
        overlay.network = build_template_network(overlay.holes, scheme, timing_params)
        overlay.network.timing_params = timing_params
    except TimingExprError:
        fallback = {"system": overlay.network.system or "nonel"}
        if delay_interval_ms is not None:
            fallback["interval_ms"] = float(delay_interval_ms)
        overlay.network = build_template_network(overlay.holes, "row", fallback)


def _fragmentation_outcomes(overlay: BlastDesign, params: ScenarioParams, outcomes: ScenarioOutcomes) -> None:
    from simulation.fragmentation.engine import predict_design

    try:
        payload = predict_design(
            overlay,
            model=params.fragmentation_model or "kuzram",
            lump_size_mm=params.lump_size_mm,
            hole_oversize_coeff=(overlay.charge_rules or {}).get("hole_oversize_coeff"),
        )
    except ValueError as exc:
        outcomes.warnings.append(str(exc))
        return
    site = payload.get("site") or {}
    prediction = site.get("prediction") or {}
    outcomes.x50_mm = _opt_pred(prediction.get("x50_mm"))
    outcomes.x80_mm = _opt_pred(prediction.get("x80_mm"))
    outcomes.oversize_pct = _opt_pred(prediction.get("oversize_pct"))
    outcomes.x50_engineering_mm = outcomes.x50_mm
    outcomes.x80_engineering_mm = outcomes.x80_mm
    outcomes.oversize_engineering_pct = outcomes.oversize_pct
    outcomes.fragmentation_source = SOURCE_ENGINEERING
    for warning in payload.get("warnings") or []:
        outcomes.warnings.append(str(warning))


def _opt_pred(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    return float(raw)


def _vibration_outcomes(overlay: BlastDesign, params: ScenarioParams, outcomes: ScenarioOutcomes) -> None:
    from design.vibration import predict_design as predict_vibration

    enabled = [hole for hole in overlay.holes if hole.enabled]
    try:
        result = resolve_network(overlay.network, enabled, overlay.loads)
        mic = charge_per_delay(
            result.times_ms,
            overlay.loads,
            window_ms=params.mic_window_ms,
            events=result.events,
        )
        outcomes.mic_kg = float(mic.get("mic_kg") or 0.0)
    except Exception as exc:  # pragma: no cover - timing edge cases
        outcomes.warnings.append(f"MIC недоступен: {exc}")
        outcomes.mic_kg = None

    try:
        payload = predict_vibration(
            overlay,
            model_id=params.vibration_model_id,
            mic_window_ms=params.mic_window_ms,
        )
    except (ValueError, Exception) as exc:
        outcomes.warnings.append(str(exc))
        payload = {}
    predictions = list(payload.get("predictions") or [])
    if predictions:
        peak = max(predictions, key=lambda row: float(row.get("ppv_mm_s") or 0.0))
        outcomes.ppv_mm_s = float(peak.get("ppv_mm_s") or 0.0)
    elif outcomes.mic_kg is not None and overlay.receptors:
        receptor: Receptor = overlay.receptors[0]
        nearest = min(
            enabled,
            key=lambda hole: (hole.collar.x - receptor.location.x) ** 2
            + (hole.collar.y - receptor.location.y) ** 2,
            default=None,
        )
        if nearest is not None:
            distance = (
                (nearest.collar.x - receptor.location.x) ** 2
                + (nearest.collar.y - receptor.location.y) ** 2
            ) ** 0.5
            outcomes.ppv_mm_s = estimate_ppv(outcomes.mic_kg, max(distance, 1.0), 200.0, 1.6)
    for warning in payload.get("warnings") or []:
        text = str(warning)
        if text not in outcomes.warnings:
            outcomes.warnings.append(text)
    outcomes.ppv_engineering_mm_s = outcomes.ppv_mm_s
    outcomes.vibration_source = SOURCE_ENGINEERING


def evaluate_overlay(overlay: BlastDesign, params: ScenarioParams) -> ScenarioOutcomes:
    """Engineering outcomes on an already-built overlay. Does not persist."""
    stats = design_summary(overlay)
    geometry = resolved_geometry(overlay, params)
    outcomes = ScenarioOutcomes(
        drilling_metres=float(stats.get("drilling_footage_m") or 0.0),
        explosive_mass_kg=float(stats.get("total_charge_kg") or 0.0),
        powder_factor_kg_m3=float(stats.get("avg_specific_q_kg_m3") or 0.0),
        hole_count=int(stats.get("hole_count") or 0),
        block_volume_m3=float(stats.get("block_volume_m3") or 0.0),
        diameter_mm=geometry["diameter_mm"],
        spacing_a_m=geometry["spacing_a_m"],
        burden_b_m=geometry["burden_b_m"],
        fragmentation_source=SOURCE_ENGINEERING,
        vibration_source=SOURCE_ENGINEERING,
        cost_source=SOURCE_ENGINEERING,
        warnings=[],
    )
    if overlay.loads:
        _fragmentation_outcomes(overlay, params, outcomes)
    else:
        outcomes.warnings.append("Нет зарядов — прогноз кусковатости пропущен.")
    _vibration_outcomes(overlay, params, outcomes)
    return outcomes


def build_and_evaluate(design: BlastDesign, params: ScenarioParams) -> tuple[BlastDesign, ScenarioOutcomes, str, str]:
    """Clone, apply knobs, evaluate. Returns overlay, outcomes, source hash, overlay hash."""
    source_hash = revision_sha256(design)
    overlay = apply_params(design, params)
    if revision_sha256(design) != source_hash:
        raise RuntimeError("Построение сценария изменило утверждённый паспорт — это запрещено.")
    outcomes = evaluate_overlay(overlay, params)
    overlay_hash = revision_sha256(overlay)
    return overlay, outcomes, source_hash, overlay_hash
