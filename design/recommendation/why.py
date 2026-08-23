"""Human-readable 'why' for a suggested overlay (BDX-018).

Reuses BDX-015 driver / delta text when a model explanation is present and
BDX-014 interval / confidence / similarity when a model assessment exists.
Engineering deltas stay in the declared unit — never converted silently.
"""
from __future__ import annotations

from typing import Any

from design.optimization.types import OBJECTIVE_SPECS, OptimizationCandidate
from design.recommendation.types import (
    REASON_DECISION,
    REASON_DELTA,
    REASON_EXPLANATION,
    REASON_PARAM,
    REASON_PROFILE,
    REASON_UNCERTAINTY,
    ROLE_PREDICTED,
    RecommendationAssessment,
    RecommendationProfile,
    RecommendationReason,
)
from intelligence.explainability.types import explanation_from_payload
from intelligence.uncertainty.types import confidence_label_ru

_OBJECTIVE_BY_KEY = {item["key"]: item for item in OBJECTIVE_SPECS}

_PARAM_SPECS: tuple[dict[str, str], ...] = (
    {"key": "diameter_mm", "label": "Диаметр", "unit": "мм"},
    {"key": "burden_b_m", "label": "ЛНС", "unit": "м"},
    {"key": "spacing_a_m", "label": "Шаг", "unit": "м"},
    {"key": "subdrill_m", "label": "Перебур", "unit": "м"},
    {"key": "stemming_m", "label": "Забойка", "unit": "м"},
    {"key": "explosive_key", "label": "Тип ВВ", "unit": ""},
    {"key": "inclination_deg", "label": "Наклон", "unit": "°"},
    {"key": "delay_interval_ms", "label": "Замедление", "unit": "мс"},
)

_OUTCOME_SPECS: tuple[dict[str, str], ...] = (
    {"key": "total_predicted_cost_rub", "label": "Прогнозная смета", "unit": "₽", "objective": "cost"},
    {"key": "oversize_pct", "label": "Негабарит", "unit": "%", "objective": "oversize"},
    {"key": "drilling_metres", "label": "Погонаж бурения", "unit": "м", "objective": "drilling_metres"},
    {"key": "ppv_mm_s", "label": "PPV", "unit": "мм/с", "objective": "ppv"},
    {"key": "x50_mm", "label": "X50", "unit": "мм", "objective": "target_x50"},
)


def _format_number(value: float | None, unit: str) -> str:
    if value is None:
        return "—"
    number = float(value)
    if unit in {"₽"}:
        text = f"{number:,.0f}".replace(",", " ")
    elif unit in {"мм", "мс"}:
        text = f"{number:.0f}" if abs(number - round(number)) < 1e-6 else f"{number:.1f}"
    elif abs(number) >= 100:
        text = f"{number:.1f}"
    else:
        text = f"{number:.2f}"
    return f"{text} {unit}".strip()


def _signed(delta: float, unit: str) -> str:
    prefix = "+" if delta > 0 else ""
    return f"{prefix}{_format_number(delta, unit)}"


def _param_value(raw: Any, unit: str) -> str:
    if raw in (None, ""):
        return "—"
    if unit == "":
        return str(raw)
    try:
        return _format_number(float(raw), unit)
    except (TypeError, ValueError):
        return str(raw)


def _weight_text(profile: RecommendationProfile) -> str:
    parts: list[str] = []
    for key, weight in profile.weights.items():
        spec = _OBJECTIVE_BY_KEY.get(key)
        label = spec["label"] if spec else key
        parts.append(f"{label} ×{weight:g}")
    return "; ".join(parts)


def profile_reason(profile: RecommendationProfile) -> RecommendationReason:
    return RecommendationReason(
        kind=REASON_PROFILE,
        title=f"Профиль {profile.label}",
        detail=f"{profile.description} Веса: {_weight_text(profile)}.",
        role=ROLE_PREDICTED,
    )


def decision_reason() -> RecommendationReason:
    return RecommendationReason(
        kind=REASON_DECISION,
        title="Рекомендация, не утверждение",
        detail=(
            "Оверлей не применяется сам и не меняет DESIGNED-паспорт. "
            "Инженер решает, сохранить его как сценарий сравнения или оставить проект без изменений."
        ),
        role=ROLE_PREDICTED,
    )


