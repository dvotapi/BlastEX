"""Create, list and compare design overlays. Never writes the approved passport."""
from __future__ import annotations

from typing import Any

from api.exceptions import (
    DesignNotFoundError,
    DesignScenarioNotFoundError as ApiScenarioNotFound,
    InvalidDesignError,
    InvalidDesignScenarioError,
)
from api.schemas.design import BlastDesignSchema, DesignCostRequest
from api.schemas.scenarios import (
    DesignScenarioSchema,
    ScenarioCompareRequest,
    ScenarioCompareResponse,
    ScenarioCreateRequest,
    ScenarioCreateResponse,
    ScenarioListResponse,
    ScenarioSummarySchema,
)
from api.services.design_service import estimate_design_cost
from cost.v2.legacy_adapter import default_legacy_references
from design.models import BlastDesign
from design.persistence import DesignNotFoundError as StoreDesignNotFound
from design.persistence import load_design
from design.scenarios.compare import compare_scenarios
from design.scenarios.engine import (
    InvalidScenarioParamsError,
    build_and_evaluate,
    clone_design,
    evaluate_overlay,
    holes_loads_payload,
    resolved_geometry,
    revision_sha256,
)
from design.scenarios.persistence import (
    DesignScenarioNotFoundError as StoreScenarioNotFound,
)
from design.scenarios.persistence import (
    list_scenarios as store_list,
    load_scenario as store_load,
    new_scenario_id,
    save_scenario,
)
from design.scenarios.types import (
    APPLIED_AS,
    KIND_APPROVED,
    KIND_OVERLAY,
    SOURCE_CALIBRATION,
    SOURCE_ML_OVERLAY,
    DesignScenario,
    ScenarioOutcomes,
    ScenarioParams,
)

APPROVED_SCENARIO_ID = "approved"


def _design_from_schema(schema: BlastDesignSchema) -> BlastDesign:
    return BlastDesign.from_dict(schema.model_dump())


def _assert_unchanged(before: dict[str, Any], design: BlastDesign, action: str) -> None:
    after = holes_loads_payload(design)
    if after != before:
        raise InvalidDesignError(
            f"{action} не должно менять проектные скважины и заряды утверждённого паспорта."
        )


def _scenario_schema(item: DesignScenario) -> DesignScenarioSchema:
    return DesignScenarioSchema(**item.to_dict())


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


def _overlay_target(prediction, name: str) -> float | None:
    if prediction is None:
        return None
    item = prediction.predictions.get(name) if hasattr(prediction, "predictions") else None
    if item is None or not getattr(prediction, "prediction_applied", False):
        return None
    value = getattr(item, "value", None)
    return None if value is None else float(value)


