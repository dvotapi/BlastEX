"""HTTP contracts for the mass-blast project module."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MassBlastBlockInputSchema(BaseModel):
    design_id: str = Field(..., min_length=1, max_length=120)
    technical_passport_id: str | None = Field(None, max_length=36)
    code: str = Field("", max_length=120)
    horizon: str = Field("", max_length=120)


class ResponsibilitySchema(BaseModel):
    role_code: str = Field(..., min_length=1, max_length=80)
    employee_code: str = Field(..., min_length=1, max_length=80)
    employee_name: str = Field("", max_length=300)
    position_name: str = Field("", max_length=300)


class GuardPostSchema(BaseModel):
    code: str = Field(..., min_length=1, max_length=80)
    location: str = Field(..., min_length=1, max_length=500)
    responsible_employee_code: str = Field("", max_length=80)
    notes: str = Field("", max_length=1000)


class NotificationSchema(BaseModel):
    recipient: str = Field(..., min_length=1, max_length=300)
    channel: str = Field("", max_length=80)
    sent_at: str = Field("", max_length=60)


class MassBlastProjectInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=300)
    site_code: str = Field(..., min_length=1, max_length=80)
    object_name: str = Field(..., min_length=1, max_length=300)
    customer_code: str = Field("", max_length=80)
    blast_date: str = Field(..., min_length=1, max_length=10)
    blast_time: str = Field("", max_length=20)
    document_profile_code: str = Field("STANDARD", min_length=1, max_length=80)
    reference_revision_id: str | None = Field(None, max_length=36)
    blocks: list[MassBlastBlockInputSchema] = Field(min_length=1, max_length=100)
    responsibilities: list[ResponsibilitySchema] = Field(default_factory=list)
    safety_plan: dict[str, Any] = Field(default_factory=dict)
    charging_schedule: list[dict[str, Any]] = Field(default_factory=list)
    signal_plan: dict[str, Any] = Field(default_factory=dict)
    guard_posts: list[GuardPostSchema] = Field(default_factory=list)
    notifications: list[NotificationSchema] = Field(default_factory=list)
    expected_version: int | None = Field(None, ge=1)


class MassBlastProjectSummarySchema(BaseModel):
    id: str
    name: str
    site_code: str
    object_name: str
    blast_date: str
    lifecycle_status: Literal["draft", "in_review", "approved", "executed", "closed"]
    version: int
    current_revision_id: str | None = None
    block_design_ids: list[str] = Field(default_factory=list)
    updated_at: str


class MassBlastProjectSchema(MassBlastProjectSummarySchema):
    customer_code: str = ""
    blast_time: str = ""
    document_profile_code: str
    reference_revision_id: str | None = None
    blocks: list[dict[str, Any]]
    responsibilities: list[ResponsibilitySchema]
    safety_plan: dict[str, Any]
    charging_schedule: list[dict[str, Any]]
    signal_plan: dict[str, Any]
    guard_posts: list[GuardPostSchema]
    notifications: list[NotificationSchema]
    created_at: str
    created_by: str
    updated_by: str


class MassBlastValidationIssueSchema(BaseModel):
    level: Literal["error", "warning"]
    code: str
    message: str
    path: str = ""


class MassBlastValidationResponse(BaseModel):
    valid: bool
    issues: list[MassBlastValidationIssueSchema]
    context: dict[str, Any]


class RevisionCreateSchema(BaseModel):
    expected_version: int = Field(..., ge=1)
    require_attachments: bool = False


class MassBlastRevisionSchema(BaseModel):
    id: str
    project_id: str
    revision_no: int
    previous_revision_id: str | None = None
    reference_revision_id: str
    technical_formula_version: str
    document_template_version: str
    content_sha256: str
    created_at: str
    created_by: str
    context: dict[str, Any]


class MassBlastApprovalCreateSchema(BaseModel):
    role_code: str = Field(..., min_length=1, max_length=80)
    decision: Literal["approved", "rejected"]
    comment: str = Field("", max_length=2000)


class MassBlastApprovalSchema(BaseModel):
    id: str
    revision_id: str
    role_code: str
    actor: str
    decision: Literal["approved", "rejected"]
    comment: str
    content_sha256: str
    created_at: str


class MassBlastDocumentCreateSchema(BaseModel):
    revision_id: str = Field(..., min_length=1, max_length=36)
    kind: Literal["PROJECT", "ORDER", "SCHEDULE", "PACKAGE"] = "PROJECT"
    format: Literal["PDF", "XLSX", "ZIP"] = "PDF"


class MassBlastDocumentSchema(BaseModel):
    id: str
    revision_id: str
    kind: str
    format: str
    filename: str
    sha256: str
    created_at: str


class MassBlastAttachmentSchema(BaseModel):
    id: str
    project_id: str
    revision_id: str | None = None
    kind: str
    filename: str
    mime_type: str
    byte_size: int
    sha256: str
    created_at: str
    created_by: str


class MassBlastLifecycleSchema(BaseModel):
    to_status: Literal["draft", "in_review", "approved", "executed", "closed"]
    expected_version: int = Field(..., ge=1)
    confirm: bool = False
    note: str = Field("", max_length=2000)