def param_reasons(
    suggested: OptimizationCandidate,
    baseline: OptimizationCandidate | None,
) -> list[RecommendationReason]:
    reasons: list[RecommendationReason] = []
    suggested_values = dict(suggested.decision.values)
    if not suggested_values and suggested.params:
        payload = suggested.params.to_dict()
        for spec in _PARAM_SPECS:
            if payload.get(spec["key"]) not in (None, ""):
                suggested_values[spec["key"]] = payload[spec["key"]]
    baseline_values = dict(baseline.decision.values) if baseline is not None else {}
    baseline_params = baseline.params.to_dict() if baseline is not None else {}
    for spec in _PARAM_SPECS:
        key = spec["key"]
        rec = suggested_values.get(key)
        if rec in (None, ""):
            rec = suggested.params.to_dict().get(key)
        base = baseline_values.get(key)
        if base in (None, ""):
            base = baseline_params.get(key)
        if rec in (None, "") or rec == base:
            continue
        rec_text = _param_value(rec, spec["unit"])
        base_text = _param_value(base, spec["unit"])
        detail = (
            f"{spec['label']}: {base_text} → {rec_text} (PREDICTED оверлей, единицы {spec['unit'] or 'без конвертации'})."
            if base not in (None, "")
            else f"{spec['label']}: {rec_text} (PREDICTED оверлей)."
        )
        delta = None
        rec_num = None
        base_num = None
        try:
            rec_num = float(rec)
            base_num = None if base in (None, "") else float(base)
            if base_num is not None:
                delta = rec_num - base_num
        except (TypeError, ValueError):
            rec_num = None
            base_num = None
        reasons.append(
            RecommendationReason(
                kind=REASON_PARAM,
                title=spec["label"],
                detail=detail,
                metric=key,
                unit=spec["unit"],
                baseline=base_num,
                recommended=rec_num,
                delta=delta,
                role=ROLE_PREDICTED,
            )
        )
    return reasons


def outcome_reasons(
    suggested: OptimizationCandidate,
    baseline: OptimizationCandidate | None,
) -> list[RecommendationReason]:
    reasons: list[RecommendationReason] = []
    for spec in _OUTCOME_SPECS:
        rec = suggested.outcomes.metric_value(spec["key"])
        base = baseline.outcomes.metric_value(spec["key"]) if baseline is not None else None
        if rec is None:
            continue
        delta = None if base is None else rec - base
        if delta is None:
            detail = f"{spec['label']}: {_format_number(rec, spec['unit'])} (PREDICTED)."
        else:
            detail = (
                f"{spec['label']}: {_format_number(base, spec['unit'])} → "
                f"{_format_number(rec, spec['unit'])} ({_signed(delta, spec['unit'])}, PREDICTED)."
            )
        reasons.append(
            RecommendationReason(
                kind=REASON_DELTA,
                title=spec["label"],
                detail=detail,
                metric=spec["key"],
                unit=spec["unit"],
                baseline=base,
                recommended=rec,
                delta=delta,
                role=ROLE_PREDICTED,
            )
        )
    return reasons


def assessment_reasons(assessments: list[RecommendationAssessment]) -> list[RecommendationReason]:
    reasons: list[RecommendationReason] = []
    models = [item for item in assessments if item.model_available]
    if not models:
        reasons.append(
            RecommendationReason(
                kind=REASON_UNCERTAINTY,
                title="Модели не подключены",
                detail=(
                    "Интервал, уверенность и сходство (BDX-014) недоступны: production-модели исходов "
                    "не применены. Сравнение опирается на инженерный прогноз PREDICTED."
                ),
                role=ROLE_PREDICTED,
            )
        )
        return reasons
    for item in models:
        interval = item.uncertainty or {}
        lower = interval.get("lower")
        upper = interval.get("upper")
        band = (
            f"{_format_number(float(lower), item.unit)}–{_format_number(float(upper), item.unit)}"
            if lower is not None and upper is not None
            else "интервал недоступен"
        )
        confidence = item.confidence_label or confidence_label_ru(item.confidence)
        similar = f"{round(item.similarity_score * 100)} %"
        extra = ""
        if item.extrapolated_features or not item.in_domain:
            extra = " Признаки вне области обучения — экстраполяция."
        warning = f" {item.applicability_warning}" if item.applicability_warning else ""
        reasons.append(
            RecommendationReason(
                kind=REASON_UNCERTAINTY,
                title=f"{item.target_label}: уверенность {confidence}",
                detail=(
                    f"Ожидаемый интервал {band}; сходство {similar}; "
                    f"сопоставимых взрывов {item.comparable_count}.{extra}{warning}"
                ),
                metric=item.target_name,
                unit=item.unit,
                recommended=item.prediction,
                role=ROLE_PREDICTED,
            )
        )
        explanation = explanation_from_payload(item.explanation)
        if explanation.recommendation_summary:
            reasons.append(
                RecommendationReason(
                    kind=REASON_EXPLANATION,
                    title=f"{item.target_label}: почему модель сдвинула прогноз",
                    detail=explanation.recommendation_summary,
                    metric=item.target_name,
                    unit=item.unit,
                    recommended=item.prediction,
                    role=ROLE_PREDICTED,
                )
            )
        elif explanation.summary:
            reasons.append(
                RecommendationReason(
                    kind=REASON_EXPLANATION,
                    title=f"{item.target_label}: драйверы",
                    detail=explanation.summary,
                    metric=item.target_name,
                    unit=item.unit,
                    recommended=item.prediction,
                    role=ROLE_PREDICTED,
                )
            )
    return reasons


def build_reasons(
    *,
    profile: RecommendationProfile,
    suggested: OptimizationCandidate | None,
    baseline: OptimizationCandidate | None,
    assessments: list[RecommendationAssessment] | None = None,
) -> list[RecommendationReason]:
    reasons = [profile_reason(profile)]
    if suggested is not None:
        reasons.extend(param_reasons(suggested, baseline))
        reasons.extend(outcome_reasons(suggested, baseline))
    reasons.extend(assessment_reasons(list(assessments or [])))
    reasons.append(decision_reason())
    return reasons
