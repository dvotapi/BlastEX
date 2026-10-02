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
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from functools import lru_cache

from api import config
from api.schemas.cad import (
    CadAreaBasisInfoSchema,
    CadAreaBasisResponse,
    CadCrsResponse,
    CadCrsSchema,
    CadDefaultsSchema,
    CadEntitySchema,
    CadImportResponse,
    CadLayerSchema,
    CadMetaResponse,
    CadOriginSchema,
    CadParamsSchema,
    CadRoleSchema,
    CadRolesRequest,
    CadRolesResponse,
    CadSeriesVersionSchema,
    CadSituationKindSchema,
    CadSourceMetaRequest,
    CadSourceMetaResponse,
    CadSourceSchema,
    CadWarningSchema,
)
from sqlalchemy.exc import SQLAlchemyError

from cost.v2.models import ReferenceSnapshot
from cost.v2.repository import EconomicsRepository, EconomicsRepositoryError
from design.spatial.cad.model import (
    AREA_BASES,
    AREA_BASIS_CODES,
    DEFAULT_AREA_BASIS,
    LAYER_ONLY_ROLES,
    LAYER_ROLE_CODES,
    ORIGIN_TEMPLATE,
    ORIGINS,
    ROLE_CODES,
    ROLE_SITUATION,
    ROLES,
    SITUATION_KIND_CODES,
    SITUATION_KINDS,
    CadDrawing,
    CadEntity,
    CadWarning,
    ru_number,
)
from design.spatial.cad.crs import far_from_site, robust_extent_of
from design.spatial.cad.reader import CLOSURE_TOLERANCE_M, CadReadError, ReadOptions, read_cad
from design.spatial.cad.repository import (
    CadRepository,
    CadSourceConflict,
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
from design.spatial.cad.situation import (
    LayerKind,
    assign_kinds,
    order_versions,
    series_key,
    title_and_date_from_file_name,
)

# Чертёж блока с ситуацией весит сотни килобайт; десятки мегабайт — уже
# подложка всего карьера, разбирать её онлайн смысла нет.
MAX_FILE_BYTES = 40 * 1024 * 1024
MAX_FILES = 10
# Источников объекта в каталоге ситуации, в серии и при проверке СК.
MAX_SITE_SOURCES = 50

# Сколько раз повторить правку, если источник изменили между чтением и записью.
WRITE_ATTEMPTS = 3
CONFLICT_MESSAGE = (
    "Этот чертёж одновременно правят в другом окне. Закройте импорт и откройте чертёж заново."
)

GEOMETRY_NAMES = {"line": "линия", "point": "точка или знак", "text": "подпись"}


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
            area_basis=DEFAULT_AREA_BASIS,
        ),
        area_bases=[
            CadAreaBasisInfoSchema(code=code, label=label, description=description)
            for code, label, description in AREA_BASES
        ],
        situation_kinds=[CadSituationKindSchema(code=code, label=label) for code, label in SITUATION_KINDS],
    )


@dataclass
class SiteContext:
    """То, что ответу об источнике нужно знать об объекте: площадь блока, СК, другие источники."""

    area_basis: str = DEFAULT_AREA_BASIS
    crs: dict | None = None
    sources: list[CadSourceRecord] = field(default_factory=list)


def site_context(repository: CadRepository, organization_id: str, site_code: str) -> SiteContext:
    if not site_code:
        return SiteContext()
    return SiteContext(
        area_basis=area_basis_of(repository, organization_id, site_code),
        crs=repository.get_site_crs(organization_id, site_code),
        sources=repository.list_site_sources(organization_id, site_code, limit=MAX_SITE_SOURCES),
    )


def crs_named(crs: dict | None) -> bool:
    return bool(crs and str(crs.get("name") or "").strip())


