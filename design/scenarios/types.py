"""Design-scenario entity (BDX-016).

A scenario is an overlay attached to an approved BlastDesign. It stores the
engineering knobs (diameter, grid, powder factor) plus predicted outcomes and
cost. Persistence lives beside the passport, never inside it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

KIND_APPROVED = "approved"
KIND_OVERLAY = "overlay"
APPLIED_AS = "scenario_overlay"
SOURCE_ENGINEERING = "engineering"
SOURCE_ML_OVERLAY = "ml_overlay"
SOURCE_CALIBRATION = "calibration_overlay"

COMPARE_METRICS: tuple[dict[str, str], ...] = (
    {"key": "diameter_mm", "label": "Диаметр", "unit": "мм"},
    {"key": "spacing_a_m", "label": "Шаг", "unit": "м"},
    {"key": "burden_b_m", "label": "ЛНС", "unit": "м"},
    {"key": "powder_factor_kg_m3", "label": "Удельный расход q", "unit": "кг/м³"},
    {"key": "drilling_metres", "label": "Погонаж бурения", "unit": "м"},
    {"key": "explosive_mass_kg", "label": "Масса ВВ", "unit": "кг"},
    {"key": "hole_count", "label": "Число скважин", "unit": "шт"},
    {"key": "x50_mm", "label": "X50", "unit": "мм"},
    {"key": "x80_mm", "label": "X80", "unit": "мм"},
    {"key": "oversize_pct", "label": "Негабарит", "unit": "%"},
    {"key": "mic_kg", "label": "MIC", "unit": "кг"},
    {"key": "ppv_mm_s", "label": "PPV", "unit": "мм/с"},
    {"key": "direct_cost_rub", "label": "Прямые затраты", "unit": "₽"},
    {"key": "total_predicted_cost_rub", "label": "Прогнозная смета", "unit": "₽"},
)

LOWER_IS_BETTER = frozenset(
    {
        "drilling_metres",
        "explosive_mass_kg",
        "x50_mm",
        "x80_mm",
        "oversize_pct",
        "mic_kg",
        "ppv_mm_s",
        "direct_cost_rub",
        "total_predicted_cost_rub",
    }
)


def _opt_float(data: dict[str, Any], key: str) -> float | None:
    raw = data.get(key)
    if raw is None or raw == "":
        return None
    return float(raw)


@dataclass
class ScenarioParams:
    """Engineering knobs that differ from the approved passport."""

    diameter_mm: float | None = None
    spacing_a_m: float | None = None
    burden_b_m: float | None = None
    powder_factor_kg_m3: float | None = None
    stemming_m: float | None = None
    subdrill_m: float | None = None
    pattern: str | None = None
    cost_scenario_id: str = "drill_blast"
    fragmentation_model: str = "kuzram"
    lump_size_mm: float = 400.0
    mic_window_ms: float = 8.0
    vibration_model_id: str = ""
    site_id: str = ""
    use_production_overlays: bool = False
    outcome_model_ids: dict[str, str] = field(default_factory=dict)
    calibration_model_ids: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "diameter_mm": self.diameter_mm,
            "spacing_a_m": self.spacing_a_m,
            "burden_b_m": self.burden_b_m,
            "powder_factor_kg_m3": self.powder_factor_kg_m3,
            "stemming_m": self.stemming_m,
            "subdrill_m": self.subdrill_m,
            "pattern": self.pattern,
            "cost_scenario_id": self.cost_scenario_id,
            "fragmentation_model": self.fragmentation_model,
            "lump_size_mm": self.lump_size_mm,
            "mic_window_ms": self.mic_window_ms,
            "vibration_model_id": self.vibration_model_id,
            "site_id": self.site_id,
            "use_production_overlays": self.use_production_overlays,
            "outcome_model_ids": dict(self.outcome_model_ids),
            "calibration_model_ids": dict(self.calibration_model_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ScenarioParams:
        data = data or {}
        outcome_ids = data.get("outcome_model_ids") or {}
        calibration_ids = data.get("calibration_model_ids") or {}
        return cls(
            diameter_mm=_opt_float(data, "diameter_mm"),
            spacing_a_m=_opt_float(data, "spacing_a_m"),
            burden_b_m=_opt_float(data, "burden_b_m"),
            powder_factor_kg_m3=_opt_float(data, "powder_factor_kg_m3"),
            stemming_m=_opt_float(data, "stemming_m"),
            subdrill_m=_opt_float(data, "subdrill_m"),
            pattern=str(data["pattern"]).strip() if data.get("pattern") else None,
            cost_scenario_id=str(data.get("cost_scenario_id") or "drill_blast"),
            fragmentation_model=str(data.get("fragmentation_model") or "kuzram"),
            lump_size_mm=float(data.get("lump_size_mm") or 400.0),
            mic_window_ms=float(data.get("mic_window_ms") or 8.0),
            vibration_model_id=str(data.get("vibration_model_id") or ""),
            site_id=str(data.get("site_id") or ""),
            use_production_overlays=bool(data.get("use_production_overlays", False)),
            outcome_model_ids={str(key): str(value) for key, value in dict(outcome_ids).items()},
            calibration_model_ids={str(key): str(value) for key, value in dict(calibration_ids).items()},
        )


@dataclass
class ScenarioOutcomes:
    """Predicted comparison fields. None means the overlay could not compute it."""

    drilling_metres: float = 0.0
    explosive_mass_kg: float = 0.0
    powder_factor_kg_m3: float = 0.0
    hole_count: int = 0
    block_volume_m3: float = 0.0
    diameter_mm: float | None = None
    spacing_a_m: float | None = None
    burden_b_m: float | None = None
    x50_mm: float | None = None
    x80_mm: float | None = None
    oversize_pct: float | None = None
    mic_kg: float | None = None
    ppv_mm_s: float | None = None
    direct_cost_rub: float | None = None
    total_predicted_cost_rub: float | None = None
    cost_per_m3: float | None = None
    x50_engineering_mm: float | None = None
    x80_engineering_mm: float | None = None
    oversize_engineering_pct: float | None = None
    ppv_engineering_mm_s: float | None = None
    fragmentation_source: str = SOURCE_ENGINEERING
    vibration_source: str = SOURCE_ENGINEERING
    cost_source: str = SOURCE_ENGINEERING
    ml_overlay_applied: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "drilling_metres": self.drilling_metres,
            "explosive_mass_kg": self.explosive_mass_kg,
            "powder_factor_kg_m3": self.powder_factor_kg_m3,
            "hole_count": self.hole_count,
            "block_volume_m3": self.block_volume_m3,
            "diameter_mm": self.diameter_mm,
            "spacing_a_m": self.spacing_a_m,
            "burden_b_m": self.burden_b_m,
            "x50_mm": self.x50_mm,
            "x80_mm": self.x80_mm,
            "oversize_pct": self.oversize_pct,
            "mic_kg": self.mic_kg,
            "ppv_mm_s": self.ppv_mm_s,
            "direct_cost_rub": self.direct_cost_rub,
            "total_predicted_cost_rub": self.total_predicted_cost_rub,
            "cost_per_m3": self.cost_per_m3,
            "x50_engineering_mm": self.x50_engineering_mm,
            "x80_engineering_mm": self.x80_engineering_mm,
            "oversize_engineering_pct": self.oversize_engineering_pct,
            "ppv_engineering_mm_s": self.ppv_engineering_mm_s,
            "fragmentation_source": self.fragmentation_source,
            "vibration_source": self.vibration_source,
            "cost_source": self.cost_source,
            "ml_overlay_applied": self.ml_overlay_applied,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ScenarioOutcomes:
        data = data or {}
        return cls(
            drilling_metres=float(data.get("drilling_metres") or 0.0),
            explosive_mass_kg=float(data.get("explosive_mass_kg") or 0.0),
            powder_factor_kg_m3=float(data.get("powder_factor_kg_m3") or 0.0),
            hole_count=int(data.get("hole_count") or 0),
            block_volume_m3=float(data.get("block_volume_m3") or 0.0),
            diameter_mm=_opt_float(data, "diameter_mm"),
            spacing_a_m=_opt_float(data, "spacing_a_m"),
            burden_b_m=_opt_float(data, "burden_b_m"),
            x50_mm=_opt_float(data, "x50_mm"),
            x80_mm=_opt_float(data, "x80_mm"),
            oversize_pct=_opt_float(data, "oversize_pct"),
            mic_kg=_opt_float(data, "mic_kg"),
            ppv_mm_s=_opt_float(data, "ppv_mm_s"),
            direct_cost_rub=_opt_float(data, "direct_cost_rub"),
            total_predicted_cost_rub=_opt_float(data, "total_predicted_cost_rub"),
            cost_per_m3=_opt_float(data, "cost_per_m3"),
            x50_engineering_mm=_opt_float(data, "x50_engineering_mm"),
            x80_engineering_mm=_opt_float(data, "x80_engineering_mm"),
            oversize_engineering_pct=_opt_float(data, "oversize_engineering_pct"),
            ppv_engineering_mm_s=_opt_float(data, "ppv_engineering_mm_s"),
            fragmentation_source=str(data.get("fragmentation_source") or SOURCE_ENGINEERING),
            vibration_source=str(data.get("vibration_source") or SOURCE_ENGINEERING),
            cost_source=str(data.get("cost_source") or SOURCE_ENGINEERING),
            ml_overlay_applied=bool(data.get("ml_overlay_applied", False)),
            warnings=[str(item) for item in data.get("warnings", [])],
        )

    def metric_value(self, key: str) -> float | None:
        mapping = {
            "diameter_mm": self.diameter_mm,
            "spacing_a_m": self.spacing_a_m,
            "burden_b_m": self.burden_b_m,
            "powder_factor_kg_m3": self.powder_factor_kg_m3,
            "drilling_metres": self.drilling_metres,
            "explosive_mass_kg": self.explosive_mass_kg,
            "hole_count": float(self.hole_count),
            "x50_mm": self.x50_mm,
            "x80_mm": self.x80_mm,
            "oversize_pct": self.oversize_pct,
            "mic_kg": self.mic_kg,
            "ppv_mm_s": self.ppv_mm_s,
            "direct_cost_rub": self.direct_cost_rub,
            "total_predicted_cost_rub": self.total_predicted_cost_rub,
        }
        value = mapping.get(key)
        if value is None:
            return None
        return float(value)


@dataclass
class DesignScenario:
    """Named overlay attached to a design_id. Never written into BlastDesign."""

    scenario_id: str
    design_id: str
    name: str
    params: ScenarioParams = field(default_factory=ScenarioParams)
    outcomes: ScenarioOutcomes = field(default_factory=ScenarioOutcomes)
    kind: str = KIND_OVERLAY
    source_design_updated_at: str = ""
    source_revision_sha256: str = ""
    overlay_revision_sha256: str = ""
    created_at: str = ""
    modifies_design: bool = False
    applied_as: str = APPLIED_AS

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "design_id": self.design_id,
            "name": self.name,
            "params": self.params.to_dict(),
            "outcomes": self.outcomes.to_dict(),
            "kind": self.kind,
            "source_design_updated_at": self.source_design_updated_at,
            "source_revision_sha256": self.source_revision_sha256,
            "overlay_revision_sha256": self.overlay_revision_sha256,
            "created_at": self.created_at,
            "modifies_design": False,
            "applied_as": APPLIED_AS,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DesignScenario:
        data = data or {}
        kind = str(data.get("kind") or KIND_OVERLAY)
        if kind not in {KIND_APPROVED, KIND_OVERLAY}:
            kind = KIND_OVERLAY
        return cls(
            scenario_id=str(data.get("scenario_id") or ""),
            design_id=str(data.get("design_id") or ""),
            name=str(data.get("name") or "Сценарий"),
            params=ScenarioParams.from_dict(data.get("params")),
            outcomes=ScenarioOutcomes.from_dict(data.get("outcomes")),
            kind=kind,
            source_design_updated_at=str(data.get("source_design_updated_at") or ""),
            source_revision_sha256=str(data.get("source_revision_sha256") or ""),
            overlay_revision_sha256=str(data.get("overlay_revision_sha256") or ""),
            created_at=str(data.get("created_at") or ""),
            modifies_design=False,
            applied_as=APPLIED_AS,
        )


@dataclass
class ScenarioSummary:
    scenario_id: str
    design_id: str
    name: str
    kind: str
    created_at: str
    diameter_mm: float | None = None
    spacing_a_m: float | None = None
    burden_b_m: float | None = None
    powder_factor_kg_m3: float | None = None
    hole_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "design_id": self.design_id,
            "name": self.name,
            "kind": self.kind,
            "created_at": self.created_at,
            "diameter_mm": self.diameter_mm,
            "spacing_a_m": self.spacing_a_m,
            "burden_b_m": self.burden_b_m,
            "powder_factor_kg_m3": self.powder_factor_kg_m3,
            "hole_count": self.hole_count,
        }
