"""Deterministic multi-objective search (BDX-017).

Candidates are BDX-016 scenario overlays. The approved BlastDesign is not
replaced. This is not an RL trainer and not an ML recommendation engine
(BDX-018).
"""
from design.optimization.engine import OptimizationError, new_run_id, optimize
from design.optimization.pareto import dominates, mark_pareto, pick_compromise
from design.optimization.persistence import (
    OptimizationNotFoundError,
    list_runs,
    load_run,
    save_run,
)
from design.optimization.space import InvalidSearchSpaceError, build_space, enumerate_vectors
from design.optimization.types import (
    APPLIED_AS,
    DEFAULT_OBJECTIVES,
    METHOD_DETERMINISTIC_PARETO,
    OBJECTIVE_SPECS,
    VARIABLE_SPECS,
    DecisionVector,
    OptimizationCandidate,
    OptimizationResult,
    VariableBound,
)

__all__ = [
    "APPLIED_AS",
    "DEFAULT_OBJECTIVES",
    "METHOD_DETERMINISTIC_PARETO",
    "OBJECTIVE_SPECS",
    "VARIABLE_SPECS",
    "DecisionVector",
    "InvalidSearchSpaceError",
    "OptimizationCandidate",
    "OptimizationError",
    "OptimizationNotFoundError",
    "OptimizationResult",
    "VariableBound",
    "build_space",
    "dominates",
    "enumerate_vectors",
    "list_runs",
    "load_run",
    "mark_pareto",
    "new_run_id",
    "optimize",
    "pick_compromise",
    "save_run",
]
