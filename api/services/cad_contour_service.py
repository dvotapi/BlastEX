"""Контур блока из импортированного чертежа (TASK-013, PR 2).

Два сценария:

- «линии для контура» — места разреза линий выбранных ролей в пересечениях
  (по ним щелчок в сборке берёт участок) и сшитые бровки с разрывами;
- «контур» — предпросмотр любого из четырёх способов: кольцо, ошибки для
  кнопки «Построить блок», оба контура, свободная поверхность, фланги и
  отметки уступа.

Геометрия — `design/spatial/cad/` (shapely); здесь только чтение сущностей
источника с изоляцией по организации и сборка ответа. Проблема контура —
не HTTP-ошибка: предпросмотр показывает её у кнопки.
"""
from __future__ import annotations

from api.schemas.cad import (
    CadBenchSchema,
    CadContourIssueSchema,
    CadContourItemSchema,
    CadContourLinesRequest,
    CadContourLinesResponse,
    CadContourRequest,
    CadContourResponse,
    CadFlankSchema,
    CadGapSchema,
    CadItemInfoSchema,
    CadRingSchema,
    CadStitchedLineSchema,
    CadStitchPartSchema,
    CadWarningSchema,
)
from api.services.cad_service import CadImportError
from design.spatial.cad.contour import (
    ContourDraft,
    ContourInputError,
    ContourItem,
    assemble,
    click_contour,
    crest_block,
    ready_contour,
    split_lines,
)
from design.spatial.cad.model import ROLE_CREST_BOTTOM, ROLE_CREST_TOP, ROLES, CadEntity
from design.spatial.cad.repository import CadRepository, CadSourceNotFound, CadSourceRecord
from design.spatial.cad.rings import ring_area, ring_perimeter
from design.spatial.cad.stitch import StitchedLine, StitchGap, stitch_lines
from design.spatial.cad.two_contours import BenchLevels, TwoContours, bench_levels, two_contours

LINE_ROLES = frozenset(item.code for item in ROLES if "line" in item.applies_to)
CREST_ROLES = {ROLE_CREST_TOP, ROLE_CREST_BOTTOM}


def _require(repository: CadRepository, organization_id: str, source_id: str) -> CadSourceRecord:
    record = repository.get_source(organization_id, source_id)
    if record is None:
        raise CadSourceNotFound(source_id)
    return record


def _line_roles(roles: list[str]) -> set[str]:
    unknown = [role for role in roles if role not in LINE_ROLES]
    if unknown:
        raise CadImportError(f"Роль «{unknown[0]}» не подходит линиям контура.")
    return set(roles)


def _lines(entities: list[CadEntity]) -> list[CadEntity]:
    return [item for item in entities if item.geometry_type == "line" and len(item.points) >= 2]


def _crests(entities: list[CadEntity]) -> tuple[list[StitchedLine], list[StitchedLine], list[StitchGap], list[StitchGap]]:
    tops, top_gaps = stitch_lines([item for item in _lines(entities) if item.role == ROLE_CREST_TOP])
    bottoms, bottom_gaps = stitch_lines([item for item in _lines(entities) if item.role == ROLE_CREST_BOTTOM])
    return tops, bottoms, top_gaps, bottom_gaps


def _stitched_schema(line: StitchedLine) -> CadStitchedLineSchema:
    return CadStitchedLineSchema(
        points=[list(point) for point in line.points],
        parts=[
            CadStitchPartSchema(
                handle=part.handle, reversed=part.reversed, length_m=part.length_m, chain_start_m=part.chain_start_m
            )
            for part in line.parts
        ],
        length_m=line.length_m,
    )


def _gap_schema(role: str, gap: StitchGap) -> CadGapSchema:
    return CadGapSchema(role=role, a=list(gap.a), b=list(gap.b), distance_m=gap.distance_m, reason=gap.reason)


def lines(
    repository: CadRepository, organization_id: str, source_id: str, request: CadContourLinesRequest
) -> CadContourLinesResponse:
    _require(repository, organization_id, source_id)
    roles = _line_roles(request.roles)
    entities = repository.list_entities(organization_id, source_id, roles=roles | CREST_ROLES)
    try:
        splits, crossings = split_lines([item for item in _lines(entities) if item.role in roles])
    except ContourInputError as exc:
        raise CadImportError(str(exc)) from exc
    tops, bottoms, top_gaps, bottom_gaps = _crests(entities)
    return CadContourLinesResponse(
        splits=splits,
        intersections=[list(point) for point in crossings],
        crests_top=[_stitched_schema(line) for line in tops],
        crests_bottom=[_stitched_schema(line) for line in bottoms],
        gaps=[
            *(_gap_schema(ROLE_CREST_TOP, gap) for gap in top_gaps),
            *(_gap_schema(ROLE_CREST_BOTTOM, gap) for gap in bottom_gaps),
        ],
    )