def _apply_ml_overlays(
    team_id: str,
    overlay: BlastDesign,
    params: ScenarioParams,
    outcomes: ScenarioOutcomes,
) -> None:
    wants_ml = bool(params.use_production_overlays or params.outcome_model_ids or params.calibration_model_ids)
    if not wants_ml or not team_id:
        return
    applied = False
    site_id = (params.site_id or "").strip()
    try:
        from api.schemas.outcomes import OutcomePredictAllRequest
        from api.services import outcome_service
        from intelligence.outcomes.types import TARGET_OVERSIZE, TARGET_PPV, TARGET_X50, TARGET_X80

        panel = outcome_service.predict_panel(
            team_id,
            OutcomePredictAllRequest(
                site_id=site_id,
                use_production=params.use_production_overlays,
                model_ids=dict(params.outcome_model_ids),
                design=BlastDesignSchema(**overlay.to_dict()),
            ),
        )
        frag = panel.models.get("fragmentation")
        oversize = panel.models.get("oversize")
        vibration = panel.models.get("vibration")
        x50 = _overlay_target(frag, TARGET_X50)
        x80 = _overlay_target(frag, TARGET_X80)
        oversize_pct = _overlay_target(oversize, TARGET_OVERSIZE)
        ppv = _overlay_target(vibration, TARGET_PPV)
        if x50 is not None:
            outcomes.x50_mm = x50
            outcomes.fragmentation_source = SOURCE_ML_OVERLAY
            applied = True
        if x80 is not None:
            outcomes.x80_mm = x80
            outcomes.fragmentation_source = SOURCE_ML_OVERLAY
            applied = True
        if oversize_pct is not None:
            outcomes.oversize_pct = oversize_pct
            applied = True
        if ppv is not None:
            outcomes.ppv_mm_s = ppv
            outcomes.vibration_source = SOURCE_ML_OVERLAY
            applied = True
        for warning in panel.warnings[:3]:
            if warning not in outcomes.warnings:
                outcomes.warnings.append(warning)
    except Exception as exc:
        outcomes.warnings.append(f"ML-оверлей исходов пропущен: {exc}")

    try:
        from intelligence.calibration.persistence import load_model, production_model
        from intelligence.calibration.prediction import apply_residual, features_from_design
        from intelligence.calibration.types import (
            MODEL_KUZRAM_RESIDUAL,
            MODEL_OVERSIZE_RESIDUAL,
            MODEL_PPV_RESIDUAL,
        )

        features = features_from_design(overlay, site_id=site_id or "unknown")
        mapping = (
            (MODEL_KUZRAM_RESIDUAL, "x50_mm", "x50_engineering_mm"),
            (MODEL_OVERSIZE_RESIDUAL, "oversize_pct", "oversize_engineering_pct"),
            (MODEL_PPV_RESIDUAL, "ppv_mm_s", "ppv_engineering_mm_s"),
        )
        for model_type, field, baseline_field in mapping:
            model_id = str(params.calibration_model_ids.get(model_type) or "").strip()
            model = None
            if model_id:
                model = load_model(team_id, model_id)
            elif params.use_production_overlays and site_id:
                model = production_model(team_id, site_id, model_type)
            if model is None:
                continue
            baseline = getattr(outcomes, baseline_field)
            if baseline is None:
                continue
            prediction = apply_residual(
                model,
                features=features,
                baseline=float(baseline),
                baseline_source="engineering",
            )
            calibrated = float(prediction.calibrated)
            setattr(outcomes, field, calibrated)
            applied = True
            if field in {"x50_mm", "x80_mm"}:
                outcomes.fragmentation_source = SOURCE_CALIBRATION
            if field == "ppv_mm_s":
                outcomes.vibration_source = SOURCE_CALIBRATION
    except Exception as exc:
        outcomes.warnings.append(f"Калибровочный оверлей пропущен: {exc}")

    outcomes.ml_overlay_applied = applied


def _build_scenario(
    *,
    team_id: str,
    design: BlastDesign,
    name: str,
    params: ScenarioParams,
    kind: str,
    scenario_id: str,
) -> tuple[DesignScenario, BlastDesign]:
    overlay, outcomes, source_hash, overlay_hash = build_and_evaluate(design, params)
    _apply_cost(overlay, params, outcomes)
    _apply_ml_overlays(team_id, overlay, params, outcomes)
    geometry = resolved_geometry(overlay, params)
    outcomes.diameter_mm = geometry["diameter_mm"]
    outcomes.spacing_a_m = geometry["spacing_a_m"]
    outcomes.burden_b_m = geometry["burden_b_m"]
    scenario = DesignScenario(
        scenario_id=scenario_id,
        design_id=design.design_id,
        name=name,
        params=params,
        outcomes=outcomes,
        kind=kind,
        source_design_updated_at=design.updated_at,
        source_revision_sha256=source_hash,
        overlay_revision_sha256=overlay_hash,
        modifies_design=False,
        applied_as=APPLIED_AS,
    )
    return scenario, overlay


def create_scenario(team_id: str, request: ScenarioCreateRequest) -> ScenarioCreateResponse:
    design = _design_from_schema(request.design)
    if not design.holes:
        raise InvalidDesignScenarioError("В паспорте нет скважин — сценарий строить не из чего.")
    approved_before = holes_loads_payload(design)
    source_hash = revision_sha256(design)
    params = ScenarioParams.from_dict(request.params.model_dump())
    try:
        scenario, _overlay = _build_scenario(
            team_id=team_id,
            design=design,
            name=request.name.strip(),
            params=params,
            kind=KIND_OVERLAY,
            scenario_id=new_scenario_id(),
        )
    except InvalidScenarioParamsError as exc:
        raise InvalidDesignScenarioError(str(exc)) from exc
    _assert_unchanged(approved_before, design, "Создание сценария")
    if revision_sha256(design) != source_hash:
        raise InvalidDesignError("Создание сценария изменило утверждённый паспорт.")

    if request.persist:
        if not design.design_id:
            raise InvalidDesignScenarioError("Для сохранения сценария у паспорта должен быть design_id.")
        save_scenario(team_id, scenario)
        try:
            stored = load_design(team_id, design.design_id)
            _assert_unchanged(approved_before, stored, "Сохранение сценария")
        except StoreDesignNotFound:
            # Overlay may be attached to an in-memory design that is not yet a plan.
            pass

    payload = scenario.to_dict()
    payload["approved_revision_sha256"] = source_hash
    payload["approved_unchanged"] = True
    return ScenarioCreateResponse(**payload)


