"""Pydantic schemas for design-scenario overlays (BDX-016)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.design import BlastDesignSchema


class ScenarioParamsSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    diameter_mm: float | None = Field(None, gt=0)
    spacing_a_m: float | None = Field(None, gt=0)
    burden_b_m: float | None = Field(None, gt=0)
    powder_factor_kg_m3: float | None = Field(None, gt=0)
    stemming_m: float | None = Field(None, ge=0)
    subdrill_m: float | None = Field(None, ge=0)
    pattern: str | None = None
    explosive_key: str | None = None
    inclination_deg: float | None = Field(None, ge=0, le=45)
    delay_interval_ms: float | None = Field(None, gt=0)
    cost_scenario_id: str = "drill_blast"
    fragmentation_model: str = "kuzram"
    lump_size_mm: float = Field(400.0, gt=0)
    mic_window_ms: float = Field(8.0, gt=0)
    vibration_model_id: str = ""
    site_id: str = ""
    use_production_overlays: bool = False
    outcome_model_ids: dict[str, str] = Field(default_factory=dict)
    calibration_model_ids: dict[str, str] = Field(default_factory=dict)


class ScenarioOutcomesSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

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
    fragmentation_source: str = "engineering"
    vibration_source: str = "engineering"
    cost_source: str = "engineering"
    ml_overlay_applied: bool = False
    warnings: list[str] = Field(default_factory=list)


class DesignScenarioSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scenario_id: str
    design_id: str
    name: str
    params: ScenarioParamsSchema = Field(default_factory=ScenarioParamsSchema)
    outcomes: ScenarioOutcomesSchema = Field(default_factory=ScenarioOutcomesSchema)
    kind: str = "overlay"
    source_design_updated_at: str = ""
    source_revision_sha256: str = ""
    overlay_revision_sha256: str = ""
    created_at: str = ""
    modifies_design: bool = False
    applied_as: str = "scenario_overlay"


class ScenarioSummarySchema(BaseModel):
    scenario_id: str
    design_id: str
    name: str
    kind: str = "overlay"
    created_at: str = ""
    diameter_mm: float | None = None
    spacing_a_m: float | None = None
    burden_b_m: float | None = None
    powder_factor_kg_m3: float | None = None
    hole_count: int = 0


class ScenarioListResponse(BaseModel):
    items: list[ScenarioSummarySchema] = Field(default_factory=list)
    design_id: str = ""
    modifies_design: bool = False


class ScenarioCreateRequest(BaseModel):
    design: BlastDesignSchema
    name: str = Field(..., min_length=1)
    params: ScenarioParamsSchema = Field(default_factory=ScenarioParamsSchema)
    persist: bool = True


class ScenarioCreateResponse(DesignScenarioSchema):
    approved_revision_sha256: str = ""
    approved_unchanged: bool = True


class ScenarioCompareRequest(BaseModel):
    design_id: str = ""
    scenario_ids: list[str] = Field(default_factory=list)
    include_baseline: bool = True
    design: BlastDesignSchema | None = None
    inline: list[DesignScenarioSchema] = Field(default_factory=list)


class ScenarioCompareColumnSchema(BaseModel):
    scenario_id: str
    name: str
    kind: str
    design_id: str = ""


class ScenarioCompareRowSchema(BaseModel):
    key: str
    label: str
    unit: str
    values: dict[str, float | None] = Field(default_factory=dict)
    best_scenario_id: str | None = None


class ScenarioCompareResponse(BaseModel):
    metrics: list[dict[str, str]] = Field(default_factory=list)
    scenarios: list[ScenarioCompareColumnSchema] = Field(default_factory=list)
    rows: list[ScenarioCompareRowSchema] = Field(default_factory=list)
    cells: dict[str, dict[str, float | None]] = Field(default_factory=dict)
    applied_as: str = "scenario_overlay"
    modifies_design: bool = False
    is_optimiser: bool = False
    approved_unchanged: bool = True
    warnings: list[str] = Field(default_factory=list)