def _draft(
    repository: CadRepository, organization_id: str, source_id: str, request: CadContourRequest
) -> tuple[ContourDraft, list[CadEntity]]:
    """Черновик контура выбранным способом и сущности бровок для двух контуров."""

    crests = repository.list_entities(organization_id, source_id, roles=CREST_ROLES)
    method = request.method
    if method == "ready":
        found = _lines(repository.list_entities(organization_id, source_id, handles={request.handle}))
        if not found:
            raise CadImportError(f"Линии {request.handle or '—'} нет в этом чертеже.")
        return ready_contour(found[0], request.tolerance_m), crests

    if method == "click":
        if request.point is None:
            raise CadImportError("Укажите точку внутри контура.")
        roles = _line_roles(request.roles)
        entities = _lines(repository.list_entities(organization_id, source_id, roles=roles))
        return click_contour(entities, (request.point[0], request.point[1]), request.tolerance_m, request.bridge_m), crests

    items = [_item(item) for item in request.items]
    if method == "assembly":
        handles = {item.handle for item in items if item.kind == "part"}
        entities = {item.handle: item for item in _lines(repository.list_entities(organization_id, source_id, handles=handles))}
        missing = sorted(handles - set(entities))
        if missing:
            raise CadImportError(f"Объекта {missing[0]} нет среди линий этого чертежа.")
        return assemble(items, entities, request.tolerance_m), crests

    if request.crest is None:
        raise CadImportError("Отметьте начало и конец блока на верхней бровке и задайте ширину.")
    tops, bottoms, _, _ = _crests(crests)
    by_handle = {item.handle: item for item in _lines(crests)}
    crest = request.crest
    draft = crest_block(
        tops,
        bottoms,
        by_handle,
        (crest.start[0], crest.start[1]),
        (crest.end[0], crest.end[1]),
        crest.width_m,
        crest.side,
        request.tolerance_m,
    )
    return draft, crests


def _item(schema: CadContourItemSchema) -> ContourItem:
    return ContourItem(
        kind=schema.kind,
        handle=schema.handle,
        start_m=schema.start_m,
        end_m=schema.end_m,
        points=[(point[0], point[1]) for point in schema.points if len(point) >= 2],
        flip=schema.flip,
        label=schema.label,
    )


def contour(
    repository: CadRepository, organization_id: str, source_id: str, request: CadContourRequest
) -> CadContourResponse:
    record = _require(repository, organization_id, source_id)
    try:
        draft, crest_entities = _draft(repository, organization_id, source_id, request)
    except ContourInputError as exc:
        raise CadImportError(str(exc)) from exc

    response = CadContourResponse(
        ok=draft.ok,
        method=request.method,
        issues=[CadContourIssueSchema(**issue.to_dict()) for issue in draft.issues],
        warnings=[CadWarningSchema(**warning.to_dict()) for warning in draft.warnings],
        closings=[[list(a), list(b)] for a, b in draft.closings],
        items=[CadContourItemSchema(**item.to_dict()) for item in draft.items],
        item_info=[CadItemInfoSchema(**vars(info)) for info in draft.item_info],
        crest_line=[list(point) for point in draft.crest_line] if draft.crest_line else None,
    )
    if draft.ring:
        response.top = CadRingSchema(
            points=[list(point) for point in draft.ring],
            area_m2=ring_area(draft.ring),
            perimeter_m=ring_perimeter(draft.ring),
        )
    if not draft.ok:
        return response

    tops, bottoms, _, _ = _crests(crest_entities)
    face_lines = [StitchedLine(points=[(x, y, 0.0) for x, y in draft.crest_line])] if draft.crest_line else None
    two = two_contours(draft.ring, tops, bottoms, face_lines=face_lines)
    floor_z = record.params.get("floor_z_m")
    if floor_z is None:
        floor_z = record.summary.get("floor_z_m")
    levels = bench_levels(draft.ring, two.free_faces, tops, bottoms, floor_z)
    _fill(response, two, levels)
    return response


def _fill(response: CadContourResponse, two: TwoContours, levels: BenchLevels) -> None:
    response.bottom = CadRingSchema(
        points=[list(point) for point in two.bottom],
        area_m2=two.area_bottom_m2,
        perimeter_m=ring_perimeter(two.bottom),
    )
    response.mean_area_m2 = two.area_mean_m2
    response.free_faces = [list(edge) for edge in two.free_faces]
    response.flanks = [
        CadFlankSchema(start=list(flank.start), end=list(flank.end) if flank.end else None, length_m=flank.length_m)
        for flank in two.flanks
    ]
    response.warnings.extend(CadWarningSchema(**warning.to_dict()) for warning in [*two.warnings, *levels.warnings])
    response.bench = CadBenchSchema(
        crest_z_m=levels.crest_z_m,
        toe_z_m=levels.toe_z_m,
        height_m=levels.height_m,
        crest_source=levels.crest_source,
        toe_source=levels.toe_source,
    )
