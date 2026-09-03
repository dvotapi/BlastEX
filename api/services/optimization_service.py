"""Run deterministic Pareto search on overlays. Never writes the approved passport."""
from __future__ import annotations

from typing import Any

from api.exceptions import (
    DesignNotFoundError,
    InvalidDesignError,
    InvalidOptimizationError,
    OptimizationNotFoundError as ApiOptimizationNotFound,
)
from api.schemas.design import BlastDesignSchema, DesignCostRequest
from api.schemas.optimization import (
    OptimizationListResponse,
    OptimizationPromoteRequest,
    OptimizationRequest,
    OptimizationResultSchema,
    OptimizationRunSummarySchema,
)
from api.schemas.scenarios import ScenarioCreateRequest, ScenarioCreateResponse, ScenarioParamsSchema
from api.services.design_service import estimate_design_cost
from api.services.scenario_service import create_scenario
from cost.v2.legacy_adapter import default_legacy_references
from design.models import BlastDesign
from design.optimization.engine import OptimizationError, optimize
from design.optimization.persistence import (
    OptimizationNotFoundError as StoreOptimizationNotFound,
)
from design.optimization.persistence import list_runs as store_list
from design.optimization.persistence import load_run as store_load
from design.optimization.persistence import save_run
from design.optimization.types import VariableBound
from design.persistence import DesignNotFoundError as StoreDesignNotFound
from design.persistence import load_design
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
    # Справочники — фиксированные значения Cost V1 по умолчанию, а не опубликованная
    # ревизия организации: этот ML-сервис читает per-org справочники не через это поле.
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


def run_optimization(team_id: str, request: OptimizationRequest) -> OptimizationResultSchema:
    design = _design_from_schema(request.design)
    if not design.holes:
        raise InvalidOptimizationError("В паспорте нет скважин — оптимизировать нечего.")
    approved_before = holes_loads_payload(design)
    source_hash = revision_sha256(design)
    bounds = [VariableBound.from_dict(item.model_dump()) for item in request.variables]
    params = ScenarioParams.from_dict(request.params.model_dump())
    constraints = {
        "max_ppv_mm_s": request.constraints.max_ppv_mm_s,
        "max_oversize_pct": request.constraints.max_oversize_pct,
        "max_cost_rub": request.constraints.max_cost_rub,
    }
    try:
        result = optimize(
            design,
            bounds,
            objectives=list(request.objectives),
            target_x50_mm=float(request.target_x50_mm),
            max_candidates=int(request.max_candidates),
            include_baseline=bool(request.include_baseline),
            base_params=params,
            constraints=constraints,
            cost_fn=_apply_cost,
        )
    except OptimizationError as exc:
        raise InvalidOptimizationError(str(exc)) from exc

    _assert_unchanged(approved_before, design, "Оптимизация")
    if revision_sha256(design) != source_hash:
        raise InvalidDesignError("Оптимизация изменила утверждённый паспорт.")

    if request.persist:
        if not design.design_id:
            raise InvalidOptimizationError("Для сохранения прогона у паспорта должен быть design_id.")
        save_run(team_id, result)
        try:
            stored = load_design(team_id, design.design_id)
            _assert_unchanged(approved_before, stored, "Сохранение прогона оптимизации")
        except StoreDesignNotFound:
            pass

    if request.persist_pareto_as_scenarios:
        if not design.design_id:
            raise InvalidOptimizationError("Для сохранения фронта у паспорта должен быть design_id.")
        for index, candidate in enumerate(result.pareto_front, start=1):
            create_scenario(
                team_id,
                ScenarioCreateRequest(
                    design=request.design,
                    name=f"Парето {index}",
                    params=ScenarioParamsSchema(**candidate.params.to_dict()),
                    persist=True,
                ),
            )
        _assert_unchanged(approved_before, design, "Сохранение Парето как сценариев")

    payload = result.to_dict()
    payload["approved_unchanged"] = True
    return OptimizationResultSchema(**payload)


def list_plan_runs(team_id: str, design_id: str) -> OptimizationListResponse:
    items = store_list(team_id, design_id)
    return OptimizationListResponse(
        items=[OptimizationRunSummarySchema(**item) for item in items],
        design_id=design_id,
        modifies_design=False,
        replaces_design=False,
    )


def get_plan_run(team_id: str, design_id: str, run_id: str) -> OptimizationResultSchema:
    try:
        result = store_load(team_id, design_id, run_id)
    except StoreOptimizationNotFound as exc:
        raise ApiOptimizationNotFound(run_id) from exc
    return OptimizationResultSchema(**result.to_dict())


def promote_candidate(team_id: str, request: OptimizationPromoteRequest) -> ScenarioCreateResponse:
    """Save one overlay as a named scenario. Does not apply it to the passport."""
    created = create_scenario(
        team_id,
        ScenarioCreateRequest(
            design=request.design,
            name=request.name.strip(),
            params=request.params,
            persist=request.persist,
        ),
    )
    return created
