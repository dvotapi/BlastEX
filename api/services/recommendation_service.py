"""Suggest a profile overlay. Never writes the approved passport."""
from __future__ import annotations

from typing import Any

from api.exceptions import (
    InvalidDesignError,
    InvalidRecommendationError,
    RecommendationNotFoundError as ApiRecommendationNotFound,
)
from api.schemas.design import BlastDesignSchema, DesignCostRequest
from api.schemas.outcomes import OutcomePredictAllRequest
from api.schemas.recommendation import (
    RecommendationListResponse,
    RecommendationPromoteRequest,
    RecommendationRequest,
    DesignRecommendationSchema,
    RecommendationSummarySchema,
)
from api.schemas.scenarios import ScenarioCreateRequest, ScenarioCreateResponse, ScenarioParamsSchema
from api.services.design_service import estimate_design_cost
from api.services.scenario_service import create_scenario
from cost.v2.legacy_adapter import default_legacy_references
from design.models import BlastDesign
from design.optimization.types import VariableBound
from design.persistence import DesignNotFoundError as StoreDesignNotFound
from design.persistence import load_design
from design.recommendation.engine import RecommendationError, recommend
from design.recommendation.persistence import (
    RecommendationNotFoundError as StoreRecommendationNotFound,
)
from design.recommendation.persistence import list_recommendations as store_list
from design.recommendation.persistence import load_recommendation as store_load
from design.recommendation.persistence import save_recommendation
from design.recommendation.types import PROFILE_KEYS, RecommendationAssessment
from design.recommendation.why import build_reasons
from design.recommendation.profiles import profile_spec
from design.scenarios.engine import holes_loads_payload, revision_sha256
from design.scenarios.types import ScenarioOutcomes, ScenarioParams


def _design_from_schema(schema: BlastDesignSchema) -> BlastDesign:
    return BlastDesign.from_dict(schema.model_dump())


def _assert_unchanged(before: dict[str, Any], design: BlastDesign, action: str) -> None:
    after = holes_loads_payload(design)
    if after != before:
        raise InvalidDesignError(
            f"{action} не должно менять проектные скважины и заряды утверждённого паспорта."
        )


def _apply_cost(overlay: BlastDesign, params: ScenarioParams, outcomes: ScenarioOutcomes) -> None:
    # Справочники — фиксированные значения Cost V1 по умолчанию. Per-org данные
    # этот сервис не читал никогда: до переезда справочников он так же брал
    # команду по умолчанию. Чтобы включить ревизию организации, роутеру сервиса
    # нужен `Depends(current_legacy_references)`.
    try:
        result = estimate_design_cost(
            DesignCostRequest(
                design=BlastDesignSchema(**overlay.to_dict()),
                scenario_id=params.cost_scenario_id or "drill_blast",
            ),
            default_legacy_references(),
        )
    except Exception as exc:
        outcomes.warnings.append(f"Смета недоступна: {exc}")
        return
    outcomes.total_predicted_cost_rub = float(result.total_amount_rub)
    outcomes.direct_cost_rub = float(result.variable_total_rub)
    outcomes.cost_per_m3 = float(result.cost_per_m3)
    outcomes.cost_source = "engineering"


def _assessment_from_target(target, *, model_id: str) -> RecommendationAssessment | None:
    if target is None or not getattr(target, "prediction_applied", False):
        return None
    explanation = target.explanation.model_dump() if target.explanation is not None else {}
    uncertainty = target.uncertainty.model_dump() if target.uncertainty is not None else {}
    return RecommendationAssessment(
        target_name=str(target.target_name or ""),
        target_label=str(target.label or target.target_name or ""),
        unit=str(target.unit or ""),
        prediction=None if target.prediction is None and target.value is None else float(
            target.prediction if target.prediction is not None else target.value
        ),
        uncertainty=uncertainty,
        confidence=str(target.confidence or "low"),
        confidence_label=str(target.confidence_label or ""),
        similarity_score=float(target.similarity_score or 0.0),
        applicability_warning=str(target.applicability_warning or ""),
        comparable_count=int(target.comparable_count or 0),
        in_domain=bool(target.in_domain),
        sample_count=int(target.sample_count or 0),
        extrapolated_features=list(target.extrapolated_features or []),
        explanation=explanation,
        model_id=model_id,
        model_available=True,
        role="predicted",
    )


