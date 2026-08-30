"""REST API справочников и сценарной экономики производственного юнита."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from api.schemas.economics import (
    CalculationRunSchema,
    EconomicScenarioSchema,
    ReferencePublishRequest,
    ReferenceRevisionSchema,
    ReferenceSnapshotSchema,
    ReferenceValidateRequest,
    ReferenceValidationResponse,
    StoredScenarioSchema,
    TechnicalDriverRequest,
    TechnicalDriverResponse,
)
from api.security import require_internal_access, require_reference_editor
from api.services.economics_service import (
    calculate_and_store,
    get_economics_repository,
    reference_snapshot_payload,
    repository_error,
    scenario_from_payload,
    validation_payload,
)
from cost.v2.references import has_validation_errors, validate_reference_sections
from cost.v2.repository import EconomicsRepository
from cost.v2.technical_adapter import adapt_blast_block


router = APIRouter(prefix="/economics", tags=["economics-v2"])


def _identity(session: dict[str, object]) -> tuple[str, str]:
    return str(session.get("org") or "default"), str(session.get("sub") or "unknown")


@router.post("/technical-drivers", response_model=TechnicalDriverResponse)
def technical_drivers(
    payload: TechnicalDriverRequest,
    _session: dict[str, object] = Depends(require_internal_access),
) -> TechnicalDriverResponse:
    snapshot = adapt_blast_block(
        payload.block.model_dump(),
        existing_physical=payload.existing_physical,
        source_id=payload.source_id,
    )
    return TechnicalDriverResponse.model_validate(snapshot.to_dict())


@router.get("/references/snapshot", response_model=ReferenceSnapshotSchema)
def get_reference_snapshot(
    revision_id: str | None = None,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> ReferenceSnapshotSchema:
    organization_id, _ = _identity(session)
    try:
        snapshot = repository.get_reference_snapshot(organization_id, revision_id)
        return ReferenceSnapshotSchema.model_validate(reference_snapshot_payload(snapshot))
    except Exception as exc:
        raise repository_error(exc) from exc


@router.post("/references/validate", response_model=ReferenceValidationResponse)
def validate_references(
    payload: ReferenceValidateRequest,
    _session: dict[str, object] = Depends(require_internal_access),
) -> ReferenceValidationResponse:
    return ReferenceValidationResponse.model_validate(validation_payload(payload.sections))


@router.post("/references/publish", response_model=ReferenceSnapshotSchema)
def publish_references(
    payload: ReferencePublishRequest,
    session: dict[str, object] = Depends(require_reference_editor),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> ReferenceSnapshotSchema:
    organization_id, user_id = _identity(session)
    sections = {
        section: [item.to_domain() for item in items]
        for section, items in payload.sections.items()
    }
    issues = validate_reference_sections(sections)
    if has_validation_errors(issues):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Справочники содержат ошибки.", "issues": [i.to_dict() for i in issues]},
        )
    try:
        snapshot = repository.publish_references(
            organization_id=organization_id,
            user_id=user_id,
            base_revision=payload.base_revision,
            sections=sections,
            comment=payload.comment,
        )
        return ReferenceSnapshotSchema.model_validate(reference_snapshot_payload(snapshot))
    except Exception as exc:
        raise repository_error(exc) from exc


@router.get("/references/revisions", response_model=list[ReferenceRevisionSchema])
def list_reference_revisions(
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> list[ReferenceRevisionSchema]:
    organization_id, _ = _identity(session)
    try:
        return [
            ReferenceRevisionSchema.model_validate(row.to_dict())
            for row in repository.list_reference_revisions(organization_id)
        ]
    except Exception as exc:
        raise repository_error(exc) from exc


@router.get("/references/revisions/{revision_id}", response_model=ReferenceSnapshotSchema)
def get_reference_revision(
    revision_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> ReferenceSnapshotSchema:
    organization_id, _ = _identity(session)
    try:
        snapshot = repository.get_reference_snapshot(organization_id, revision_id)
        return ReferenceSnapshotSchema.model_validate(reference_snapshot_payload(snapshot))
    except Exception as exc:
        raise repository_error(exc) from exc


@router.get("/scenarios", response_model=list[StoredScenarioSchema])
def list_scenarios(
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> list[StoredScenarioSchema]:
    organization_id, _ = _identity(session)
    try:
        return [StoredScenarioSchema.model_validate(row.to_dict()) for row in repository.list_scenarios(organization_id)]
    except Exception as exc:
        raise repository_error(exc) from exc


@router.post("/scenarios", response_model=StoredScenarioSchema, status_code=status.HTTP_201_CREATED)
def create_scenario(
    payload: EconomicScenarioSchema,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> StoredScenarioSchema:
    organization_id, user_id = _identity(session)
    try:
        stored = repository.save_scenario(
            organization_id, user_id, scenario_from_payload(payload)
        )
        return StoredScenarioSchema.model_validate(stored.to_dict())
    except Exception as exc:
        raise repository_error(exc) from exc


@router.get("/scenarios/{scenario_id}", response_model=StoredScenarioSchema)
def get_scenario(
    scenario_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> StoredScenarioSchema:
    organization_id, _ = _identity(session)
    try:
        return StoredScenarioSchema.model_validate(
            repository.get_scenario(organization_id, scenario_id).to_dict()
        )
    except Exception as exc:
        raise repository_error(exc) from exc


@router.put("/scenarios/{scenario_id}", response_model=StoredScenarioSchema)
def update_scenario(
    scenario_id: str,
    payload: EconomicScenarioSchema,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> StoredScenarioSchema:
    organization_id, user_id = _identity(session)
    try:
        stored = repository.save_scenario(
            organization_id, user_id, scenario_from_payload(payload, scenario_id)
        )
        return StoredScenarioSchema.model_validate(stored.to_dict())
    except Exception as exc:
        raise repository_error(exc) from exc


@router.post("/scenarios/{scenario_id}/clone", response_model=StoredScenarioSchema)
def clone_scenario(
    scenario_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> StoredScenarioSchema:
    organization_id, user_id = _identity(session)
    try:
        return StoredScenarioSchema.model_validate(
            repository.clone_scenario(organization_id, user_id, scenario_id).to_dict()
        )
    except Exception as exc:
        raise repository_error(exc) from exc


@router.post("/scenarios/{scenario_id}/calculate", response_model=CalculationRunSchema)
def calculate_economic_scenario(
    scenario_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> CalculationRunSchema:
    organization_id, user_id = _identity(session)
    try:
        return CalculationRunSchema.model_validate(
            calculate_and_store(repository, organization_id, user_id, scenario_id)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        raise repository_error(exc) from exc


@router.get("/calculation-runs/{run_id}", response_model=CalculationRunSchema)
def get_calculation_run(
    run_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> CalculationRunSchema:
    organization_id, _ = _identity(session)
    try:
        return CalculationRunSchema.model_validate(
            repository.get_calculation_run(organization_id, run_id).to_dict()
        )
    except Exception as exc:
        raise repository_error(exc) from exc
