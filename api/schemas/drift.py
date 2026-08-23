"""Pydantic schemas for drift monitoring (BDX-021). Alerts only."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DriftMetricSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    kind: str
    role: str
    unit: str = ""
    baseline_count: int = 0
    current_count: int = 0
    baseline_mean: float | None = None
    current_mean: float | None = None
    baseline_std: float | None = None
    current_std: float | None = None
    psi: float | None = None
    ks: float | None = None
    mean_shift: float | None = None
    severity: str = "ok"
    reasons: list[str] = Field(default_factory=list)


class DriftAlertSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alert_id: str
    team_id: str
    family: str
    model_id: str
    kind: str
    role: str
    metric_name: str
    severity: str
    message: str
    report_id: str = ""
    site_id: str = ""
    created_at: str = ""
    acknowledged: bool = False
    acknowledged_by: str = ""
    acknowledged_at: str = ""
    auto_deployed: bool = False
    auto_retrained: bool = False
    live_model_unchanged: bool = True
    action: str = "alert_only"


class DriftReportSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_id: str
    team_id: str
    family: str
    model_id: str
    model_checksum: str
    model_status: str
    training_dataset_ids: list[str] = Field(default_factory=list)
    training_dataset_version: int = 0
    current_dataset_id: str = ""
    current_dataset_version: int = 0
    feature_schema_version: str = ""
    site_id: str = ""
    created_at: str = ""
    overall_severity: str = "ok"
    metrics: list[DriftMetricSchema] = Field(default_factory=list)
    alerts: list[DriftAlertSchema] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    data_roles: dict[str, str] = Field(default_factory=dict)
    auto_deployed: bool = False
    auto_retrained: bool = False
    live_model_unchanged: bool = True
    action: str = "alert_only"
    next_step: str = "human_promote_via_registry"


class DriftReportListResponse(BaseModel):
    items: list[DriftReportSchema] = Field(default_factory=list)
    auto_deployed: bool = False
    auto_retrained: bool = False


class DriftAlertListResponse(BaseModel):
    items: list[DriftAlertSchema] = Field(default_factory=list)
    auto_deployed: bool = False
    auto_retrained: bool = False


class DriftKindSchema(BaseModel):
    name: str
    label: str


class DriftSeveritySchema(BaseModel):
    name: str
    label: str


class DriftMetaResponse(BaseModel):
    kinds: list[DriftKindSchema] = Field(default_factory=list)
    severities: list[DriftSeveritySchema] = Field(default_factory=list)
    data_roles: dict[str, str] = Field(default_factory=dict)
    auto_deployed: bool = False
    auto_retrained: bool = False
    action: str = "alert_only"
    next_step: str = "human_promote_via_registry"


class DriftCheckRequest(BaseModel):
    family: str
    model_id: str
    current_dataset_id: str


class DriftAcknowledgeRequest(BaseModel):
    confirm: bool = False
