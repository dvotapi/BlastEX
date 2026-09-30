"""Импорт чертежа маркшейдера: чтение, разметка ролей, хранение (TASK-013).

Источник хранит исходный файл, параметры разбора и сводку: предупреждения
чтения, роли слоёв и ручные роли слоёв. Ручные роли сущностей живут в самих
сущностях (происхождение «вручную»), поэтому повторный разбор их не теряет.
Шаблон слоёв объекта пополняется при каждой загрузке (только новыми слоями)
и перезаписывается ручной правкой роли слоя.
"""
from __future__ import annotations

import hashlib
import uuid
from collections import Counter
from datetime import date, datetime, timezone
from functools import lru_cache

from api import config
from api.schemas.cad import (
    CadDefaultsSchema,
    CadEntitySchema,
    CadImportResponse,
    CadLayerSchema,
    CadMetaResponse,
    CadOriginSchema,
    CadParamsSchema,
    CadRoleSchema,
    CadRolesRequest,
    CadSourceSchema,
    CadWarningSchema,
)
from cost.v2.models import ReferenceSnapshot
from design.spatial.cad.model import (
    LAYER_ONLY_ROLES,
    LAYER_ROLE_CODES,
    ORIGIN_MANUAL,
    ORIGIN_TEMPLATE,
    ORIGINS,
    ROLE_CODES,
    ROLES,
    CadDrawing,
    CadEntity,
    CadWarning,
)
from design.spatial.cad.reader import CLOSURE_TOLERANCE_M, CadReadError, ReadOptions, read_cad
from design.spatial.cad.repository import (
    CadRepository,
    CadSourceNotFound,
    CadSourceRecord,
    PostgresCadRepository,
)
from design.spatial.cad.roles import (
    DEFAULT_BENCH_HEIGHT_M,
    RoleAssignment,
    RoleParams,
    TemplateEntry,
    assign_roles,
    layer_key,
)

# Чертёж блока с ситуацией весит сотни килобайт; десятки мегабайт — уже
# подложка всего карьера, разбирать её онлайн смысла нет.
MAX_FILE_BYTES = 40 * 1024 * 1024
MAX_FILES = 10


class CadImportError(Exception):
    """Ошибка импорта для пользователя; `status_code` — HTTP-код ответа."""

    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@lru_cache(maxsize=4)
def _postgres_repository(database_url: str) -> CadRepository:
    return PostgresCadRepository(database_url)


def get_cad_repository() -> CadRepository:
    return _postgres_repository(config.database_url())


def meta() -> CadMetaResponse:
    return CadMetaResponse(
        roles=[CadRoleSchema(code=item.code, label=item.label, applies_to=list(item.applies_to)) for item in ROLES],
        layer_roles=[
            CadRoleSchema(code=item.code, label=item.label, applies_to=list(item.applies_to))
            for item in LAYER_ONLY_ROLES
        ],
        origins=[CadOriginSchema(code=code, label=label) for code, label in ORIGINS.items()],
        defaults=CadDefaultsSchema(
            label_radius_m=ReadOptions().label_radius_m,
            closure_tolerance_m=CLOSURE_TOLERANCE_M,
            bench_height_m=DEFAULT_BENCH_HEIGHT_M,
            max_file_mb=MAX_FILE_BYTES // (1024 * 1024),
            max_files=MAX_FILES,
        ),
    )


def resolve_site_code(snapshot: ReferenceSnapshot | None, work_object_name: str) -> str:
    """Код объекта по имени из опубликованной ревизии справочника «sites»."""

    name = (work_object_name or "").strip()
    if not name or snapshot is None:
        return ""
    for item in snapshot.active_items("sites"):
        if item.name.strip() == name:
            return item.code
    return ""


def parse_survey_date(value: str) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise CadImportError(f"Дата съёмки «{text}» не похожа на дату ГГГГ-ММ-ДД.") from exc


def check_file_size(name: str, size: int) -> None:
    if size > MAX_FILE_BYTES:
        raise CadImportError(
            f"Файл «{name}» больше {MAX_FILE_BYTES // (1024 * 1024)} МБ. "
            "Оставьте в чертеже блок и ближайшую ситуацию.",
            status_code=413,
        )


# --- сценарии -----------------------------------------------------------


