"""Engineering scenario overlays (BDX-016).

Compare diameter / grid / powder-factor alternatives without modifying the
approved BlastDesign. Not a multi-objective optimiser (BDX-017) and not an
ML recommendation engine (BDX-018).
"""
from design.scenarios.compare import compare_scenarios
from design.scenarios.engine import (
    InvalidScenarioParamsError,
    apply_params,
    build_and_evaluate,
    clone_design,
    evaluate_overlay,
    holes_loads_payload,
    revision_sha256,
)
from design.scenarios.persistence import (
    DesignScenarioNotFoundError,
    delete_scenario,
    list_scenarios,
    load_scenario,
    new_scenario_id,
    save_scenario,
)
from design.scenarios.types import (
    APPLIED_AS,
    COMPARE_METRICS,
    KIND_APPROVED,
    KIND_OVERLAY,
    DesignScenario,
    ScenarioOutcomes,
    ScenarioParams,
    ScenarioSummary,
)

__all__ = [
    "APPLIED_AS",
    "COMPARE_METRICS",
    "KIND_APPROVED",
    "KIND_OVERLAY",
    "DesignScenario",
    "DesignScenarioNotFoundError",
    "InvalidScenarioParamsError",
    "ScenarioOutcomes",
    "ScenarioParams",
    "ScenarioSummary",
    "apply_params",
    "build_and_evaluate",
    "clone_design",
    "compare_scenarios",
    "delete_scenario",
    "evaluate_overlay",
    "holes_loads_payload",
    "list_scenarios",
    "load_scenario",
    "new_scenario_id",
    "revision_sha256",
    "save_scenario",
]