def area_basis_of(repository: CadRepository, organization_id: str, site_code: str) -> str:
    """Площадь блока по соглашению маркшейдера объекта; без выбора — S ср."""

    if not site_code:
        return DEFAULT_AREA_BASIS
    saved = repository.get_area_basis(organization_id, site_code)
    return saved if saved in AREA_BASIS_CODES else DEFAULT_AREA_BASIS


def save_area_basis(
    repository: CadRepository, organization_id: str, actor: str, source_id: str, area_basis: str
) -> CadAreaBasisResponse:
    record = _require(repository, organization_id, source_id)
    if area_basis not in AREA_BASIS_CODES:
        raise CadImportError(f"Способ площади «{area_basis}» неизвестен.")
    if record.site_code:
        repository.set_area_basis(organization_id, record.site_code, area_basis, actor)
    return CadAreaBasisResponse(area_basis=area_basis, saved=bool(record.site_code))


def active_work_object_name(repository: EconomicsRepository, organization_id: str) -> str:
    """Активный объект работ организации.

    Как у «Кусковатости» «Проектирования» (#101): объект берёт сервер, а не
    шапка клиента — имя из закэшированного состояния могло устареть. Ошибка
    хранилища — не отказ импорта: шаблон просто не сохранится, с предупреждением.
    """

    try:
        workspace = repository.get_legacy_workspace(organization_id)
    except (EconomicsRepositoryError, SQLAlchemyError):
        return ""
    return (workspace.active_work_object_name if workspace else "").strip()


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
    site_crs = repository.get_site_crs(organization_id, site_code) if site_code else None

    # Тот же файл на том же объекте открывает прежний разбор: без копии байтов
    # и без лишней версии в серии ситуации. Без объекта файлы не делятся между
    # паспортами, и повтор не ищется.
    hashed = [(name, content, hashlib.sha256(content).hexdigest()) for name, content in files]
    reused: dict[str, CadSourceRecord] = {}
    to_read: list[tuple[str, bytes, str]] = []
    for name, content, sha in hashed:
        if sha in reused or any(sha == item[2] for item in to_read):
            continue
        found = repository.find_source_by_sha(organization_id, site_code, sha) if site_code else None
        if found is not None:
            reused[sha] = found
        else:
            to_read.append((name, content, sha))

    # Сначала читаются все новые файлы: нечитаемый файл не оставляет полузагрузки.
    drawings: list[tuple[str, bytes, str, CadDrawing]] = []
    for name, content, sha in to_read:
        try:
            drawings.append((name, content, sha, read_cad(content, name, _read_options(params))))
        except CadReadError as exc:
            raise CadImportError(f"«{name}»: {exc}") from exc

    items: list[tuple[CadSourceRecord, list[CadEntity]]] = []
    created: dict[str, tuple[CadSourceRecord, list[CadEntity]]] = {}
    new_layers: dict[str, str] = {}
    kind_template = _site_kind_template(template)
    for name, content, sha, drawing in drawings:
        assignment = assign_roles(drawing.entities, template, _role_params(params))
        kinds = assign_kinds(drawing.entities, kind_template)
        summary = _summary(
            drawing, assignment, kinds, manual_layers={}, site_code=site_code, work_object_name=work_object_name
        )
        title, name_date = title_and_date_from_file_name(name)
        record = CadSourceRecord(
            id=str(uuid.uuid4()),
            site_code=site_code,
            work_object_name=work_object_name.strip(),
            file_name=name,
            file_format=drawing.source_format,
            file_size=len(content),
            file_sha256=sha,
            params=params.model_dump(),
            summary=summary,
            uploaded_by=actor,
            # С микросекундами: «прежние чертежи объекта» для проверки СК
            # различаются и внутри одной загрузки, и в одну секунду.
            uploaded_at=datetime.now(timezone.utc),
            title=title,
            survey_date=survey_date or name_date,
            # Файл наследует СК объекта — её снимок на момент загрузки.
            coordinate_system=dict(site_crs) if crs_named(site_crs) else None,
            file_data=content,
        )
        items.append((record, drawing.entities))
        created[sha] = (record, drawing.entities)
        if site_code:
            # Следующий файл той же загрузки размечается уже с этими слоями.
            for layer in assignment.layers:
                new_layers.setdefault(layer.name, layer.role)
                template.setdefault(layer_key(layer.name), TemplateEntry(layer.role))

    if items:
        repository.create_sources(organization_id, items)
    if site_code and new_layers:
        repository.add_missing_layer_roles(organization_id, site_code, new_layers, actor)

    context = site_context(repository, organization_id, site_code)
    sources: list[CadSourceSchema] = []
    for name, _, sha in hashed:
        if sha in created:
            record, entities = created[sha]
            sources.append(_source_schema(record, entities, context))
            continue
        record = reused[sha]
        note = CadWarning(
            code="already_loaded",
            message=(
                f"Файл «{name}» уже загружен {record.uploaded_at:%d.%m.%Y} — открыт прежний разбор "
                "с его ролями, названием и датой."
            ),
            level="info",
        )
        entities = repository.list_entities(organization_id, record.id)
        sources.append(_source_schema(record, entities, context, notes=[note]))
    return CadImportResponse(sources=sources)