def import_files(
    repository: CadRepository,
    organization_id: str,
    actor: str,
    files: list[tuple[str, bytes]],
    params: CadParamsSchema,
    work_object_name: str,
    survey_date: date | None,
    snapshot: ReferenceSnapshot | None,
) -> CadImportResponse:
    if not files:
        raise CadImportError("Выберите хотя бы один файл DXF или DWG.")
    if len(files) > MAX_FILES:
        raise CadImportError(f"За один раз можно загрузить не больше {MAX_FILES} файлов.")
    for name, content in files:
        check_file_size(name, len(content))

    site_code = resolve_site_code(snapshot, work_object_name)
    template = repository.get_layer_template(organization_id, site_code) if site_code else {}

    # Сначала читаются все файлы: нечитаемый файл не оставляет полузагрузки.
    drawings: list[tuple[str, bytes, CadDrawing]] = []
    for name, content in files:
        try:
            drawings.append((name, content, read_cad(content, name, _read_options(params))))
        except CadReadError as exc:
            raise CadImportError(f"«{name}»: {exc}") from exc

    items: list[tuple[CadSourceRecord, list[CadEntity]]] = []
    new_layers: dict[str, str] = {}
    for name, content, drawing in drawings:
        assignment = assign_roles(drawing.entities, template, _role_params(params))
        summary = _summary(drawing, assignment, manual_layers={}, site_code=site_code, work_object_name=work_object_name)
        record = CadSourceRecord(
            id=str(uuid.uuid4()),
            site_code=site_code,
            work_object_name=work_object_name.strip(),
            file_name=name,
            file_format=drawing.source_format,
            file_size=len(content),
            file_sha256=hashlib.sha256(content).hexdigest(),
            params=params.model_dump(),
            summary=summary,
            uploaded_by=actor,
            uploaded_at=datetime.now(timezone.utc).replace(microsecond=0),
            survey_date=survey_date,
            file_data=content,
        )
        items.append((record, drawing.entities))
        if site_code:
            # Следующий файл той же загрузки размечается уже с этими слоями.
            for layer in assignment.layers:
                new_layers.setdefault(layer.name, layer.role)
                template.setdefault(layer_key(layer.name), TemplateEntry(layer.role))

    repository.create_sources(organization_id, items)
    if site_code and new_layers:
        repository.add_missing_layer_roles(organization_id, site_code, new_layers, actor)
    sources = [_source_schema(record, entities) for record, entities in items]
    return CadImportResponse(sources=sources)


def get_source(repository: CadRepository, organization_id: str, source_id: str) -> CadSourceSchema:
    record = _require(repository, organization_id, source_id)
    return _source_schema(record, repository.list_entities(organization_id, source_id))


def reparse(
    repository: CadRepository, organization_id: str, source_id: str, params: CadParamsSchema
) -> CadSourceSchema:
    record = _require(repository, organization_id, source_id, with_file=True)
    try:
        drawing = read_cad(record.file_data or b"", record.file_name, _read_options(params))
    except CadReadError as exc:
        raise CadImportError(f"«{record.file_name}»: {exc}") from exc

    manual_entities = {
        item.handle: item.role
        for item in repository.list_entities(organization_id, source_id)
        if item.role_origin == ORIGIN_MANUAL
    }
    manual_layers = dict(record.summary.get("manual_layers") or {})
    template = _source_template(record.summary)
    assignment = assign_roles(drawing.entities, template, _role_params(params), manual_layers, manual_entities)
    summary = _summary(
        drawing,
        assignment,
        manual_layers=manual_layers,
        site_code=record.site_code,
        work_object_name=record.work_object_name,
    )
    repository.replace_entities(organization_id, source_id, drawing.entities, params.model_dump(), summary)
    record.params, record.summary = params.model_dump(), summary
    return _source_schema(record, drawing.entities)


def save_roles(
    repository: CadRepository,
    organization_id: str,
    actor: str,
    source_id: str,
    request: CadRolesRequest,
) -> CadSourceSchema:
    record = _require(repository, organization_id, source_id)
    entities = repository.list_entities(organization_id, source_id)
    layer_names = {item.layer for item in entities}
    handles = {item.handle for item in entities}

    for name, role in request.layers.items():
        if name not in layer_names:
            raise CadImportError(f"Слоя «{name}» нет в этом чертеже.")
        if role not in LAYER_ROLE_CODES:
            raise CadImportError(f"Роль «{role}» неизвестна.")
    for handle, role in request.entities.items():
        if handle not in handles:
            raise CadImportError(f"Объекта {handle} нет в этом чертеже.")
        if role is not None and role not in ROLE_CODES:
            raise CadImportError(f"Роль «{role}» неизвестна.")

    before = {item.handle: (item.role, item.role_origin) for item in entities}
    manual_layers = {**(record.summary.get("manual_layers") or {}), **request.layers}
    manual_entities = {item.handle: item.role for item in entities if item.role_origin == ORIGIN_MANUAL}
    for handle, role in request.entities.items():
        if role is None:
            manual_entities.pop(handle, None)
        else:
            manual_entities[handle] = role

    template = _source_template(record.summary)
    params = CadParamsSchema.model_validate(record.params)
    assignment = assign_roles(entities, template, _role_params(params), manual_layers, manual_entities)

    summary = dict(record.summary)
    summary["manual_layers"] = manual_layers
    summary["layer_roles"] = [
        _layer_entry(layer) for layer in assignment.layers
    ]
    summary["floor_z_m"] = assignment.floor_z_m
    summary["role_warnings"] = [item.to_dict() for item in assignment.warnings]
    changed = {
        item.handle: (item.role, item.role_origin)
        for item in entities
        if before[item.handle] != (item.role, item.role_origin)
    }
    repository.update_roles(organization_id, source_id, changed, summary)
    if record.site_code and request.layers:
        repository.upsert_layer_roles(organization_id, record.site_code, request.layers, actor)
    record.summary = summary
    return _source_schema(record, entities)


# --- сборка ответа ------------------------------------------------------


