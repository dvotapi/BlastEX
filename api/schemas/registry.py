"""Pydantic schemas for the formal model registry (BDX-020)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RegistryLineageSchema(BaseModel):
    training_dataset_id: str = ""
    training_dataset_ids: list[str] = Field(default_factory=list)
    training_dataset_version: int = 0
    feature_schema_version: str = ""


class RegistryTransitionSchema(BaseModel):
    from_status: str
    to_status: str
    actor: str
    at: str
    note: str = ""
    confirm: bool = True
    auto_deployed: bool = False


class RegistryRecordSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    family: str
    model_id: str
    team_id: str
    site_id: str
    scope: str = ""
    model_type: str
    class_name: str = ""
    model_version: int
    status: str
    source_status: str
    checksum: str
    lineage: RegistryLineageSchema
    training_date: str = ""
    algorithm: str = ""
    sample_count: int = 0
    promoted_by: str = ""
    promoted_at: str = ""
    transitions: list[RegistryTransitionSchema] = Field(default_factory=list)
    allowed_transitions: list[str] = Field(default_factory=list)
    auto_deployed: bool = False
    data_roles: dict[str, str] = Field(default_factory=dict)


class RegistryListResponse(BaseModel):
    items: list[RegistryRecordSchema] = Field(default_factory=list)
    auto_deployed: bool = False


class RegistryFamilySchema(BaseModel):
    name: str
    label: str


class RegistryStatusSchema(BaseModel):
    name: str
    label: str
    allowed_transitions: list[str] = Field(default_factory=list)


class RegistryMetaResponse(BaseModel):
    families: list[RegistryFamilySchema] = Field(default_factory=list)
    statuses: list[RegistryStatusSchema] = Field(default_factory=list)
    auto_deployed: bool = False


class RegistryPromoteRequest(BaseModel):
    to_status: str
    confirm: bool = False
    note: str = ""