def list_plan_scenarios(team_id: str, design_id: str) -> ScenarioListResponse:
    items = store_list(team_id, design_id)
    return ScenarioListResponse(
        items=[ScenarioSummarySchema(**item.to_dict()) for item in items],
        design_id=design_id,
        modifies_design=False,
    )


def get_plan_scenario(team_id: str, design_id: str, scenario_id: str) -> DesignScenarioSchema:
    try:
        scenario = store_load(team_id, design_id, scenario_id)
    except StoreScenarioNotFound as exc:
        raise ApiScenarioNotFound(scenario_id) from exc
    return _scenario_schema(scenario)


def _baseline_scenario(team_id: str, design: BlastDesign, params: ScenarioParams | None = None) -> DesignScenario:
    baseline_params = params or ScenarioParams()
    overlay = clone_design(design)
    outcomes = evaluate_overlay(overlay, baseline_params)
    _apply_cost(overlay, baseline_params, outcomes)
    _apply_ml_overlays(team_id, overlay, baseline_params, outcomes)
    geometry = resolved_geometry(overlay, baseline_params)
    outcomes.diameter_mm = geometry["diameter_mm"]
    outcomes.spacing_a_m = geometry["spacing_a_m"]
    outcomes.burden_b_m = geometry["burden_b_m"]
    return DesignScenario(
        scenario_id=APPROVED_SCENARIO_ID,
        design_id=design.design_id,
        name="Утверждённый проект",
        params=baseline_params,
        outcomes=outcomes,
        kind=KIND_APPROVED,
        source_design_updated_at=design.updated_at,
        source_revision_sha256=revision_sha256(design),
        overlay_revision_sha256=revision_sha256(overlay),
        modifies_design=False,
        applied_as=APPLIED_AS,
    )


def compare_plan_scenarios(team_id: str, request: ScenarioCompareRequest) -> ScenarioCompareResponse:
    design = _design_from_schema(request.design) if request.design is not None else None
    design_id = (request.design_id or (design.design_id if design else "")).strip()
    approved_before = holes_loads_payload(design) if design is not None else None

    stored: list[DesignScenario] = []
    if design_id:
        wanted = [item.strip() for item in request.scenario_ids if item.strip() and item != APPROVED_SCENARIO_ID]
        if wanted:
            for scenario_id in wanted:
                try:
                    stored.append(store_load(team_id, design_id, scenario_id))
                except StoreScenarioNotFound as exc:
                    raise ApiScenarioNotFound(scenario_id) from exc
        else:
            stored.extend(store_load(team_id, design_id, item.scenario_id) for item in store_list(team_id, design_id))

    inline = [DesignScenario.from_dict(item.model_dump()) for item in request.inline]
    scenarios = stored + inline

    if request.include_baseline:
        if design is None and design_id:
            try:
                design = load_design(team_id, design_id)
                approved_before = holes_loads_payload(design)
            except StoreDesignNotFound as exc:
                raise DesignNotFoundError(design_id) from exc
        if design is not None:
            scenarios = [_baseline_scenario(team_id, design)] + scenarios

    if not scenarios:
        raise InvalidDesignScenarioError("Нет сценариев для сравнения.")

    payload = compare_scenarios(scenarios)
    if design is not None and approved_before is not None:
        _assert_unchanged(approved_before, design, "Сравнение сценариев")
        if design_id:
            try:
                reloaded = load_design(team_id, design_id)
                _assert_unchanged(approved_before, reloaded, "Сравнение сценариев")
            except StoreDesignNotFound:
                pass
    payload["approved_unchanged"] = True
    payload["warnings"] = []
    return ScenarioCompareResponse(**payload)
