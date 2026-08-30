"""Сервисный слой Cost V2: БД, валидация и расчёт."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from fastapi import HTTPException, status

from api.schemas.economics import EconomicScenarioSchema, ReferenceItemSchema
from cost.v2.engine import FORMULA_VERSION, calculate_scenario
from cost.v2.references import (
    group_catalog,
    has_validation_errors,
    section_catalog,
    validate_reference_sections,
)
from cost.v2.repository import (
    EconomicsRecordNotFound,
    EconomicsRepository,
    ReferenceRevisionConflict,
)


@lru_cache(maxsize=4)
def _postgres_repository(database_url: str) -> EconomicsRepository:
    from cost.v2.db_repository import PostgresEconomicsRepository

    return PostgresEconomicsRepository(database_url)


def get_economics_repository() -> EconomicsRepository:
    database_url = os.getenv("BLASTEX_DATABASE_URL", "").strip()
    if not database_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cost V2 не подключён: задайте BLASTEX_DATABASE_URL для базы project1.",
        )
    return _postgres_repository(database_url)


def reference_snapshot_payload(snapshot: Any) -> dict[str, Any]:
    payload = snapshot.to_dict()
    for section in section_catalog():
        payload["sections"].setdefault(section["code"], [])
    payload["section_catalog"] = section_catalog()
    payload["group_catalog"] = group_catalog()
    return payload


def validation_payload(sections: dict[str, list[ReferenceItemSchema]]) -> dict[str, Any]:
    domain_sections = {
        section: [item.to_domain() for item in items] for section, items in sections.items()
    }
    issues = validate_reference_sections(domain_sections)
    return {
        "valid": not has_validation_errors(issues),
        "issues": [issue.to_dict() for issue in issues],
    }


def calculate_and_store(
    repository: EconomicsRepository,
    organization_id: str,
    user_id: str,
    scenario_id: str,
) -> dict[str, Any]:
    stored = repository.get_scenario(organization_id, scenario_id)
    scenario = stored.scenario
    references = repository.get_reference_snapshot(
        organization_id, scenario.reference_revision_id
    )
    result = calculate_scenario(scenario, references)
    run = repository.save_calculation_run(
        organization_id=organization_id,
        user_id=user_id,
        scenario=scenario,
        reference_revision_id=references.revision_id,
        formula_version=FORMULA_VERSION,
        result=result,
    )
    return run.to_dict()


def scenario_from_payload(payload: EconomicScenarioSchema, scenario_id: str = "") -> Any:
    data = payload.model_dump()
    if scenario_id:
        data["id"] = scenario_id
    return EconomicScenarioSchema.model_validate(data).to_domain()


def repository_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ReferenceRevisionConflict):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
            headers={"X-Current-Revision": exc.actual},
        )
    if isinstance(exc, EconomicsRecordNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Cost V2 временно недоступен: {exc}",
    )
