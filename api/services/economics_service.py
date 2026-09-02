"""Сервисный слой Cost V2: БД, валидация и расчёт."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from fastapi import HTTPException, status

from api.schemas.economics import (
    EconomicScenarioSchema,
    EventCalculationRequest,
    ReferenceItemSchema,
    TechnicalPassportCreateSchema,
)
from cost.v2.engine import FORMULA_VERSION, calculate_scenario
from cost.v2.models import EconomicScenario
from cost.v2.references import (
    REFERENCE_SECTION_DEFINITIONS,
    group_catalog,
    has_validation_errors,
    section_catalog,
    validate_reference_sections,
)
from cost.v2.schemas import SECTION_SCHEMAS, section_fieldsets, section_json_schema
from cost.v2.repository import (
    EconomicsRecordNotFound,
    EconomicsRepository,
    ReferenceRevisionConflict,
)
from cost.v2.technical_adapter import adapt_blast_block, scale_passport_physical


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


@lru_cache(maxsize=1)
def reference_schema_payload() -> dict[str, Any]:
    """Каталог схем разделов. Схема статична — считается один раз на процесс."""

    sections: dict[str, Any] = {}
    for code, meta in REFERENCE_SECTION_DEFINITIONS.items():
        if code not in SECTION_SCHEMAS:
            continue
        sections[code] = {
            "code": code,
            "label": meta["label"],
            "group": meta["group"],
            "view": meta.get("view", "table"),
            "deprecated": bool(meta.get("deprecated", False)),
            "list_columns": list(meta.get("columns", [])),
            "fieldsets": section_fieldsets(code),
            "json_schema": section_json_schema(code),
        }
    return {"groups": group_catalog(), "sections": sections}


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
    resolved, sources = resolve_scenario_passports(repository, organization_id, scenario)
    result = calculate_scenario(resolved, references)
    result["calculation_scope"] = "UNIT"
    result["technical_sources"] = sources
    run = repository.save_calculation_run(
        organization_id=organization_id,
        user_id=user_id,
        scenario=resolved,
        reference_revision_id=references.revision_id,
        formula_version=FORMULA_VERSION,
        result=result,
    )
    return run.to_dict()


def create_technical_passport(
    repository: EconomicsRepository,
    organization_id: str,
    user_id: str,
    payload: TechnicalPassportCreateSchema,
) -> dict[str, Any]:
    references = repository.get_reference_snapshot(
        organization_id, payload.reference_revision_id
    )
    block = payload.block.model_dump()
    drivers = adapt_blast_block(
        block,
        existing_physical=payload.existing_physical,
        source_id=payload.previous_passport_id,
    )
    stored = repository.save_technical_passport(
        organization_id,
        user_id,
        site_code=payload.site_code,
        object_name=payload.object_name,
        previous_passport_id=payload.previous_passport_id,
        reference_revision_id=references.revision_id,
        formula_version=payload.formula_version,
        input_snapshot=payload.input_snapshot,
        selected_variant=payload.selected_variant,
        block_snapshot=block,
        physical={key: str(value) for key, value in drivers.physical.items()},
        lineage=drivers.lineage,
    )
    return stored.to_dict()


def resolve_scenario_passports(
    repository: EconomicsRepository,
    organization_id: str,
    scenario: EconomicScenario,
) -> tuple[EconomicScenario, list[dict[str, Any]]]:
    """Resolve one immutable technical passport per service-line month."""

    data = scenario.to_dict()
    sources: list[dict[str, Any]] = []
    for collection in ("baseline_service_lines", "candidate_service_lines"):
        for line in data[collection]:
            for plan in line["monthly_plans"]:
                passport_id = plan.get("technical_passport_id")
                if not passport_id:
                    continue
                passport = repository.get_technical_passport(organization_id, passport_id)
                if line.get("site_code") and passport.site_code != line["site_code"]:
                    raise ValueError(
                        f"Паспорт {passport.id} относится к объекту {passport.site_code}, "
                        f"а строка — к {line['site_code']}."
                    )
                manual = dict(plan.get("physical") or {})
                planned_volume = manual.get("rock_volume_m3")
                if planned_volume in (None, "") and str(line.get("billing_unit", "")).upper() == "M3":
                    planned_volume = plan.get("billed_quantity", 0)
                if planned_volume in (None, ""):
                    raise ValueError(
                        f"{line.get('name') or line.get('id')}, {plan.get('month')}: "
                        "для масштабирования паспорта задайте горную массу, м³."
                    )
                scaled = scale_passport_physical(passport.physical, planned_volume)
                plan["physical"] = {
                    **manual,
                    **{key: str(value) for key, value in scaled.items()},
                }
                sources.append(
                    {
                        "service_line_id": line.get("id", ""),
                        "month": plan.get("month", ""),
                        "technical_passport_id": passport.id,
                        "technical_formula_version": passport.formula_version,
                        "technical_reference_revision_id": passport.reference_revision_id,
                        "scale_basis": "rock_volume_m3",
                        "planned_rock_volume_m3": str(planned_volume),
                    }
                )
    return EconomicScenario.from_dict(data), sources


def calculate_event_and_store(
    repository: EconomicsRepository,
    organization_id: str,
    user_id: str,
    payload: EventCalculationRequest,
) -> dict[str, Any]:
    passport = repository.get_technical_passport(
        organization_id, payload.technical_passport_id
    )
    references = repository.get_reference_snapshot(
        organization_id, payload.reference_revision_id
    )
    physical = dict(passport.physical)
    unit_driver = {
        "M3": "rock_volume_m3",
        "M": "drilling_m",
        "KG": "explosive_kg",
        "BLAST": "blasts",
    }.get(payload.billing_unit.upper())
    billed_quantity = payload.billed_quantity
    if billed_quantity is None:
        billed_quantity = physical.get(unit_driver, "1") if unit_driver else "1"
    scenario = EconomicScenario.from_dict(
        {
            "id": f"EVENT-{passport.id}",
            "name": payload.name,
            "production_unit_code": payload.production_unit_code,
            "baseline_service_lines": [],
            "candidate_service_lines": [
                {
                    "id": f"event-{passport.id}",
                    "name": payload.name,
                    "package_code": payload.package_code,
                    "customer_code": payload.customer_code,
                    "site_code": passport.site_code,
                    "billing_unit": payload.billing_unit,
                    "market_price_rub": payload.market_price_rub,
                    "monthly_plans": [
                        {
                            "month": payload.month,
                            "billed_quantity": billed_quantity,
                            "physical": physical,
                        }
                    ],
                    "operation_overrides": [
                        item.model_dump() for item in payload.operation_overrides
                    ],
                    "site_conditions": payload.site_conditions.model_dump(),
                    "options": payload.options,
                }
            ],
            "reference_revision_id": references.revision_id,
        }
    )
    result = calculate_scenario(scenario, references, include_allocated_costs=False)
    result["calculation_scope"] = "EVENT"
    result["allocated_overhead_included"] = False
    result["technical_sources"] = [
        {
            "technical_passport_id": passport.id,
            "technical_formula_version": passport.formula_version,
            "technical_reference_revision_id": passport.reference_revision_id,
            "scale_basis": "one_block",
        }
    ]
    run = repository.save_event_calculation_run(
        organization_id,
        user_id,
        reference_revision_id=references.revision_id,
        formula_version=FORMULA_VERSION,
        technical_formula_version=passport.formula_version,
        technical_passport_id=passport.id,
        site_code=passport.site_code,
        period=payload.month,
        input_snapshot=scenario.to_dict(),
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
