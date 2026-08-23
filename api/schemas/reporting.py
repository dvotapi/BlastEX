"""Pydantic schemas for the BDX-024 official blast passport."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.design import BlastDesignSchema


class PlannedCostInputSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    total_amount_rub: float | None = None
    cost_per_m3: float | None = None
    variable_total_rub: float | None = None
    labor_total_rub: float | None = None
    fixed_total_rub: float | None = None
    notes: str = ""
    role: str = "designed"


class PassportBuildRequest(BaseModel):
    design: BlastDesignSchema
    lump_size_mm: float = 400.0
    max_oversize_pct: float = 5.0
    fragmentation_model: str = "kuzram"
    include_predictions: bool = True
    planned_cost: PlannedCostInputSchema | None = None
    predicted_cost: PlannedCostInputSchema | None = None


class PassportRolesResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    roles: list[str]
    labels_ru: dict[str, str]
    labels_en: dict[str, str]
    kind: str
    approved: bool = False
    auto_approved: bool = False
    evaluates_code: bool = False
    silent_unit_conversion: bool = False
    disclaimer: str


class PassportDocumentSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    kind: str = "blast_passport"
    version: str = "1"
    design_id: str
    name: str
    generated_at: str = ""
    updated_at: str = ""
    approved: bool = False
    auto_approved: bool = False
    design_rewritten: bool = False
    disclaimer: str
    roles: list[str] = Field(default_factory=list)
    role_labels_ru: dict[str, str] = Field(default_factory=dict)
    role_labels_en: dict[str, str] = Field(default_factory=dict)
    designed: dict[str, Any] = Field(default_factory=dict)
    executed: dict[str, Any] = Field(default_factory=dict)
    predicted: dict[str, Any] = Field(default_factory=dict)
    measured: dict[str, Any] = Field(default_factory=dict)
    planned_cost: dict[str, Any] | None = None
    comparison: list[dict[str, Any]] = Field(default_factory=list)
    holes: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
