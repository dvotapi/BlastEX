"""Pydantic schemas for immutable training-dataset snapshots (BDX-011)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.design import BlastDesignSchema


class SampleValidationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ok: bool
    closed: bool = False
    reasons: list[str] = Field(default_factory=list)
    complete_target_groups: list[str] = Field(default_factory=list)


class TrainingSampleSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_blast_id: str
    site_id: str
    feature_schema_version: str
    features: dict[str, Any] = Field(default_factory=dict)
    targets: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    validation: SampleValidationSchema


class RejectedSampleSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_blast_id: str = ""
    reasons: list[str] = Field(default_factory=list)
    closed: bool = False


class DatasetSnapshotSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_id: str
    dataset_version: int
    feature_schema_version: str
    source_blast_ids: list[str] = Field(default_factory=list)
    created_at: str
    site_id: str
    name: str = ""
    kind: str = "training_snapshot"
    sample_count: int = 0
    rejected_count: int = 0
    samples: list[TrainingSampleSchema] = Field(default_factory=list)
    rejected: list[RejectedSampleSchema] = Field(default_factory=list)
    immutable: bool = True


class DatasetSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_id: str
    name: str = ""
    dataset_version: int
    feature_schema_version: str
    site_id: str
    created_at: str
    source_blast_ids: list[str] = Field(default_factory=list)
    sample_count: int = 0
    rejected_count: int = 0
    immutable: bool = True


class DatasetListResponse(BaseModel):
    items: list[DatasetSummarySchema] = Field(default_factory=list)


class DatasetBuildRequest(BaseModel):
    site_id: str
    name: str = ""
    design_ids: list[str] = Field(default_factory=list)
    include_design: BlastDesignSchema | None = None


class DatasetPreviewRequest(BaseModel):
    site_id: str
    design: BlastDesignSchema