def get_source(repository: CadRepository, organization_id: str, source_id: str) -> CadSourceSchema:
    record = _require(repository, organization_id, source_id)
    return _source_schema(
        record,
        repository.list_entities(organization_id, source_id),
        site_context(repository, organization_id, record.site_code),
    )


def reparse(
    repository: CadRepository, organization_id: str, source_id: str, params: CadParamsSchema
) -> CadSourceSchema:
    record = _require(repository, organization_id, source_id, with_file=True)
    try:
        drawing = read_cad(record.file_data or b"", record.file_name, _read_options(params))
    except CadReadError as exc:
        raise CadImportError(f"«{record.file_name}»: {exc}") from exc

    for attempt in range(WRITE_ATTEMPTS):
        if attempt:
            # Источник изменили между чтением и записью — ручные роли берём свежие.
            record = _require(repository, organization_id, source_id)
        manual_entities = dict(record.summary.get("manual_entities") or {})
        manual_layers = dict(record.summary.get("manual_layers") or {})
        manual_kinds = dict(record.summary.get("manual_kinds") or {})
        template = _source_template(record.summary)
        assignment = assign_roles(drawing.entities, template, _role_params(params), manual_layers, manual_entities)
        kinds = assign_kinds(drawing.entities, _source_kind_template(record.summary), manual_kinds)
        summary = _summary(
            drawing,
            assignment,
            kinds,
            manual_layers=manual_layers,
            manual_entities=manual_entities,
            manual_kinds=manual_kinds,
            site_code=record.site_code,
            work_object_name=record.work_object_name,
        )
        try:
            repository.replace_entities(
                organization_id,
                source_id,
                drawing.entities,
                params.model_dump(),
                summary,
                expected_revision=record.revision,
            )
        except CadSourceConflict:
            continue
        record.params, record.summary = params.model_dump(), summary
        return _source_schema(
            record, drawing.entities, site_context(repository, organization_id, record.site_code)
        )
    raise CadImportError(CONFLICT_MESSAGE, status_code=409)


def save_roles(
    repository: CadRepository,
    organization_id: str,
    actor: str,
    source_id: str,
    request: CadRolesRequest,
) -> CadRolesResponse:
    """Правка ролей — разница к текущему состоянию.

    Две правки одного источника из разных окон не должны затирать друг друга:
    запись проходит, только если ревизия источника не сменилась с чтения, а
    иначе правка применяется заново к свежему состоянию — она разница, поэтому
    повтор безопасен.
    """

    for _ in range(WRITE_ATTEMPTS):
        try:
            return _save_roles_once(repository, organization_id, actor, source_id, request)
        except CadSourceConflict:
            continue
    raise CadImportError(CONFLICT_MESSAGE, status_code=409)


