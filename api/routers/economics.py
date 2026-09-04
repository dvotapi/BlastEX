"""REST API справочников и сценарной экономики производственного юнита."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

from api.schemas.reference_schema import ReferenceSchemaResponse
from api.schemas.economics import (
    CalculationRunSchema,
    EconomicScenarioSchema,
    EventCalculationRequest,
    PublicDeltaRequest,
    PublicDeltaResponse,
    PublicLinkRequest,
    PublicLinkSchema,
    PublicSyncSettingsRequest,
    PublicSyncSettingsSchema,
    ReferenceImportResponse,
    ReferenceItemSchema,
    ReferencePublishRequest,
    ReferenceRevisionSchema,
    ReferenceSnapshotSchema,
    ReferenceValidateRequest,
    ReferenceValidationResponse,
    StoredScenarioSchema,
    TechnicalDriverRequest,
    TechnicalDriverResponse,
    TechnicalPassportCreateSchema,
    TechnicalPassportSchema,
)
from api.security import require_admin, require_internal_access, require_reference_editor
from api.services.economics_service import (
    calculate_event_and_store,
    calculate_and_store,
    create_technical_passport,
    domain_sections,
    get_economics_repository,
    reference_schema_payload,
    reference_snapshot_payload,
    repository_error,
    scenario_from_payload,
    validation_payload,
)
from api.services.public_sync_service import (
    get_public_reader,
    public_delta_payload,
    public_link_payload,
    public_settings_payload,
    reference_issues,
    settings_from_request,
)
from cost.v2.public_sync import PublicReader, PublicWriteError
from cost.v2.reference_files import XLSX_MEDIA_TYPE, ReferenceFileError, export_json, export_xlsx, import_file
from cost.v2.references import has_validation_errors
from cost.v2.repository import (
    EconomicsRecordNotFound,
    EconomicsRepository,
    EconomicsRepositoryError,
    PublicLink,
    PublicLinkConflict,
    ReferenceRevisionConflict,
)
from cost.v2.technical_adapter import adapt_blast_block


router = APIRouter(prefix="/economics", tags=["economics-v2"])

# Полный каталог справочников в xlsx весит сотни килобайт; десятки мегабайт —
# это уже не справочники, читать такой файл в память незачем.
MAX_REFERENCE_FILE_BYTES = 20 * 1024 * 1024


def _identity(session: dict[str, object]) -> tuple[str, str]:
    return str(session.get("org") or "default"), str(session.get("sub") or "unknown")


def _public_link(request: PublicLinkRequest) -> PublicLink:
    """Связь из запроса в доменный вид: раздел и таблицу схема уже проверила."""

    return PublicLink(
        section=request.section,
        code=request.code,
        public_table=request.public_table,
        public_id=request.public_id,
    )


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


@router.get("/technical-passports", response_model=list[TechnicalPassportSchema])
def list_technical_passports(
    site_code: str | None = None,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> list[TechnicalPassportSchema]:
    organization_id, _ = _identity(session)
    try:
        return [
            TechnicalPassportSchema.model_validate(item.to_dict())
            for item in repository.list_technical_passports(organization_id, site_code)
        ]
    except Exception as exc:
        raise repository_error(exc) from exc


@router.get("/technical-passports/{passport_id}", response_model=TechnicalPassportSchema)
def get_technical_passport(
    passport_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> TechnicalPassportSchema:
    organization_id, _ = _identity(session)
    try:
        return TechnicalPassportSchema.model_validate(
            repository.get_technical_passport(organization_id, passport_id).to_dict()
        )
    except Exception as exc:
        raise repository_error(exc) from exc


@router.post(
    "/technical-passports",
    response_model=TechnicalPassportSchema,
    status_code=status.HTTP_201_CREATED,
)
def post_technical_passport(
    payload: TechnicalPassportCreateSchema,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> TechnicalPassportSchema:
    organization_id, user_id = _identity(session)
    try:
        return TechnicalPassportSchema.model_validate(
            create_technical_passport(repository, organization_id, user_id, payload)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        raise repository_error(exc) from exc


@router.post("/calculations/event", response_model=CalculationRunSchema)
def calculate_event(
    payload: EventCalculationRequest,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> CalculationRunSchema:
    organization_id, user_id = _identity(session)
    try:
        return CalculationRunSchema.model_validate(
            calculate_event_and_store(repository, organization_id, user_id, payload)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        raise repository_error(exc) from exc


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


@router.get("/references/schema", response_model=ReferenceSchemaResponse)
def get_reference_schema(
    _session: dict[str, object] = Depends(require_internal_access),
) -> ReferenceSchemaResponse:
    """Схема полей каждого раздела: по ней фронт рисует списки и формы."""

    return ReferenceSchemaResponse.model_validate(reference_schema_payload())


@router.get("/references/public-settings", response_model=PublicSyncSettingsSchema)
def get_public_settings(
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> PublicSyncSettingsSchema:
    """Настройки обмена организации со схемой public (§4.5, §5).

    Читать их может любой сотрудник: без них страница «Справочники» не знает,
    показывать ли плашку журнала и переключатели зеркал.
    """

    organization_id, _ = _identity(session)
    try:
        settings = repository.get_public_sync_settings(organization_id)
    except Exception as exc:
        raise repository_error(exc) from exc
    return PublicSyncSettingsSchema.model_validate(public_settings_payload(settings))


@router.put("/references/public-settings", response_model=PublicSyncSettingsSchema)
def put_public_settings(
    payload: PublicSyncSettingsRequest,
    session: dict[str, object] = Depends(require_admin),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> PublicSyncSettingsSchema:
    """Новое состояние настроек целиком; включение зеркала создаёт его таблицу."""

    organization_id, user_id = _identity(session)
    try:
        saved = repository.set_public_sync_settings(
            organization_id, user_id, settings_from_request(payload)
        )
    except PublicWriteError as exc:
        # Таблицу зеркала создать не вышло — отказала чужая схема, а не BlastEX.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": str(exc)},
        ) from exc
    except EconomicsRepositoryError as exc:
        # Раздел, которого нет среди зеркал (например, сопоставленный): это
        # неверный запрос, а не отказ хранилища.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc)},
        ) from exc
    except Exception as exc:
        raise repository_error(exc) from exc
    return PublicSyncSettingsSchema.model_validate(public_settings_payload(saved))


@router.post("/references/validate", response_model=ReferenceValidationResponse)
def validate_references(
    payload: ReferenceValidateRequest,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
    reader: PublicReader = Depends(get_public_reader),
) -> ReferenceValidationResponse:
    organization_id, _ = _identity(session)
    try:
        issues = reference_issues(
            reader, repository, organization_id, domain_sections(payload.sections)
        )
    except Exception as exc:
        raise repository_error(exc) from exc
    return ReferenceValidationResponse.model_validate(validation_payload(issues))


@router.post("/references/publish", response_model=ReferenceSnapshotSchema)
def publish_references(
    payload: ReferencePublishRequest,
    session: dict[str, object] = Depends(require_reference_editor),
    repository: EconomicsRepository = Depends(get_economics_repository),
    reader: PublicReader = Depends(get_public_reader),
) -> ReferenceSnapshotSchema:
    organization_id, user_id = _identity(session)
    sections = domain_sections(payload.sections)
    links = [_public_link(link) for link in payload.public_links]
    try:
        issues = reference_issues(reader, repository, organization_id, sections, links)
    except Exception as exc:
        raise repository_error(exc) from exc
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
            public_links=links,
        )
        return ReferenceSnapshotSchema.model_validate(reference_snapshot_payload(snapshot))
    except PublicLinkConflict as exc:
        # Строка журнала занята другой записью справочника: ни ревизия, ни
        # связи не записаны — это выбор пользователя, а не отказ хранилища.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc)},
        ) from exc
    except PublicWriteError as exc:
        # Журнал не принял выгрузку: ревизии нет, транзакция откачена целиком
        # (§4.5). Отказала чужая система — 502, а не 503 «Cost V2 недоступен».
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": str(exc)},
        ) from exc
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


@router.post("/references/public-delta", response_model=PublicDeltaResponse)
def get_public_delta(
    payload: PublicDeltaRequest,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
    reader: PublicReader = Depends(get_public_reader),
) -> PublicDeltaResponse:
    """Разница журнала public с переданным черновиком (§4.4).

    Недоступность public — не ошибка запроса: ответ 200 с ``available: false``
    и текстом причины, страница «Справочники» продолжает работать без журнала.
    """

    organization_id, _ = _identity(session)
    try:
        return PublicDeltaResponse.model_validate(
            public_delta_payload(
                reader,
                repository,
                organization_id,
                payload.sections,
                [_public_link(link) for link in payload.pending_links],
            )
        )
    except Exception as exc:
        # Недоступность журнала уже обработана внутри сервиса; сюда доходит
        # только отказ хранилища связей — это 503, а не пустая разница.
        raise repository_error(exc) from exc


@router.post(
    "/references/public-links",
    response_model=PublicLinkSchema,
    status_code=status.HTTP_201_CREATED,
)
def create_public_link(
    payload: PublicLinkRequest,
    session: dict[str, object] = Depends(require_reference_editor),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> PublicLinkSchema:
    organization_id, user_id = _identity(session)
    try:
        saved = repository.save_public_link(organization_id, user_id, _public_link(payload))
    except (ReferenceRevisionConflict, EconomicsRecordNotFound) as exc:
        # Подклассы `EconomicsRepositoryError` со своими кодами (409 с
        # заголовком ревизии и 404) разбирает `repository_error`, поэтому они
        # ловятся раньше базового класса.
        raise repository_error(exc) from exc
    except EconomicsRepositoryError as exc:
        # Строка public уже связана с другой записью раздела — это конфликт
        # выбора пользователя, а не поломка хранилища (503 из repository_error).
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc)},
        ) from exc
    except Exception as exc:
        raise repository_error(exc) from exc
    return PublicLinkSchema.model_validate(public_link_payload(saved))


@router.get("/references/public-links", response_model=list[PublicLinkSchema])
def list_public_links(
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> list[PublicLinkSchema]:
    organization_id, _ = _identity(session)
    try:
        return [
            PublicLinkSchema.model_validate(public_link_payload(link))
            for link in repository.list_public_links(organization_id)
        ]
    except Exception as exc:
        raise repository_error(exc) from exc


@router.get("/references/export")
def export_references(
    format: str = "xlsx",
    revision_id: str | None = None,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> Response:
    """Опубликованная ревизия файлом: книга xlsx (лист на раздел) или JSON-снимок."""

    if format not in {"xlsx", "json"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Формат экспорта: xlsx или json.",
        )
    organization_id, _ = _identity(session)
    try:
        snapshot = repository.get_reference_snapshot(organization_id, revision_id)
    except Exception as exc:
        raise repository_error(exc) from exc
    file_name = f"references-{snapshot.revision_id[:8]}.{format}"
    disposition = f'attachment; filename="{file_name}"'
    if format == "json":
        return JSONResponse(export_json(snapshot), headers={"Content-Disposition": disposition})
    return Response(
        export_xlsx(snapshot),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": disposition},
    )


@router.post("/references/import", response_model=ReferenceImportResponse)
async def import_references(
    file: UploadFile = File(...),
    _session: dict[str, object] = Depends(require_reference_editor),
) -> ReferenceImportResponse:
    """Файл → разделы черновика. В базу ничего не пишется: дальше проверка и публикация."""

    too_big = HTTPException(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        detail=f"Файл больше {MAX_REFERENCE_FILE_BYTES // (1024 * 1024)} МБ.",
    )
    try:
        # Размер известен до чтения не всегда, поэтому проверяем дважды.
        if file.size is not None and file.size > MAX_REFERENCE_FILE_BYTES:
            raise too_big
        data = await file.read()
        if len(data) > MAX_REFERENCE_FILE_BYTES:
            raise too_big
        try:
            # Разбор книги синхронный и небыстрый: в цикле событий он
            # остановил бы все остальные запросы, поэтому уходит в поток.
            sections = await run_in_threadpool(import_file, file.filename or "", data)
        except ReferenceFileError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": str(exc)},
            ) from exc
        return ReferenceImportResponse(
            file_name=file.filename or "",
            counts={section: len(items) for section, items in sections.items()},
            sections={
                section: [ReferenceItemSchema.model_validate(item.to_dict()) for item in items]
                for section, items in sections.items()
            },
        )
    finally:
        await file.close()


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
