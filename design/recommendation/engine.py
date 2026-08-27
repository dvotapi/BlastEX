"""Suggest a profile-weighted overlay. Never write it back into the passport.

Reuses BDX-016 ``build_and_evaluate`` via BDX-017 ``optimize``. The result is
a recommendation: ``auto_applied`` is always false and the DESIGNED holes /
loads are checked after the search.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable

from design.models import BlastDesign
from design.optimization.engine import OptimizationError, optimize
from design.optimization.types import (
    DEFAULT_OBJECTIVES,
    KIND_BASELINE,
    VariableBound,
)
from design.recommendation.profiles import (
    UnknownProfileError,
    pick_for_profile,
    profile_spec,
    profile_winners,
)
from design.recommendation.types import (
    APPLIED_AS,
    DEFAULT_MAX_CANDIDATES,
    DEFAULT_TARGET_X50_MM,
    METHOD_PROFILE_PARETO,
    ROLE_DESIGNED,
    ROLE_PREDICTED,
    DesignRecommendation,
    RecommendationAssessment,
)
from design.recommendation.why import build_reasons
from design.scenarios.engine import holes_loads_payload, resolved_geometry, revision_sha256
from design.scenarios.types import ScenarioParams

AssessFn = Callable[[BlastDesign, ScenarioParams], list[RecommendationAssessment]]


class RecommendationError(ValueError):
    """Recommendation request cannot be evaluated."""


def new_recommendation_id() -> str:
    return "rec-" + uuid.uuid4().hex[:10]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_bounds(design: BlastDesign) -> list[VariableBound]:
    """Small discrete neighbourhood around the approved geometry. Units stay explicit."""
    geometry = resolved_geometry(design, ScenarioParams())
    diameter = geometry.get("diameter_mm") or 152.0
    burden = geometry.get("burden_b_m") or 4.0
    spacing = geometry.get("spacing_a_m") or 5.0
    diameters = [152.0, 165.0]
    if float(diameter) not in diameters:
        diameters.append(float(diameter))
    diameters = sorted({round(float(item), 6) for item in diameters if float(item) > 0})
    burdens = sorted({
        value
        for value in (float(burden) - 0.5, float(burden), float(burden) + 0.5)
        if value > 0
    })
    spacings = sorted({
        value
        for value in (float(spacing) - 0.5, float(spacing), float(spacing) + 0.5)
        if value > 0
    })
    return [
        VariableBound(name="diameter_mm", values=diameters),
        VariableBound(name="burden_b_m", values=burdens),
        VariableBound(name="spacing_a_m", values=spacings),
    ]


def recommend(
    design: BlastDesign,
    profile_key: str,
    bounds: list[VariableBound] | None = None,
    *,
    objectives: list[str] | None = None,
    target_x50_mm: float = DEFAULT_TARGET_X50_MM,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    base_params: ScenarioParams | None = None,
    constraints: dict[str, float | None] | None = None,
    cost_fn=None,
    assess_fn: AssessFn | None = None,
    recommendation_id: str | None = None,
) -> DesignRecommendation:
    """Pick one overlay for the profile. Does not persist and does not save the design."""
    if not design.holes:
        raise RecommendationError("В паспорте нет скважин — рекомендовать нечего.")
    try:
        profile = profile_spec(profile_key)
    except UnknownProfileError as exc:
        raise RecommendationError(str(exc)) from exc
    if float(target_x50_mm) <= 0:
        raise RecommendationError("Целевой X50 должен быть больше нуля (мм).")

    source_hash = revision_sha256(design)
    approved_before = holes_loads_payload(design)
    keys = [item for item in (objectives or list(DEFAULT_OBJECTIVES)) if item]
    space = list(bounds) if bounds else default_bounds(design)

    try:
        search = optimize(
            design,
            space,
            objectives=keys,
            target_x50_mm=float(target_x50_mm),
            max_candidates=int(max_candidates),
            include_baseline=True,
            base_params=base_params or ScenarioParams(),
            constraints=constraints,
            cost_fn=cost_fn,
        )
    except OptimizationError as exc:
        raise RecommendationError(str(exc)) from exc

    if holes_loads_payload(design) != approved_before or revision_sha256(design) != source_hash:
        raise RuntimeError("Рекомендация изменила утверждённый паспорт — это запрещено.")

    baseline = next((item for item in search.candidates if item.kind == KIND_BASELINE), None)
    suggested = pick_for_profile(search.candidates, profile.key, keys)
    winners = profile_winners(search.candidates, keys)
    alternatives: list = []
    seen = {suggested.candidate_id if suggested else ""}
    for other in winners.values():
        if other.candidate_id in seen:
            continue
        alternatives.append(other)
        seen.add(other.candidate_id)

    assessments: list[RecommendationAssessment] = []
    warnings = list(search.warnings)
    if assess_fn is not None and suggested is not None:
        from design.scenarios.engine import apply_params

        overlay = apply_params(design, suggested.params)
        if holes_loads_payload(design) != approved_before:
            raise RuntimeError("Оценка модели изменила утверждённый паспорт — это запрещено.")
        try:
            assessments = list(assess_fn(overlay, suggested.params) or [])
        except Exception as exc:
            warnings.append(f"Модели исходов не применены: {exc}")
            assessments = []

    reasons = build_reasons(
        profile=profile,
        suggested=suggested,
        baseline=baseline,
        assessments=assessments,
    )
    if suggested is None:
        warnings.append("Профиль не нашёл допустимый оверлей на прогнозном фронте.")

    return DesignRecommendation(
        recommendation_id=recommendation_id or new_recommendation_id(),
        design_id=design.design_id,
        profile=profile.key,
        suggested=suggested,
        baseline=baseline,
        alternatives=alternatives,
        profile_picks={key: item.candidate_id for key, item in winners.items()},
        reasons=reasons,
        assessments=assessments,
        objectives=keys,
        target_x50_mm=float(target_x50_mm),
        search_run_id=search.run_id,
        evaluated=search.evaluated,
        pareto_count=len(search.pareto_front),
        method=METHOD_PROFILE_PARETO,
        auto_applied=False,
        approved=False,
        replaces_design=False,
        modifies_design=False,
        applied_as=APPLIED_AS,
        source_design_role=ROLE_DESIGNED,
        suggested_role=ROLE_PREDICTED,
        engineer_decides=True,
        source_revision_sha256=source_hash,
        approved_unchanged=True,
        created_at=_utc_now_iso(),
        warnings=warnings,
    )
