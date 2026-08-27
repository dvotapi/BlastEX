"""Evaluate a discrete grid of overlays and return the Pareto set.

Uses BDX-016 ``build_and_evaluate``. The approved design is cloned per
candidate and checked after every evaluation. This is not an RL policy and
does not write the chosen overlay back into the passport.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from design.models import BlastDesign
from design.optimization.pareto import mark_pareto, pick_compromise
from design.optimization.space import (
    InvalidSearchSpaceError,
    build_space,
    enumerate_vectors,
)
from design.optimization.types import (
    APPLIED_AS,
    DEFAULT_MAX_CANDIDATES,
    DEFAULT_OBJECTIVES,
    DEFAULT_TARGET_X50_MM,
    KIND_BASELINE,
    KIND_CANDIDATE,
    METHOD_DETERMINISTIC_PARETO,
    OBJECTIVE_SPECS,
    ROLE_DESIGNED,
    ROLE_PREDICTED,
    DecisionVector,
    ObjectiveScore,
    OptimizationCandidate,
    OptimizationResult,
    VariableBound,
)
from design.scenarios.engine import (
    InvalidScenarioParamsError,
    build_and_evaluate,
    evaluate_overlay,
    holes_loads_payload,
    revision_sha256,
)
from design.scenarios.types import ScenarioOutcomes, ScenarioParams

CostFn = Callable[[BlastDesign, ScenarioParams, ScenarioOutcomes], None]

_OBJECTIVE_BY_KEY = {item["key"]: item for item in OBJECTIVE_SPECS}


class OptimizationError(ValueError):
    """Search request cannot be evaluated."""


def new_run_id() -> str:
    return "opt-" + uuid.uuid4().hex[:10]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _candidate_id(index: int) -> str:
    return f"cand-{index:04d}"


def compute_objectives(
    outcomes: ScenarioOutcomes,
    keys: list[str],
    target_x50_mm: float,
) -> tuple[dict[str, float | None], list[ObjectiveScore]]:
    mapping: dict[str, float | None] = {
        "cost": outcomes.total_predicted_cost_rub,
        "oversize": outcomes.oversize_pct,
        "drilling_metres": float(outcomes.drilling_metres),
        "ppv": outcomes.ppv_mm_s,
        "target_x50": None if outcomes.x50_mm is None else abs(float(outcomes.x50_mm) - float(target_x50_mm)),
    }
    if mapping["drilling_metres"] is None and outcomes.drilling_metres == 0.0:
        mapping["drilling_metres"] = 0.0
    scores: list[ObjectiveScore] = []
    selected: dict[str, float | None] = {}
    for key in keys:
        spec = _OBJECTIVE_BY_KEY.get(key)
        if spec is None:
            raise OptimizationError(f"Неизвестная цель «{key}».")
        value = mapping.get(key)
        selected[key] = value
        scores.append(
            ObjectiveScore(
                key=key,
                value=value,
                unit=spec["unit"],
                role=ROLE_PREDICTED,
                sense=spec["sense"],
            )
        )
    return selected, scores


def _feasible(
    objectives: dict[str, float | None],
    keys: list[str],
    constraints: dict[str, float | None],
    outcomes: ScenarioOutcomes,
) -> bool:
    if any(objectives.get(key) is None for key in keys):
        return False
    max_ppv = constraints.get("max_ppv_mm_s")
    if max_ppv is not None and outcomes.ppv_mm_s is not None and outcomes.ppv_mm_s > max_ppv:
        return False
    max_oversize = constraints.get("max_oversize_pct")
    if max_oversize is not None and outcomes.oversize_pct is not None and outcomes.oversize_pct > max_oversize:
        return False
    max_cost = constraints.get("max_cost_rub")
    if max_cost is not None and outcomes.total_predicted_cost_rub is not None:
        if outcomes.total_predicted_cost_rub > max_cost:
            return False
    return True


def _evaluate_one(
    *,
    design: BlastDesign,
    params: ScenarioParams,
    decision: DecisionVector,
    candidate_id: str,
    kind: str,
    objective_keys: list[str],
    target_x50_mm: float,
    constraints: dict[str, float | None],
    cost_fn: CostFn | None,
    approved_before: dict[str, Any],
    source_hash: str,
) -> OptimizationCandidate:
    if kind == KIND_BASELINE:
        from design.scenarios.engine import clone_design

        overlay = clone_design(design)
        outcomes = evaluate_overlay(overlay, params)
        overlay_hash = revision_sha256(overlay)
        eval_source = source_hash
    else:
        overlay, outcomes, eval_source, overlay_hash = build_and_evaluate(design, params)
    if cost_fn is not None:
        cost_fn(overlay, params, outcomes)
    if holes_loads_payload(design) != approved_before or revision_sha256(design) != source_hash:
        raise RuntimeError("Оптимизация изменила утверждённый паспорт — это запрещено.")
    if eval_source != source_hash:
        raise RuntimeError("Хеш исходного паспорта не совпал после оценки кандидата.")
    objectives, scores = compute_objectives(outcomes, objective_keys, target_x50_mm)
    warnings = list(outcomes.warnings)
    return OptimizationCandidate(
        candidate_id=candidate_id,
        params=params,
        outcomes=outcomes,
        decision=decision,
        objectives=objectives,
        scores=scores,
        feasible=_feasible(objectives, objective_keys, constraints, outcomes),
        kind=kind,
        overlay_revision_sha256=overlay_hash,
        source_revision_sha256=source_hash,
        warnings=warnings,
        applied_as=APPLIED_AS,
        modifies_design=False,
        role=ROLE_PREDICTED,
    )


def optimize(
    design: BlastDesign,
    bounds: list[VariableBound],
    *,
    objectives: list[str] | None = None,
    target_x50_mm: float = DEFAULT_TARGET_X50_MM,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    include_baseline: bool = True,
    base_params: ScenarioParams | None = None,
    constraints: dict[str, float | None] | None = None,
    cost_fn: CostFn | None = None,
    run_id: str | None = None,
) -> OptimizationResult:
    """Deterministic grid search + Pareto. Does not persist and does not save the design."""
    if not design.holes:
        raise OptimizationError("В паспорте нет скважин — оптимизировать нечего.")
    if float(target_x50_mm) <= 0:
        raise OptimizationError("Целевой X50 должен быть больше нуля (мм).")
    keys = [item for item in (objectives or list(DEFAULT_OBJECTIVES)) if item]
    unknown = [key for key in keys if key not in _OBJECTIVE_BY_KEY]
    if unknown:
        raise OptimizationError(f"Неизвестные цели: {', '.join(unknown)}.")
    if not keys:
        raise OptimizationError("Задайте хотя бы одну цель.")

    source_hash = revision_sha256(design)
    approved_before = holes_loads_payload(design)
    base = base_params or ScenarioParams()
    try:
        space = build_space(bounds)
        vectors = enumerate_vectors(space, max_candidates)
    except InvalidSearchSpaceError as exc:
        raise OptimizationError(str(exc)) from exc

    limits = constraints or {}
    candidates: list[OptimizationCandidate] = []
    warnings: list[str] = []
    skipped = 0
    index = 1

    if include_baseline:
        baseline = _evaluate_one(
            design=design,
            params=base,
            decision=DecisionVector(values={}),
            candidate_id=_candidate_id(index),
            kind=KIND_BASELINE,
            objective_keys=keys,
            target_x50_mm=target_x50_mm,
            constraints=limits,
            cost_fn=cost_fn,
            approved_before=approved_before,
            source_hash=source_hash,
        )
        candidates.append(baseline)
        index += 1

    for vector in vectors:
        params = vector.to_params(base)
        try:
            candidate = _evaluate_one(
                design=design,
                params=params,
                decision=vector,
                candidate_id=_candidate_id(index),
                kind=KIND_CANDIDATE,
                objective_keys=keys,
                target_x50_mm=target_x50_mm,
                constraints=limits,
                cost_fn=cost_fn,
                approved_before=approved_before,
                source_hash=source_hash,
            )
        except InvalidScenarioParamsError as exc:
            skipped += 1
            warnings.append(str(exc))
            index += 1
            continue
        candidates.append(candidate)
        index += 1

    if holes_loads_payload(design) != approved_before:
        raise RuntimeError("Оптимизация изменила утверждённый паспорт — это запрещено.")

    front = mark_pareto(candidates, keys)
    compromise = pick_compromise(front, keys)
    if not front:
        warnings.append("Парето-фронт пуст: ни один кандидат не получил полный набор прогнозных целей.")

    return OptimizationResult(
        run_id=run_id or new_run_id(),
        design_id=design.design_id,
        candidates=candidates,
        pareto_front=front,
        compromise_candidate_id=compromise.candidate_id if compromise else None,
        objectives=keys,
        target_x50_mm=float(target_x50_mm),
        evaluated=len(candidates),
        feasible=sum(1 for item in candidates if item.feasible),
        skipped=skipped,
        method=METHOD_DETERMINISTIC_PARETO,
        uses_rl=False,
        replaces_design=False,
        modifies_design=False,
        applied_as=APPLIED_AS,
        source_design_role=ROLE_DESIGNED,
        candidate_role=ROLE_PREDICTED,
        source_revision_sha256=source_hash,
        approved_unchanged=True,
        created_at=_utc_now_iso(),
        warnings=warnings,
        space=space,
    )
