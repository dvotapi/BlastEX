"""Multi-objective search entities (BDX-017).

Candidates are scenario overlays. Scores are PREDICTED engineering outcomes.
The approved DESIGNED passport is never replaced or rewritten.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from design.scenarios.types import ScenarioOutcomes, ScenarioParams

APPLIED_AS = "optimization_overlay"
METHOD_DETERMINISTIC_PARETO = "deterministic_search_pareto"
ROLE_PREDICTED = "predicted"
ROLE_DESIGNED = "designed"
KIND_CANDIDATE = "optimization_candidate"
KIND_BASELINE = "approved_baseline"

VARIABLE_SPECS: tuple[dict[str, str], ...] = (
    {"key": "diameter_mm", "label": "Диаметр", "unit": "мм", "kind": "float"},
    {"key": "burden_b_m", "label": "ЛНС", "unit": "м", "kind": "float"},
    {"key": "spacing_a_m", "label": "Шаг", "unit": "м", "kind": "float"},
    {"key": "subdrill_m", "label": "Перебур", "unit": "м", "kind": "float"},
    {"key": "stemming_m", "label": "Забойка", "unit": "м", "kind": "float"},
    {"key": "explosive_key", "label": "Тип ВВ", "unit": "", "kind": "categorical"},
    {"key": "inclination_deg", "label": "Наклон", "unit": "°", "kind": "float"},
    {"key": "delay_interval_ms", "label": "Замедление", "unit": "мс", "kind": "float"},
)

OBJECTIVE_SPECS: tuple[dict[str, str], ...] = (
    {
        "key": "cost",
        "metric": "total_predicted_cost_rub",
        "label": "Затраты",
        "unit": "₽",
        "sense": "min",
    },
    {
        "key": "oversize",
        "metric": "oversize_pct",
        "label": "Негабарит",
        "unit": "%",
        "sense": "min",
    },
    {
        "key": "drilling_metres",
        "metric": "drilling_metres",
        "label": "Погонаж бурения",
        "unit": "м",
        "sense": "min",
    },
    {
        "key": "ppv",
        "metric": "ppv_mm_s",
        "label": "PPV",
        "unit": "мм/с",
        "sense": "min",
    },
    {
        "key": "target_x50",
        "metric": "x50_mm",
        "label": "Отклонение от целевого X50",
        "unit": "мм",
        "sense": "min_abs_target",
    },
)

VARIABLE_KEYS = frozenset(item["key"] for item in VARIABLE_SPECS)
OBJECTIVE_KEYS = frozenset(item["key"] for item in OBJECTIVE_SPECS)
DEFAULT_OBJECTIVES: tuple[str, ...] = ("cost", "oversize", "drilling_metres", "ppv", "target_x50")
DEFAULT_TARGET_X50_MM = 200.0
DEFAULT_MAX_CANDIDATES = 36


def _opt_float(data: dict[str, Any], key: str) -> float | None:
    raw = data.get(key)
    if raw is None or raw == "":
        return None
    return float(raw)


@dataclass
class VariableAxis:
    """One discrete decision axis. Units stay as declared — never converted."""

    name: str
    values: list[Any]
    unit: str = ""
    kind: str = "float"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "values": list(self.values),
            "unit": self.unit,
            "kind": self.kind,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> VariableAxis:
        data = data or {}
        return cls(
            name=str(data.get("name") or ""),
            values=list(data.get("values") or []),
            unit=str(data.get("unit") or ""),
            kind=str(data.get("kind") or "float"),
        )


@dataclass
class VariableBound:
    """User-facing axis: explicit values or min/max/step in the declared unit."""

    name: str
    values: list[Any] = field(default_factory=list)
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "values": list(self.values),
            "minimum": self.minimum,
            "maximum": self.maximum,
            "step": self.step,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> VariableBound:
        data = data or {}
        raw_values = data.get("values") or []
        return cls(
            name=str(data.get("name") or data.get("key") or ""),
            values=list(raw_values),
            minimum=_opt_float(data, "minimum") if data.get("minimum") is not None else _opt_float(data, "min"),
            maximum=_opt_float(data, "maximum") if data.get("maximum") is not None else _opt_float(data, "max"),
            step=_opt_float(data, "step"),
        )


@dataclass
class DecisionVector:
    """One point in the discrete search space."""

    values: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"values": dict(self.values)}

    def to_params(self, base: ScenarioParams | None = None) -> ScenarioParams:
        payload = base.to_dict() if base is not None else {}
        mapping = {
            "diameter_mm": "diameter_mm",
            "burden_b_m": "burden_b_m",
            "spacing_a_m": "spacing_a_m",
            "subdrill_m": "subdrill_m",
            "stemming_m": "stemming_m",
            "explosive_key": "explosive_key",
            "inclination_deg": "inclination_deg",
            "delay_interval_ms": "delay_interval_ms",
        }
        for axis, field_name in mapping.items():
            if axis in self.values and self.values[axis] not in (None, ""):
                payload[field_name] = self.values[axis]
        return ScenarioParams.from_dict(payload)

    def fingerprint(self) -> str:
        items = []
        for key in sorted(self.values):
            items.append(f"{key}={self.values[key]}")
        return "|".join(items)


@dataclass
class ObjectiveScore:
    key: str
    value: float | None
    unit: str
    role: str = ROLE_PREDICTED
    sense: str = "min"

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "unit": self.unit,
            "role": self.role,
            "sense": self.sense,
        }


@dataclass
class OptimizationCandidate:
    """Evaluated overlay. Never written into the approved BlastDesign."""

    candidate_id: str
    params: ScenarioParams
    outcomes: ScenarioOutcomes
    decision: DecisionVector = field(default_factory=DecisionVector)
    objectives: dict[str, float | None] = field(default_factory=dict)
    scores: list[ObjectiveScore] = field(default_factory=list)
    feasible: bool = True
    on_pareto: bool = False
    pareto_rank: int = 0
    kind: str = KIND_CANDIDATE
    overlay_revision_sha256: str = ""
    source_revision_sha256: str = ""
    warnings: list[str] = field(default_factory=list)
    applied_as: str = APPLIED_AS
    modifies_design: bool = False
    role: str = ROLE_PREDICTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "params": self.params.to_dict(),
            "outcomes": self.outcomes.to_dict(),
            "decision": self.decision.to_dict(),
            "objectives": dict(self.objectives),
            "scores": [item.to_dict() for item in self.scores],
            "feasible": self.feasible,
            "on_pareto": self.on_pareto,
            "pareto_rank": self.pareto_rank,
            "kind": self.kind,
            "overlay_revision_sha256": self.overlay_revision_sha256,
            "source_revision_sha256": self.source_revision_sha256,
            "warnings": list(self.warnings),
            "applied_as": APPLIED_AS,
            "modifies_design": False,
            "role": self.role,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> OptimizationCandidate:
        data = data or {}
        scores = [
            ObjectiveScore(
                key=str(item.get("key") or ""),
                value=_opt_float(item, "value") if isinstance(item, dict) else None,
                unit=str(item.get("unit") or ""),
                role=str(item.get("role") or ROLE_PREDICTED),
                sense=str(item.get("sense") or "min"),
            )
            for item in data.get("scores") or []
            if isinstance(item, dict)
        ]
        raw_objectives = data.get("objectives") or {}
        return cls(
            candidate_id=str(data.get("candidate_id") or ""),
            params=ScenarioParams.from_dict(data.get("params")),
            outcomes=ScenarioOutcomes.from_dict(data.get("outcomes")),
            decision=DecisionVector(values=dict((data.get("decision") or {}).get("values") or {})),
            objectives={str(key): (None if raw is None else float(raw)) for key, raw in dict(raw_objectives).items()},
            scores=scores,
            feasible=bool(data.get("feasible", True)),
            on_pareto=bool(data.get("on_pareto", False)),
            pareto_rank=int(data.get("pareto_rank") or 0),
            kind=str(data.get("kind") or KIND_CANDIDATE),
            overlay_revision_sha256=str(data.get("overlay_revision_sha256") or ""),
            source_revision_sha256=str(data.get("source_revision_sha256") or ""),
            warnings=[str(item) for item in data.get("warnings", [])],
            applied_as=APPLIED_AS,
            modifies_design=False,
            role=str(data.get("role") or ROLE_PREDICTED),
        )


@dataclass
class OptimizationResult:
    """Search report. The approved design stays DESIGNED and unchanged."""

    run_id: str
    design_id: str
    candidates: list[OptimizationCandidate] = field(default_factory=list)
    pareto_front: list[OptimizationCandidate] = field(default_factory=list)
    compromise_candidate_id: str | None = None
    objectives: list[str] = field(default_factory=lambda: list(DEFAULT_OBJECTIVES))
    target_x50_mm: float = DEFAULT_TARGET_X50_MM
    evaluated: int = 0
    feasible: int = 0
    skipped: int = 0
    method: str = METHOD_DETERMINISTIC_PARETO
    uses_rl: bool = False
    replaces_design: bool = False
    modifies_design: bool = False
    applied_as: str = APPLIED_AS
    source_design_role: str = ROLE_DESIGNED
    candidate_role: str = ROLE_PREDICTED
    source_revision_sha256: str = ""
    approved_unchanged: bool = True
    created_at: str = ""
    warnings: list[str] = field(default_factory=list)
    space: list[VariableAxis] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "design_id": self.design_id,
            "candidates": [item.to_dict() for item in self.candidates],
            "pareto_front": [item.to_dict() for item in self.pareto_front],
            "compromise_candidate_id": self.compromise_candidate_id,
            "objectives": list(self.objectives),
            "target_x50_mm": self.target_x50_mm,
            "evaluated": self.evaluated,
            "feasible": self.feasible,
            "skipped": self.skipped,
            "method": METHOD_DETERMINISTIC_PARETO,
            "uses_rl": False,
            "replaces_design": False,
            "modifies_design": False,
            "applied_as": APPLIED_AS,
            "source_design_role": ROLE_DESIGNED,
            "candidate_role": ROLE_PREDICTED,
            "source_revision_sha256": self.source_revision_sha256,
            "approved_unchanged": True,
            "created_at": self.created_at,
            "warnings": list(self.warnings),
            "space": [item.to_dict() for item in self.space],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> OptimizationResult:
        data = data or {}
        candidates = [OptimizationCandidate.from_dict(item) for item in data.get("candidates") or []]
        front_ids = {
            str(item.get("candidate_id") or "")
            for item in data.get("pareto_front") or []
            if isinstance(item, dict)
        }
        by_id = {item.candidate_id: item for item in candidates}
        front = [by_id[item_id] for item_id in front_ids if item_id in by_id]
        if not front:
            front = [OptimizationCandidate.from_dict(item) for item in data.get("pareto_front") or []]
        return cls(
            run_id=str(data.get("run_id") or ""),
            design_id=str(data.get("design_id") or ""),
            candidates=candidates,
            pareto_front=front,
            compromise_candidate_id=str(data["compromise_candidate_id"]) if data.get("compromise_candidate_id") else None,
            objectives=[str(item) for item in data.get("objectives") or list(DEFAULT_OBJECTIVES)],
            target_x50_mm=float(data.get("target_x50_mm") or DEFAULT_TARGET_X50_MM),
            evaluated=int(data.get("evaluated") or 0),
            feasible=int(data.get("feasible") or 0),
            skipped=int(data.get("skipped") or 0),
            method=METHOD_DETERMINISTIC_PARETO,
            uses_rl=False,
            replaces_design=False,
            modifies_design=False,
            applied_as=APPLIED_AS,
            source_design_role=ROLE_DESIGNED,
            candidate_role=ROLE_PREDICTED,
            source_revision_sha256=str(data.get("source_revision_sha256") or ""),
            approved_unchanged=True,
            created_at=str(data.get("created_at") or ""),
            warnings=[str(item) for item in data.get("warnings", [])],
            space=[VariableAxis.from_dict(item) for item in data.get("space") or []],
        )