def _save_roles_once(
    repository: CadRepository,
    organization_id: str,
    actor: str,
    source_id: str,
    request: CadRolesRequest,
) -> CadRolesResponse:
    record = _require(repository, organization_id, source_id)
    entities = repository.list_entities(organization_id, source_id)
    layer_names = {item.layer for item in entities}
    handles = {item.handle for item in entities}

    for name, role in request.layers.items():
        if name not in layer_names:
            raise CadImportError(f"Слоя «{name}» нет в этом чертеже.")
        if role not in LAYER_ROLE_CODES:
            raise CadImportError(f"Роль «{role}» неизвестна.")
    geometry = {item.handle: item.geometry_type for item in entities}
    for handle, role in request.entities.items():
        if handle not in handles:
            raise CadImportError(f"Объекта {handle} нет в этом чертеже.")
        if role is None:
            continue
        if role not in ROLE_CODES:
            raise CadImportError(f"Роль «{role}» неизвестна.")
        info = next(item for item in ROLES if item.code == role)
        if geometry[handle] not in info.applies_to:
            raise CadImportError(
                f"Роль «{info.label}» не подходит объекту {handle} ({GEOMETRY_NAMES[geometry[handle]]})."
            )

    for name, kind in request.kinds.items():
        if name not in layer_names:
            raise CadImportError(f"Слоя «{name}» нет в этом чертеже.")
        if kind is not None and kind not in SITUATION_KIND_CODES:
            raise CadImportError(f"Вид «{kind}» неизвестен.")

    before = {item.handle: (item.role, item.role_origin) for item in entities}
    manual_layers = {**(record.summary.get("manual_layers") or {}), **request.layers}
    # Явные роли объектов хранятся отдельно: происхождение «вручную» есть и у
    # объектов, унаследовавших роль от слоя, заданного вручную, — их повторная
    # правка слоя должна перекрасить, а явные — нет.
    manual_entities = dict(record.summary.get("manual_entities") or {})
    for handle, role in request.entities.items():
        if role is None:
            manual_entities.pop(handle, None)
        else:
            manual_entities[handle] = role

    template = _source_template(record.summary)
    params = CadParamsSchema.model_validate(record.params)
    assignment = assign_roles(entities, template, _role_params(params), manual_layers, manual_entities)

    # Вид — только у слоёв, где после этой же правки есть объекты ситуации.
    situation_layers = {item.layer for item in entities if item.role == ROLE_SITUATION}
    for name in request.kinds:
        if name not in situation_layers:
            raise CadImportError(f"На слое «{name}» нет объектов ситуации — вид ему не нужен.")
    manual_kinds = dict(record.summary.get("manual_kinds") or {})
    kind_template = _source_kind_template(record.summary)
    for name, kind in request.kinds.items():
        if kind is None:
            # «По имени слоя»: и без ручного вида, и без вида из шаблона.
            manual_kinds.pop(name, None)
            kind_template.pop(layer_key(name), None)
        else:
            manual_kinds[name] = kind
    kinds = assign_kinds(entities, kind_template, manual_kinds)

    summary = dict(record.summary)
    summary["manual_layers"] = manual_layers
    summary["manual_entities"] = manual_entities
    summary["manual_kinds"] = manual_kinds
    summary["layer_kinds"] = [item.to_dict() for item in kinds]
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
    repository.update_roles(organization_id, source_id, changed, summary, expected_revision=record.revision)
    if record.site_code and request.layers:
        repository.upsert_layer_roles(organization_id, record.site_code, request.layers, actor)
    if record.site_code and request.kinds:
        repository.upsert_layer_kinds(organization_id, record.site_code, dict(request.kinds), actor)
    return CadRolesResponse(
        id=record.id,
        template_saved=bool(record.site_code),
        floor_z_m=summary.get("floor_z_m"),
        warnings=_warnings(summary),
        layers=_layer_schemas(summary, entities),
        roles={handle: [role, origin] for handle, (role, origin) in changed.items()},
        overrides=sorted(manual_entities),
    )


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


