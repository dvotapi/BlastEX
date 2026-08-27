"""Build and list immutable training-dataset snapshots. No model training."""
from __future__ import annotations

from design import persistence as design_persistence
from design.models import BlastDesign
from api.exceptions import DatasetNotFoundError, ImmutableDatasetError, InvalidDesignError
from api.schemas.datasets import (
    DatasetBuildRequest,
    DatasetListResponse,
    DatasetPreviewRequest,
    DatasetSnapshotSchema,
    DatasetSummarySchema,
    SampleValidationSchema,
)
from intelligence.datasets.builder import (
    FEATURE_SCHEMA_VERSION,
    build_sample,
    build_snapshot,
    next_dataset_version,
)
from intelligence.datasets import persistence as dataset_persistence


def _design_from_schema(schema) -> BlastDesign:
    return BlastDesign.from_dict(schema.model_dump())


def _load_candidates(team_id: str, design_ids: list[str]) -> list[BlastDesign]:
    if design_ids:
        designs: list[BlastDesign] = []
        for design_id in design_ids:
            try:
                designs.append(design_persistence.load_design(team_id, design_id))
            except design_persistence.DesignNotFoundError as exc:
                raise InvalidDesignError(f"Паспорт БВР «{design_id}» не найден.") from exc
        return designs
    return [design_persistence.load_design(team_id, item.design_id) for item in design_persistence.list_designs(team_id)]


def preview_design(request: DatasetPreviewRequest) -> SampleValidationSchema:
    if not request.site_id.strip():
        raise InvalidDesignError("Для проверки образца нужен site_id.")
    design = _design_from_schema(request.design)
    sample = build_sample(design, site_id=request.site_id.strip())
    return SampleValidationSchema(**sample.validation.to_dict())


def list_snapshots(team_id: str) -> DatasetListResponse:
    items = dataset_persistence.list_snapshots(team_id)
    return DatasetListResponse(items=[DatasetSummarySchema(**item.__dict__) for item in items])


def get_snapshot(team_id: str, dataset_id: str) -> DatasetSnapshotSchema:
    try:
        snapshot = dataset_persistence.load_snapshot(team_id, dataset_id)
    except dataset_persistence.DatasetNotFoundError as exc:
        raise DatasetNotFoundError(dataset_id) from exc
    except dataset_persistence.ImmutableDatasetError as exc:
        raise ImmutableDatasetError(str(exc)) from exc
    return DatasetSnapshotSchema(**snapshot.to_dict())


def build_snapshot_for_team(team_id: str, request: DatasetBuildRequest) -> DatasetSnapshotSchema:
    site_id = request.site_id.strip()
    if not site_id:
        raise InvalidDesignError("Для снимка датасета нужен site_id.")
    designs = _load_candidates(team_id, [item.strip() for item in request.design_ids if item.strip()])
    if request.include_design is not None:
        extra = _design_from_schema(request.include_design)
        if extra.design_id:
            designs = [item for item in designs if item.design_id != extra.design_id]
        designs.append(extra)
    if not designs:
        raise InvalidDesignError("Нет паспортов для сборки снимка.")

    snapshot = build_snapshot(
        designs,
        site_id=site_id,
        dataset_id=dataset_persistence.new_dataset_id(),
        dataset_version=next_dataset_version(dataset_persistence.existing_versions(team_id, site_id)),
        name=request.name.strip(),
    )
    try:
        saved = dataset_persistence.save_snapshot(team_id, snapshot)
    except dataset_persistence.ImmutableDatasetError as exc:
        raise ImmutableDatasetError(str(exc)) from exc
    return DatasetSnapshotSchema(**saved.to_dict())


def feature_schema_version() -> str:
    return FEATURE_SCHEMA_VERSION