def collect_assessments(team_id: str, overlay: BlastDesign, params: ScenarioParams) -> list[RecommendationAssessment]:
    """Attach BDX-014 / BDX-015 fields when production or named models exist."""
    wants_ml = bool(params.use_production_overlays or params.outcome_model_ids)
    if not wants_ml or not team_id:
        return []
    from api.services import outcome_service

    panel = outcome_service.predict_panel(
        team_id,
        OutcomePredictAllRequest(
            site_id=params.site_id,
            use_production=params.use_production_overlays,
            model_ids=dict(params.outcome_model_ids),
            design=BlastDesignSchema(**overlay.to_dict()),
        ),
    )
    collected: list[RecommendationAssessment] = []
    mapping = (
        (panel.x50_mm, (panel.models.get("fragmentation").model_id if panel.models.get("fragmentation") else "")),
        (panel.oversize_pct, (panel.models.get("oversize").model_id if panel.models.get("oversize") else "")),
        (panel.ppv, (panel.models.get("vibration").model_id if panel.models.get("vibration") else "")),
    )
    for target, model_id in mapping:
        item = _assessment_from_target(target, model_id=model_id)
        if item is not None:
            collected.append(item)
    return collected


def run_recommendation(team_id: str, request: RecommendationRequest) -> DesignRecommendationSchema:
    design = _design_from_schema(request.design)
    if not design.holes:
        raise InvalidRecommendationError("В паспорте нет скважин — рекомендовать нечего.")
    profile_key = request.normalized_profile()
    if profile_key not in PROFILE_KEYS:
        raise InvalidRecommendationError(
            f"Неизвестный профиль рекомендации «{request.profile}». Допустимы: {', '.join(PROFILE_KEYS)}."
        )
    approved_before = holes_loads_payload(design)
    source_hash = revision_sha256(design)
    bounds = [VariableBound.from_dict(item.model_dump()) for item in request.variables]
    params = ScenarioParams.from_dict(request.params.model_dump())
    constraints = {
        "max_ppv_mm_s": request.constraints.max_ppv_mm_s,
        "max_oversize_pct": request.constraints.max_oversize_pct,
        "max_cost_rub": request.constraints.max_cost_rub,
    }

    def assess(overlay: BlastDesign, overlay_params: ScenarioParams) -> list[RecommendationAssessment]:
        return collect_assessments(team_id, overlay, overlay_params)

    try:
        result = recommend(
            design,
            profile_key,
            bounds or None,
            objectives=list(request.objectives) or None,
            target_x50_mm=float(request.target_x50_mm),
            max_candidates=int(request.max_candidates),
            base_params=params,
            constraints=constraints,
            cost_fn=_apply_cost,
            assess_fn=assess if (params.use_production_overlays or params.outcome_model_ids) else None,
        )
    except RecommendationError as exc:
        raise InvalidRecommendationError(str(exc)) from exc

    _assert_unchanged(approved_before, design, "Рекомендация")
    if revision_sha256(design) != source_hash:
        raise InvalidDesignError("Рекомендация изменила утверждённый паспорт.")

    if result.assessments:
        result.reasons = build_reasons(
            profile=profile_spec(result.profile),
            suggested=result.suggested,
            baseline=result.baseline,
            assessments=result.assessments,
        )

    if request.persist:
        if not design.design_id:
            raise InvalidRecommendationError("Для сохранения рекомендации у паспорта должен быть design_id.")
        save_recommendation(team_id, result)
        try:
            stored = load_design(team_id, design.design_id)
            _assert_unchanged(approved_before, stored, "Сохранение рекомендации")
        except StoreDesignNotFound:
            pass

    if request.persist_as_scenario and result.suggested is not None:
        if not design.design_id:
            raise InvalidRecommendationError("Для сохранения сценария у паспорта должен быть design_id.")
        create_scenario(
            team_id,
            ScenarioCreateRequest(
                design=request.design,
                name=f"Рекомендация {result.profile}",
                params=ScenarioParamsSchema(**result.suggested.params.to_dict()),
                persist=True,
            ),
        )
        _assert_unchanged(approved_before, design, "Сохранение рекомендации как сценария")

    payload = result.to_dict()
    payload["approved_unchanged"] = True
    payload["auto_applied"] = False
    payload["approved"] = False
    return DesignRecommendationSchema(**payload)


def list_plan_recommendations(team_id: str, design_id: str) -> RecommendationListResponse:
    items = store_list(team_id, design_id)
    return RecommendationListResponse(
        items=[RecommendationSummarySchema(**item) for item in items],
        design_id=design_id,
        modifies_design=False,
        replaces_design=False,
        auto_applied=False,
    )


def get_plan_recommendation(team_id: str, design_id: str, recommendation_id: str) -> DesignRecommendationSchema:
    try:
        result = store_load(team_id, design_id, recommendation_id)
    except StoreRecommendationNotFound as exc:
        raise ApiRecommendationNotFound(recommendation_id) from exc
    return DesignRecommendationSchema(**result.to_dict())


def promote_recommendation(team_id: str, request: RecommendationPromoteRequest) -> ScenarioCreateResponse:
    """Save the suggested overlay as a named scenario. Does not apply it to the passport."""
    return create_scenario(
        team_id,
        ScenarioCreateRequest(
            design=request.design,
            name=request.name.strip(),
            params=request.params,
            persist=request.persist,
        ),
    )