def _read_options(params: CadParamsSchema) -> ReadOptions:
    return ReadOptions(scale=params.scale, label_radius_m=params.label_radius_m)


def _role_params(params: CadParamsSchema) -> RoleParams:
    return RoleParams(floor_z_m=params.floor_z_m, bench_height_m=params.bench_height_m)


def _layer_entry(layer) -> dict:
    return {"name": layer.name, "role": layer.role, "origin": layer.origin, "confirmed": layer.confirmed}


def _source_template(summary: dict) -> dict[str, TemplateEntry]:
    """Шаблон объекта в том виде, каким он был при импорте этого файла.

    Загрузка сама пополняет шаблон объекта ролями «авто»; если пересчитывать
    роли уже загруженного файла по текущему шаблону, после первой же правки
    все его слои сменили бы бейдж «авто» на «шаблон».
    """

    return {
        layer_key(entry["name"]): TemplateEntry(entry["role"], bool(entry.get("confirmed")))
        for entry in summary.get("layer_roles") or []
        if entry.get("origin") == ORIGIN_TEMPLATE
    }


def _require(
    repository: CadRepository, organization_id: str, source_id: str, *, with_file: bool = False
) -> CadSourceRecord:
    record = repository.get_source(organization_id, source_id, with_file=with_file)
    if record is None:
        raise CadSourceNotFound(source_id)
    return record


def _summary(
    drawing: CadDrawing,
    assignment: RoleAssignment,
    *,
    manual_layers: dict[str, str],
    site_code: str,
    work_object_name: str,
) -> dict:
    template_warnings: list[CadWarning] = []
    if not site_code:
        reason = (
            f"Объект «{work_object_name.strip()}» не найден в справочнике"
            if work_object_name.strip()
            else "Объект работ не выбран"
        )
        template_warnings.append(
            CadWarning(
                code="template_not_saved",
                message=f"{reason} — роли слоёв не сохранятся в шаблон объекта.",
            )
        )
    return {
        "insunits": drawing.insunits,
        "extent": list(drawing.extent) if drawing.extent else None,
        "suggested_scale": drawing.suggested_scale,
        "minimal_dxf": drawing.minimal_dxf,
        "layer_colors": drawing.layers,
        "read_warnings": [item.to_dict() for item in [*drawing.warnings, *template_warnings]],
        "role_warnings": [item.to_dict() for item in assignment.warnings],
        "layer_roles": [
            _layer_entry(layer) for layer in assignment.layers
        ],
        "manual_layers": manual_layers,
        "floor_z_m": assignment.floor_z_m,
    }


def _layer_schemas(summary: dict, entities: list[CadEntity]) -> list[CadLayerSchema]:
    colors = summary.get("layer_colors") or {}
    layers: list[CadLayerSchema] = []
    for entry in summary.get("layer_roles") or []:
        members = [item for item in entities if item.layer == entry["name"]]
        measured = [item for item in members if item.geometry_type != "text"]
        layers.append(
            CadLayerSchema(
                name=entry["name"],
                role=entry["role"],
                origin=entry["origin"],
                entity_count=len(members),
                kinds=dict(Counter(item.kind for item in members)),
                z_min=min((item.z_min for item in measured), default=None),
                z_max=max((item.z_max for item in measured), default=None),
                color=colors.get(entry["name"]),
                counts_by_role=dict(sorted(Counter(item.role for item in members).items())),
            )
        )
    return layers


def _entity_schema(item: CadEntity) -> CadEntitySchema:
    return CadEntitySchema(
        handle=item.handle,
        layer=item.layer,
        kind=item.kind,
        geometry_type=item.geometry_type,
        points=[list(point) for point in item.points],
        closed=item.closed,
        closed_by_gap=item.closed_by_gap,
        vertex_count=item.vertex_count,
        length_m=round(item.length_m, 3),
        area_m2=round(item.area_m2, 2),
        z_kind=item.z_kind,
        z_min=item.z_min,
        z_max=item.z_max,
        z_from_label=item.z_from_label,
        text=item.text,
        color=item.color,
        role=item.role,
        role_origin=item.role_origin,
    )


def _source_schema(record: CadSourceRecord, entities: list[CadEntity]) -> CadSourceSchema:
    summary = record.summary or {}
    warnings = [*(summary.get("read_warnings") or []), *(summary.get("role_warnings") or [])]
    return CadSourceSchema(
        id=record.id,
        file_name=record.file_name,
        format=record.file_format,
        site_code=record.site_code,
        work_object_name=record.work_object_name,
        uploaded_at=record.uploaded_at.isoformat(),
        uploaded_by=record.uploaded_by,
        survey_date=record.survey_date.isoformat() if record.survey_date else None,
        params=CadParamsSchema.model_validate(record.params),
        insunits=summary.get("insunits"),
        suggested_scale=summary.get("suggested_scale"),
        extent=summary.get("extent"),
        floor_z_m=summary.get("floor_z_m"),
        template_saved=bool(record.site_code),
        warnings=[CadWarningSchema(**item) for item in warnings],
        layers=_layer_schemas(summary, entities),
        entities=[_entity_schema(item) for item in entities],
    )
