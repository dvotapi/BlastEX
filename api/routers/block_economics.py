"""REST API вкладки «Экономика»: расчёт блока, снимки, сравнение, чувствительность."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Sequence

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
    ServiceToReferenceRequest,
    ServiceToReferenceResponse,
    VariantResultSchema,
    VariantsRequest,
    VariantsResponse,
)
from api.security import require_internal_access, require_reference_editor
from api.services.economics_service import get_economics_repository, repository_error
from api.services.public_sync_service import PublicReader, get_public_reader, reference_issues
from cost.model import sensitivity
from cost.model.engine import compute_block_economics
from cost.model.export_xlsx import export_bytes
from cost.model.inputs import BlockEconomics, ModelParameters, payload_number, payload_text
from cost.model.materials import ROLES, quantity_in_price_units
from cost.model.services import SHIFT_DRIVERS, service_code
from cost.v2.prices import effective_price, effective_price_lookup
from cost.v2.models import ReferenceItem, ReferenceSnapshot, decimal_value
from cost.v2.references import has_validation_errors
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
    # Пустая ревизия означает «считать на актуальных справочниках»: паспорт
    # фиксирует геометрию блока, а не прайс-лист, и сметчику нужна цена на
    # сегодня. Снимок прогона всегда хранит ту ревизию, на которой посчитали,
    # поэтому старый расчёт остаётся воспроизводимым.
    references = repository.get_reference_snapshot(organization_id, revision_id or None)
    return passport, references


def _compute(
    passport: StoredTechnicalPassport,
    params: ModelParameters,
    references: ReferenceSnapshot,
    *,
    as_of: date | None = None,
) -> BlockEconomics:
    return compute_block_economics(
        {"physical": passport.physical, "lineage": passport.lineage},
        params,
        references,
        passport_name=passport.object_name,
        as_of=as_of,
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
    return BlockEconomicsSchema.model_validate(
        {**result.to_dict(), "reference_revision_id": references.revision_id}
    )


@router.post("/block-economics/variants", response_model=VariantsResponse)
def block_economics_variants(
    payload: VariantsRequest,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> VariantsResponse:
    """До четырёх колонок сметы одним запросом на одной ревизии справочников.

    Ревизия берётся у первого варианта: считать колонки на разных ревизиях
    незачем — коллега опубликует новую между запросами, и суммы в соседних
    столбцах перестанут быть сравнимы. Остальные варианты используют тот же
    снимок, даже если сами просят другую ревизию.
    """

    organization_id, _ = _identity(session)
    try:
        passport, references = _load(
            repository,
            organization_id,
            payload.technical_passport_id,
            payload.variants[0].parameters.reference_revision_id,
        )
    except Exception as exc:
        raise repository_error(exc) from exc
    results = []
    for variant in payload.variants:
        params = _params_with_site(variant.parameters, passport)
        result = _compute(passport, params, references)
        results.append(
            VariantResultSchema(
                name=variant.name,
                economics=BlockEconomicsSchema.model_validate(
                    {**result.to_dict(), "reference_revision_id": references.revision_id}
                ),
            )
        )
    return VariantsResponse(reference_revision_id=references.revision_id, variants=results)


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
    return SensitivityResponse.model_validate(
        {"rows": [row.to_dict() for row in rows], "reference_revision_id": references.revision_id}
    )


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
    # с Decimal, из которого собирается книга. Дата — та, на которую прогон
    # считали: иначе истёкшая с тех пор цена материала выпала бы из выгрузки,
    # и книга разошлась бы с сохранённым сценарием.
    params = ModelParameters.from_dict(stored.parameters)
    economics = _compute(passport, params, references, as_of=stored.created_at.date())
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

    nomenclature = _nomenclature(references, passport)
    rigs = _equipment(references, "DRILL_RIG")
    szm = _equipment(references, "SZM")
    trucks = _equipment(references, "HAZMAT_TRUCK")
    emulsion_trucks = _equipment(references, "EMULSION_TRUCK")
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
            # Пусто — считать на актуальной ревизии; фактическую сметчик видит
            # в поле «Ревизия справочников».
            "reference_revision_id": "",
            "unit_plan_volume_m3": payload_number(unit, "plan_volume_m3", Decimal("0")),
            "rig_code": rig_code,
            "rig_plan_shifts": payload_number(rig_type, "norm_shifts_per_month", Decimal("0"))
            or None,
            "szm_code": szm[0]["code"] if szm else None,
            "delivery_truck_code": trucks[0]["code"] if trucks else None,
            "emulsion_truck_code": emulsion_trucks[0]["code"] if emulsion_trucks else None,
            "crew": crew,
            "drilling_executor": "OWN",
            "nomenclature": _default_nomenclature(nomenclature, passport),
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
            "operations": _package_operations(references, package),
            "nomenclature": nomenclature,
            "rigs": rigs,
            "szm": szm,
            "delivery_trucks": trucks,
            "emulsion_trucks": emulsion_trucks,
            "positions": _catalog(references, "positions"),
            "packages": [
                {"code": code, "name": item.name}
                for code, item in package_map(references).items()
            ],
            "sites": _catalog(references, "sites"),
            "reference_revision_id": references.revision_id,
        }
    )


def _nomenclature(
    references: ReferenceSnapshot, passport: StoredTechnicalPassport
) -> dict[str, list[dict[str, Any]]]:
    """Номенклатура блока по ролям: цена на дату расчёта и количество из паспорта.

    Буровой инструмент и позиции без роли в выбор не попадают: они приходят
    в расчёт через условия бурения и правила затрат, а не со вкладки.
    Количество отдаётся в единицах цены тем же правилом, что и модель:
    подпись под выбором и строка сметы должны называть одно число.
    """

    roles = {role.code: role for role in ROLES}
    prices = references.active_items("material_prices")
    catalog: dict[str, list[dict[str, Any]]] = {}
    for item in references.active_items("materials"):
        role = roles.get(payload_text(item, "nomenclature_role", "OTHER"))
        if role is None:
            continue
        driver_value = decimal_value(passport.physical.get(role.driver))
        # Ручной драйвер (электродетонаторы) в паспорте не бывает: количество
        # сметчик задаёт сам, подсказать его нечем.
        quantity, quantity_label = (
            (None, "")
            if role.driver not in passport.physical
            else quantity_in_price_units(role, item, driver_value)
        )
        catalog.setdefault(role.code, []).append(
            {
                "code": item.code,
                "name": item.name,
                "unit": role.unit,
                "price_rub": float(effective_price(effective_price_lookup(prices, item.code))),
                "length_m": float(payload_number(item, "length_m")),
                "quantity": float(quantity) if quantity is not None else None,
                # Происхождение нужно только там, где штуки переведены в
                # килограммы; для простых ролей оно повторяло бы само число.
                "quantity_label": quantity_label if role.priced_per_kg else "",
            }
        )
    for options in catalog.values():
        options.sort(key=lambda row: row["name"])
    return catalog


def _default_nomenclature(
    catalog: dict[str, list[dict[str, Any]]], passport: StoredTechnicalPassport
) -> dict[str, str]:
    """Что подставить сметчику сразу после переноса паспорта.

    Позиция без цены в умолчание не годится: она дала бы нулевую строку и
    предупреждение вместо готовой сметы.
    """

    chosen: dict[str, str] = {}
    for role, options in catalog.items():
        priced = [row for row in options if row["price_rub"] > 0]
        if priced:
            chosen[role] = priced[0]["code"]

    downhole = [
        row
        for row in catalog.get("NSI_DOWNHOLE", ())
        if row["price_rub"] > 0 and row["length_m"] > 0
    ]
    # Делитель — число устройств, а не скважин: при двух НСИ в скважине их
    # суммарная длина вдвое больше длины одного устройства.
    devices = decimal_value(passport.physical.get("downhole_nsi")) or decimal_value(
        passport.physical.get("holes")
    )
    nsi_length = decimal_value(passport.physical.get("nsi_length_m"))
    if downhole and devices > 0 and nsi_length > 0:
        target = float(nsi_length / devices)
        # Короче требуемого сеть не смонтировать, поэтому сначала подходящие
        # по длине, и среди них самое короткое; если таких нет — ближайшее.
        long_enough = [row for row in downhole if row["length_m"] >= target]
        candidates = long_enough or downhole
        chosen["NSI_DOWNHOLE"] = min(
            candidates,
            key=lambda row: (abs(row["length_m"] - target), row["name"]),
        )["code"]
    return chosen


def _package_operations(references: ReferenceSnapshot, package) -> list[dict[str, str]]:
    names = {item.code: item.name for item in references.active_items("operations")}
    return [
        {"code": op.operation_code, "name": names.get(op.operation_code, op.operation_code)}
        for op in (package.operations if package else ())
    ]


@router.post(
    "/services/to-reference",
    response_model=ServiceToReferenceResponse,
    status_code=status.HTTP_201_CREATED,
)
def service_to_reference(
    payload: ServiceToReferenceRequest,
    session: dict[str, object] = Depends(require_reference_editor),
    repository: EconomicsRepository = Depends(get_economics_repository),
    reader: PublicReader = Depends(get_public_reader),
) -> ServiceToReferenceResponse:
    """Перенести услугу со вкладки в «Правила расчёта затрат» новой ревизией.

    Серверного черновика справочников нет — страница «Справочники» держит его
    у себя и публикует целиком. Поэтому кнопка на вкладке публикует ревизию
    сама: одна запись, комментарий называет источник. Повторный перенос
    обновляет запись с тем же кодом, а не плодит дубли.
    """

    organization_id, user_id = _identity(session)
    service = payload.service
    code = service_code(service.name)
    rule_payload: dict[str, Any] = {
        "operation_code": service.operation_code,
        "cost_item_code": code,
        "behavior_type": "VARIABLE" if service.per_shift else "FIXED",
        "cost_layer": service.layer,
    }
    if service.per_shift:
        driver = SHIFT_DRIVERS.get(service.operation_code)
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"У операции {service.operation_code} нет смен: ставку за смену не привязать.",
            )
        rule_payload.update({"driver": driver, "rate_rub": str(service.amount_rub)})
    else:
        rule_payload["fixed_rub"] = str(service.amount_rub)

    try:
        current = repository.get_reference_snapshot(organization_id)
    except Exception as exc:
        raise repository_error(exc) from exc
    sections = {name: list(items) for name, items in current.sections.items()}
    existing = next((item for item in sections.get("cost_rules", ()) if item.code == code), None)
    if not payload_text(existing, "estimate_section"):
        # Новое правило заводит вкладка, а не старая ревизия: раздел ему нужен
        # сразу, иначе модель будет предупреждать о незаполненном поле на
        # каждом расчёте. Раздел, проставленный в справочнике, переживает
        # перенос — его нет в `RULE_FIELDS`.
        rule_payload["estimate_section"] = "OVERHEAD"
    if existing is not None and existing.name.strip() != service.name.strip():
        # Разные названия дали один код (транслит и регистр): перезаписать
        # чужое правило значит потерять его сумму, а ответ сказал бы
        # «обновлена» — сметчик решил бы, что так и было.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": (
                    f"Код {code} уже занят правилом «{existing.name}»: "
                    "переименуйте услугу или правьте существующее правило в справочнике."
                )
            },
        )
    sections["cost_rules"] = _upsert(
        sections.get("cost_rules", ()), code, service.name, rule_payload, owned=RULE_FIELDS
    )
    # Правило ссылается на статью затрат: без записи в «Статьях затрат»
    # ревизия не пройдёт проверку ссылок.
    sections["cost_items"] = _upsert(
        sections.get("cost_items", ()), code, service.name, {"kind": "service"}, owned=("kind",)
    )

    try:
        issues = reference_issues(reader, repository, organization_id, sections)
    except Exception as exc:
        raise repository_error(exc) from exc
    if has_validation_errors(issues):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Справочники содержат ошибки.", "issues": [i.to_dict() for i in issues]},
        )
    try:
        published = repository.publish_references(
            organization_id,
            user_id,
            current.revision_id,
            sections,
            f"Услуга со вкладки «Экономика блока»: {service.name}",
        )
    except Exception as exc:
        raise repository_error(exc) from exc
    return ServiceToReferenceResponse(
        section="cost_rules",
        code=code,
        created=existing is None,
        reference_revision_id=published.revision_id,
    )


# Поля правила затрат, которыми распоряжается вкладка: их она задаёт при
# каждом переносе и стирает, если услуга перестала быть ставкой за смену.
# Всё остальное — раздел сметы, ресурсный пул, ступени — правят в
# справочнике, и повторный перенос суммы не вправе это потерять.
RULE_FIELDS = (
    "operation_code",
    "cost_item_code",
    "behavior_type",
    "cost_layer",
    "driver",
    "rate_rub",
    "fixed_rub",
)


def _upsert(
    items: Sequence[ReferenceItem],
    code: str,
    name: str,
    payload: dict[str, Any],
    *,
    owned: Sequence[str],
) -> list[ReferenceItem]:
    """Запись с таким кодом обновляется на месте, новая — добавляется в конец.

    Обновляются только поля вкладки (`owned`): правки справочника в
    остальных полях переживают перенос.
    """

    existing = next((item for item in items if item.code == code), None)
    kept = (
        {key: value for key, value in existing.payload.items() if key not in owned}
        if existing is not None
        else {}
    )
    item = ReferenceItem(
        code=code,
        name=name,
        payload={**kept, **payload},
        source="вкладка «Экономика блока»",
        revision=(existing.revision + 1) if existing is not None else 1,
    )
    if existing is None:
        return [*items, item]
    return [item if row.code == code else row for row in items]


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