def _site_kind_template(template: dict[str, TemplateEntry]) -> dict[str, str]:
    """Виды слоёв ситуации, заданные человеком на объекте."""

    return {key: entry.kind for key, entry in template.items() if entry.kind}


def _source_kind_template(summary: dict) -> dict[str, str]:
    """Виды из шаблона в том виде, каким он был при импорте этого файла (как роли)."""

    return {
        layer_key(entry["name"]): entry["kind"]
        for entry in summary.get("layer_kinds") or []
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
    kinds: list[LayerKind],
    *,
    manual_layers: dict[str, str],
    manual_entities: dict[str, str] | None = None,
    manual_kinds: dict[str, str] | None = None,
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
        "manual_entities": dict(manual_entities or {}),
        "floor_z_m": assignment.floor_z_m,
        "layer_kinds": [item.to_dict() for item in kinds],
        "manual_kinds": dict(manual_kinds or {}),
        # Габарит без выбросов — для проверки СК по прежним чертежам объекта.
        "robust_extent": list(extent) if (extent := robust_extent_of(drawing.entities)) else None,
    }


def layer_kinds(summary: dict, entities: list[CadEntity]) -> dict[str, dict]:
    """Вид объектов ситуации по слоям; у файлов, загруженных до PR 4, — по имени слоя."""

    if "layer_kinds" in summary:
        entries = summary.get("layer_kinds") or []
    else:
        entries = [item.to_dict() for item in assign_kinds(entities, {})]
    return {entry["name"]: entry for entry in entries}


def _layer_schemas(summary: dict, entities: list[CadEntity]) -> list[CadLayerSchema]:
    colors = summary.get("layer_colors") or {}
    kinds = layer_kinds(summary, entities)
    # Один проход по объектам: слоёв бывают сотни, объектов — десятки тысяч.
    by_layer: dict[str, list[CadEntity]] = {}
    for item in entities:
        by_layer.setdefault(item.layer, []).append(item)
    layers: list[CadLayerSchema] = []
    for entry in summary.get("layer_roles") or []:
        members = by_layer.get(entry["name"], [])
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
                situation_kind=(kinds.get(entry["name"]) or {}).get("kind"),
                situation_kind_origin=(kinds.get(entry["name"]) or {}).get("origin"),
            )
        )
    return layers


def _entity_schema(item: CadEntity, overrides: frozenset[str] = frozenset()) -> CadEntitySchema:
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
        role_override=item.handle in overrides,
    )


def _warnings(summary: dict) -> list[CadWarningSchema]:
    raw = [*(summary.get("read_warnings") or []), *(summary.get("role_warnings") or [])]
    return [CadWarningSchema(**item) for item in raw]


def _series(record: CadSourceRecord, context: SiteContext) -> list[CadSeriesVersionSchema]:
    """Другие версии серии: источники объекта с тем же названием, свежие первыми."""

    key = series_key(source_title(record))
    others = [item for item in context.sources if item.id != record.id and series_key(source_title(item)) == key]
    return [
        CadSeriesVersionSchema(
            id=item.id,
            title=source_title(item),
            file_name=item.file_name,
            survey_date=item.survey_date.isoformat() if item.survey_date else None,
            uploaded_at=item.uploaded_at.isoformat(),
        )
        for item in order_versions(others)
    ]


def source_title(record: CadSourceRecord) -> str:
    return record.title or title_and_date_from_file_name(record.file_name)[0]


def _check_extent(summary: dict) -> list[float] | None:
    return summary.get("robust_extent") or summary.get("extent")


