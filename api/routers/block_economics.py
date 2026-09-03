"""REST API вкладки «Экономика»: расчёт блока, снимки, сравнение, чувствительность."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from api.schemas.block_economics import (
    BlockEconomicsRequest,
    BlockEconomicsRunRequest,
    BlockEconomicsSchema,
    EconomicsRunSchema,
    EconomicsRunSummarySchema,
    ModelDefaultsResponse,
    ModelParametersSchema,
    RunCompareRequest,
    RunCompareResponse,
    SensitivityResponse,
)
from api.security import require_internal_access
from api.services.economics_service import get_economics_repository, repository_error
from cost.model import sensitivity
from cost.model.engine import compute_block_economics
from cost.model.export_xlsx import export_bytes
from cost.model.inputs import BlockEconomics, ModelParameters, payload_number, payload_text
from cost.v2.models import ReferenceSnapshot
from cost.v2.packages import package_map
from cost.v2.repository import EconomicsRepository, StoredTechnicalPassport


router = APIRouter(prefix="/economics", tags=["block-economics"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _identity(session: dict[str, object]) -> tuple[str, str]:
    return str(session.get("org") or "default"), str(session.get("sub") or "unknown")


def _load(
    repository: EconomicsRepository,
    organization_id: str,
    passport_id: str,
    revision_id: str,
) -> tuple[StoredTechnicalPassport, ReferenceSnapshot]:
    passport = repository.get_technical_passport(organization_id, passport_id)
    # Пустая ревизия означает «считать на актуальных справочниках»; снимок
    # прогона всегда хранит ту, на которой посчитали.
    references = repository.get_reference_snapshot(
        organization_id, revision_id or passport.reference_revision_id
    )
    return passport, references


def _compute(
    passport: StoredTechnicalPassport,
    params: ModelParameters,
    references: ReferenceSnapshot,
) -> BlockEconomics:
    return compute_block_economics(
        {"physical": passport.physical, "lineage": passport.lineage},
        params,
        references,
        passport_name=passport.object_name,
    )


def _params_with_site(
    payload: ModelParametersSchema, passport: StoredTechnicalPassport
) -> ModelParameters:
    data = payload.model_dump(mode="json")
    # Объект работ берётся из паспорта: экономика не может относиться к
    # другому карьеру, чем технический расчёт.
    data["site_code"] = passport.site_code or data.get("site_code", "")
    return ModelParameters.from_dict(data)


@router.post("/block-economics", response_model=BlockEconomicsSchema)
def block_economics(
    payload: BlockEconomicsRequest,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> BlockEconomicsSchema:
    organization_id, _ = _identity(session)
    try:
        passport, references = _load(
            repository,
            organization_id,
            payload.technical_passport_id,
            payload.parameters.reference_revision_id,
        )
    except Exception as exc:
        raise repository_error(exc) from exc
    params = _params_with_site(payload.parameters, passport)
    result = _compute(passport, params, references)
    return BlockEconomicsSchema.model_validate(result.to_dict())


@router.post("/block-economics/sensitivity", response_model=SensitivityResponse)
def block_economics_sensitivity(
    payload: BlockEconomicsRequest,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> SensitivityResponse:
    organization_id, _ = _identity(session)
    try:
        passport, references = _load(
            repository,
            organization_id,
            payload.technical_passport_id,
            payload.parameters.reference_revision_id,
        )
    except Exception as exc:
        raise repository_error(exc) from exc
    rows = sensitivity.compute(
        {"physical": passport.physical, "lineage": passport.lineage},
        _params_with_site(payload.parameters, passport),
        references,
        passport_name=passport.object_name,
    )
    return SensitivityResponse.model_validate({"rows": [row.to_dict() for row in rows]})


@router.post("/runs", response_model=EconomicsRunSchema, status_code=status.HTTP_201_CREATED)
def create_run(
    payload: BlockEconomicsRunRequest,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> EconomicsRunSchema:
    organization_id, user_id = _identity(session)
    try:
        passport, references = _load(
            repository,
            organization_id,
            payload.technical_passport_id,
            payload.parameters.reference_revision_id,
        )
    except Exception as exc:
        raise repository_error(exc) from exc
    # Расчёт вне обработчика ошибок хранилища: ошибка в данных справочника не
    # должна выглядеть как «сервис временно недоступен».
    params = _params_with_site(payload.parameters, passport)
    result = _compute(passport, params, references)
    try:
        stored = repository.save_economics_run(
            organization_id,
            user_id,
            name=payload.name,
            technical_passport_id=passport.id,
            package_code=params.package_code,
            reference_revision_id=references.revision_id,
            parameters={**params.to_dict(), "reference_revision_id": references.revision_id},
            result=result.to_dict(),
        )
    except Exception as exc:
        raise repository_error(exc) from exc
    return EconomicsRunSchema.model_validate(stored.to_dict())


@router.get("/runs", response_model=list[EconomicsRunSummarySchema])
def list_runs(
    technical_passport_id: str | None = Query(None),
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> list[EconomicsRunSummarySchema]:
    organization_id, _ = _identity(session)
    try:
        rows = repository.list_economics_runs(organization_id, technical_passport_id)
    except Exception as exc:
        raise repository_error(exc) from exc
    return [EconomicsRunSummarySchema.model_validate(_summary(row.to_dict())) for row in rows]


@router.get("/runs/{run_id}", response_model=EconomicsRunSchema)
def get_run(
    run_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> EconomicsRunSchema:
    organization_id, _ = _identity(session)
    try:
        return EconomicsRunSchema.model_validate(
            repository.get_economics_run(organization_id, run_id).to_dict()
        )
    except Exception as exc:
        raise repository_error(exc) from exc


@router.post("/runs/compare", response_model=RunCompareResponse)
def compare_runs(
    payload: RunCompareRequest,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> RunCompareResponse:
    organization_id, _ = _identity(session)
    try:
        runs = [
            repository.get_economics_run(organization_id, run_id).to_dict()
            for run_id in payload.run_ids
        ]
    except Exception as exc:
        raise repository_error(exc) from exc
    return RunCompareResponse.model_validate(_compare(runs))


@router.get("/runs/{run_id}/export.xlsx")
def export_run(
    run_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> Response:
    organization_id, _ = _identity(session)
    try:
        stored = repository.get_economics_run(organization_id, run_id)
        passport = repository.get_technical_passport(
            organization_id, stored.technical_passport_id
        )
        references = repository.get_reference_snapshot(
            organization_id, stored.reference_revision_id
        )
    except Exception as exc:
        raise repository_error(exc) from exc
    # Пересчёт на сохранённой ревизии повторяет снимок и даёт доменный объект
    # с Decimal, из которого собирается книга.
    params = ModelParameters.from_dict(stored.parameters)
    economics = _compute(passport, params, references)
    content = export_bytes(
        economics,
        passport_name=f"{stored.name} — {passport.object_name}",
        parameters={
            "Технический паспорт": passport.object_name,
            "Объект работ": passport.site_code,
            "Пакет работ": stored.package_code,
            "Ревизия справочников": stored.reference_revision_id,
            "Плановый объём юнита, м³/мес": params.unit_plan_volume_m3,
            "Буровой станок": params.rig_code,
            "Плановые смены станка": params.rig_plan_shifts,
            "Исполнитель бурения": (
                "субподряд" if params.drilling_executor == "SUBCONTRACTOR" else "свой станок"
            ),
            "Состав бригады": [
                f"{member.position_code} × {member.headcount}" for member in params.crew
            ],
        },
    )
    filename = f"block-economics-{run_id}.xlsx"
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/model-defaults", response_model=ModelDefaultsResponse)
def model_defaults(
    technical_passport_id: str = Query(...),
    package_code: str = Query("DRILL_AND_BLAST"),
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> ModelDefaultsResponse:
    organization_id, _ = _identity(session)
    try:
        passport, references = _load(repository, organization_id, technical_passport_id, "")
    except Exception as exc:
        raise repository_error(exc) from exc

    site = references.item("sites", passport.site_code)
    unit_code = payload_text(site, "production_unit_code")
    unit = references.item("production_units", unit_code)
    rates = references.active_items("organization_rates")
    rate = rates[0] if rates else None

    rigs = _equipment(references, "DRILL_RIG")
    szm = _equipment(references, "SZM")
    trucks = _equipment(references, "HAZMAT_TRUCK")
    rig_code = rigs[0]["code"] if rigs else None
    rig_type = references.item("equipment_types", rig_code) if rig_code else None
    package = package_map(references).get(package_code)

    crew = [
        {
            "position_code": str(member.get("position_code", "")),
            "headcount": str(member.get("headcount", "1")),
            "shifts_per_block": None,
        }
        for template in references.active_items("crew_templates")
        if payload_text(template, "package_code") == package_code
        for member in template.payload.get("members", [])
    ]

    parameters = ModelParametersSchema.model_validate(
        {
            "package_code": package_code,
            "site_code": passport.site_code,
            "reference_revision_id": references.revision_id,
            "unit_plan_volume_m3": payload_number(unit, "plan_volume_m3", Decimal("0")),
            "rig_code": rig_code,
            "rig_plan_shifts": payload_number(rig_type, "norm_shifts_per_month", Decimal("0"))
            or None,
            "szm_code": szm[0]["code"] if szm else None,
            "delivery_truck_code": trucks[0]["code"] if trucks else None,
            "crew": crew,
            "drilling_executor": "OWN",
            "overhead_rate": payload_number(rate, "overhead_rate", Decimal("0.1")),
            "target_margin_rate": payload_number(rate, "target_margin_rate", Decimal("0.1")),
            "vat_rate": payload_number(rate, "vat_rate", Decimal("0.2")),
        }
    )
    return ModelDefaultsResponse.model_validate(
        {
            "parameters": parameters,
            "passport": passport.to_dict(),
            "package_operations": [
                item.operation_code for item in (package.operations if package else ())
            ],
            "rigs": rigs,
            "szm": szm,
            "delivery_trucks": trucks,
            "positions": _catalog(references, "positions"),
            "packages": [
                {"code": code, "name": item.name}
                for code, item in package_map(references).items()
            ],
            "sites": _catalog(references, "sites"),
            "reference_revision_id": references.revision_id,
        }
    )


def _equipment(references: ReferenceSnapshot, kind: str) -> list[dict[str, str]]:
    return [
        {"code": item.code, "name": item.name}
        for item in references.active_items("equipment_types")
        if payload_text(item, "kind") == kind
    ]


def _catalog(references: ReferenceSnapshot, section: str) -> list[dict[str, str]]:
    return [{"code": item.code, "name": item.name} for item in references.active_items(section)]


def _summary(run: dict[str, Any]) -> dict[str, Any]:
    result = run.get("result") or {}
    return {
        "id": run["id"],
        "name": run["name"],
        "technical_passport_id": run["technical_passport_id"],
        "package_code": run["package_code"],
        "reference_revision_id": run["reference_revision_id"],
        "created_at": run["created_at"],
        "created_by": run["created_by"],
        "price_per_m3": result.get("price_per_m3", {}),
    }


def _compare(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Строки, выровненные по коду статьи, с дельтой «последний минус первый»."""

    order: list[str] = []
    names: dict[str, tuple[str, str]] = {}
    amounts: dict[str, dict[str, float]] = {}
    for run in runs:
        for line in (run.get("result") or {}).get("lines", []):
            code = str(line.get("cost_item_code", ""))
            if code not in amounts:
                order.append(code)
                amounts[code] = {}
                names[code] = (str(line.get("cost_item_name", code)), str(line.get("layer", "")))
            amounts[code][run["id"]] = amounts[code].get(run["id"], 0.0) + float(
                line.get("amount_rub", 0)
            )

    rows: list[dict[str, Any]] = []
    first, last = runs[0]["id"], runs[-1]["id"]
    for code in order:
        cells = [
            {"run_id": run["id"], "amount_rub": round(amounts[code].get(run["id"], 0.0), 2)}
            for run in runs
        ]
        rows.append(
            {
                "cost_item_code": code,
                "cost_item_name": names[code][0],
                "layer": names[code][1],
                "amounts": cells,
                "delta_rub": round(
                    amounts[code].get(last, 0.0) - amounts[code].get(first, 0.0), 2
                ),
            }
        )
    rows.sort(key=lambda row: abs(row["delta_rub"]), reverse=True)

    prices: dict[str, list[float]] = {}
    for run in runs:
        for key, value in ((run.get("result") or {}).get("price_per_m3") or {}).items():
            prices.setdefault(key, []).append(float(value))
    delta = {
        key: round(values[-1] - values[0], 4) for key, values in prices.items() if values
    }
    return {
        "runs": [_summary(run) for run in runs],
        "rows": rows,
        "price_per_m3": prices,
        "delta_price_per_m3": delta,
    }