def _crs_warnings(record: CadSourceRecord, context: SiteContext) -> list[CadWarningSchema]:
    """СК объекта не задана — подсказка; чертёж дальше 5 км от прежних — предупреждение."""

    if not record.site_code:
        return []
    warnings: list[CadWarningSchema] = []
    if not crs_named(context.crs):
        warnings.append(
            CadWarningSchema(
                code="crs_missing",
                message=(
                    "У объекта не задана система координат. Задайте её один раз в строке «СК объекта» — "
                    "следующие файлы её унаследуют."
                ),
                level="info",
            )
        )
    # «Экстент объекта» — чертежи, загруженные до этого файла: первый файл не
    # проверяется, и прежний не начинает «тревожить» из-за нового чужого.
    others = [
        _check_extent(item.summary or {})
        for item in context.sources
        if item.id != record.id and item.uploaded_at < record.uploaded_at
    ]
    distance = far_from_site(_check_extent(record.summary or {}), others)
    if distance is not None:
        warnings.append(
            CadWarningSchema(
                code="crs_far",
                message=(
                    f"Чертёж лежит в {ru_number(distance / 1000, 1)} км от прежних чертежей объекта — "
                    "другая система координат или условные координаты? Координаты не пересчитываются."
                ),
            )
        )
    return warnings


def _source_schema(
    record: CadSourceRecord,
    entities: list[CadEntity],
    context: SiteContext,
    notes: list[CadWarning] | None = None,
) -> CadSourceSchema:
    summary = record.summary or {}
    overrides = frozenset(summary.get("manual_entities") or {})
    return CadSourceSchema(
        id=record.id,
        file_name=record.file_name,
        title=source_title(record),
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
        area_basis=context.area_basis,
        crs=CadCrsSchema(**context.crs) if crs_named(context.crs) else None,
        series=_series(record, context),
        warnings=[
            *(CadWarningSchema(**item.to_dict()) for item in notes or []),
            *_warnings(summary),
            *_crs_warnings(record, context),
        ],
        layers=_layer_schemas(summary, entities),
        entities=[_entity_schema(item, overrides) for item in entities],
    )


# --- название, дата и СК объекта (PR 4) ---------------------------------


def update_meta(
    repository: CadRepository, organization_id: str, source_id: str, request: CadSourceMetaRequest
) -> CadSourceMetaResponse:
    """Название и дата съёмки источника. Поле, которого нет в запросе, не меняется."""

    fields = request.model_fields_set
    title = (request.title or "").strip() if "title" in fields else None
    if title is not None and not title:
        raise CadImportError("Название не может быть пустым: по нему источник попадает в серию ситуации.")
    survey_date = parse_survey_date(request.survey_date or "") if "survey_date" in fields else None
    for _ in range(WRITE_ATTEMPTS):
        record = _require(repository, organization_id, source_id)
        new_title = title if title is not None else source_title(record)
        new_date = survey_date if "survey_date" in fields else record.survey_date
        try:
            repository.update_source_meta(
                organization_id,
                source_id,
                title=new_title,
                survey_date=new_date,
                expected_revision=record.revision,
            )
        except CadSourceConflict:
            continue
        record.title, record.survey_date = new_title, new_date
        context = site_context(repository, organization_id, record.site_code)
        return CadSourceMetaResponse(
            id=record.id,
            title=new_title,
            survey_date=new_date.isoformat() if new_date else None,
            series=_series(record, context),
        )
    raise CadImportError(CONFLICT_MESSAGE, status_code=409)


def save_crs(
    repository: CadRepository, organization_id: str, actor: str, source_id: str, crs: CadCrsSchema
) -> CadCrsResponse:
    """СК объекта источника: задаётся один раз, следующие файлы её наследуют."""

    record = _require(repository, organization_id, source_id)
    value = {"name": crs.name.strip(), "height_system": crs.height_system.strip(), "epsg": crs.epsg}
    if record.site_code:
        repository.set_site_crs(organization_id, record.site_code, value, actor)
    context = site_context(repository, organization_id, record.site_code)
    return CadCrsResponse(
        crs=CadCrsSchema(**context.crs) if crs_named(context.crs) else None,
        saved=bool(record.site_code),
        warnings=[*_warnings(record.summary or {}), *_crs_warnings(record, context)],
    )
