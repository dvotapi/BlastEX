"""Кровля блока из импортированного чертежа (TASK-013, PR 3).

Предпросмотр шага «Поверхность»: TIN кровли с ограничителями, качество,
выбросы, конфликты отметок, пороги нижней бровки, средняя высота уступа и
объёмы. Геометрия — `design/spatial/cad/surface*.py`; здесь только чтение
сущностей источника с изоляцией по организации и сборка ответа. Ошибки
входа (пределы, неизвестная точка или роль) — 422, ошибка построения — в
ответе.
"""
from __future__ import annotations

from api.schemas.cad import (
    CadConflictSchema,
    CadConflictValueSchema,
    CadContourIssueSchema,
    CadExcludedPointSchema,
    CadOutlierSchema,
    CadSnappedSchema,
    CadSurfaceBenchSchema,
    CadSurfaceQualitySchema,
    CadSurfaceRequest,
    CadSurfaceResponse,
    CadSurfaceVolumeSchema,
    CadThresholdSchema,
    CadTinSchema,
    CadWarningSchema,
)
from api.services.cad_service import CadImportError
from design.spatial.cad.model import CadEntity
from design.spatial.cad.repository import CadRepository, CadSourceNotFound, CadSourceRecord
from design.spatial.cad.surface import Roof, build_roof
from design.spatial.cad.surface_builder import SurfaceBuildError, make_builder
from design.spatial.cad.surface_data import SURFACE_ROLES, SurfaceInputError


def _require(repository: CadRepository, organization_id: str, source_id: str) -> CadSourceRecord:
    record = repository.get_source(organization_id, source_id)
    if record is None:
        raise CadSourceNotFound(source_id)
    return record


def _roles(roles: list[str]) -> set[str]:
    unknown = [role for role in roles if role not in SURFACE_ROLES]
    if unknown:
        raise CadImportError(f"Роль «{unknown[0]}» в кровлю не входит.")
    return set(roles)


def _split_id(point_id: str) -> tuple[str, int | None]:
    """«handle» — точка, «handle:n» — n-я вершина линии съёмки."""

    handle, sep, number = point_id.rpartition(":")
    if sep and number.isdigit():
        return handle, int(number)
    return point_id, None


def _excluded_points(
    repository: CadRepository, organization_id: str, source_id: str, excluded: list[str], entities: list[CadEntity]
) -> list[CadExcludedPointSchema]:
    """Исключённые отметки с местом; неизвестная — ошибка ввода."""

    if not excluded:
        return []
    known = {item.handle: item for item in entities}
    wanted = {_split_id(item)[0] for item in excluded} - set(known)
    if wanted:
        known.update({item.handle: item for item in repository.list_entities(organization_id, source_id, handles=wanted)})
    points = []
    for point_id in excluded:
        handle, number = _split_id(point_id)
        entity = known.get(handle)
        index = 0 if number is None else number
        if entity is None or entity.geometry_type == "text" or index >= len(entity.points) or (
            number is None and entity.geometry_type != "point"
        ):
            raise CadImportError(f"Отметки {point_id} нет в этом чертеже.")
        points.append(CadExcludedPointSchema(id=point_id, point=list(entity.points[index])))
    return points


def surface(
    repository: CadRepository, organization_id: str, source_id: str, request: CadSurfaceRequest
) -> CadSurfaceResponse:
    record = _require(repository, organization_id, source_id)
    roles = _roles(request.roles)
    entities = repository.list_entities(organization_id, source_id, roles=roles)
    excluded = _excluded_points(repository, organization_id, source_id, request.excluded, entities)
    floor_z = request.floor_z_m
    if floor_z is None:
        floor_z = record.params.get("floor_z_m")
    if floor_z is None:
        floor_z = record.summary.get("floor_z_m")
    top = [(point[0], point[1]) for point in request.top if len(point) >= 2]
    bottom = [(point[0], point[1]) for point in request.bottom or [] if len(point) >= 2] or None
    try:
        builder = make_builder()
        roof = build_roof(
            entities,
            top,
            bottom,
            roles=roles,
            excluded=request.excluded,
            floor_z=floor_z,
            crest_z=request.crest_z_m,
            builder=builder,
        )
    except SurfaceInputError as exc:
        raise CadImportError(str(exc)) from exc
    except SurfaceBuildError as exc:
        point = list(exc.point) if exc.point else None
        return CadSurfaceResponse(
            ok=False,
            builder="",
            issues=[CadContourIssueSchema(code="surface_build", message=exc.message, point=point)],
        )
    response = _response(roof)
    # Все исключённые — и те, что сейчас вне контура + 20 м: их можно вернуть.
    response.excluded_points = excluded
    return response


def _response(roof: Roof) -> CadSurfaceResponse:
    data = roof.data
    world = roof.world_vertices()
    return CadSurfaceResponse(
        ok=roof.ok,
        builder=roof.builder,
        plane=roof.plane,
        issues=[CadContourIssueSchema(**issue.to_dict()) for issue in roof.issues],
        warnings=[CadWarningSchema(**warning.to_dict()) for warning in roof.warnings],
        tin=CadTinSchema(vertices=world.tolist(), triangles=roof.triangles.tolist()),
        quality=CadSurfaceQualitySchema(
            spot_count=roof.spot_count,
            coverage_pct=roof.coverage_pct,
            max_gap_m=roof.max_gap_m,
            max_gap_point=list(roof.max_gap_point) if roof.max_gap_point else None,
            outlier_count=len(roof.outliers),
            conflict_count=len(data.conflicts),
            snapped_count=len(data.snapped),
            vertex_count=roof.vertex_count,
            triangle_count=roof.triangle_count,
            flat_fixed=roof.flat_fixed,
        ),
        outliers=[
            CadOutlierSchema(id=item.id, handle=_split_id(item.id)[0], point=list(item.point), deviation_m=item.deviation_m)
            for item in roof.outliers
        ],
        conflicts=[
            CadConflictSchema(
                kind=item.kind,
                point=list(item.point),
                values=[CadConflictValueSchema(role=value.role, handle=value.handle, z=value.z) for value in item.values],
                accepted_z=item.accepted_z,
            )
            for item in data.conflicts
        ],
        snapped=[
            CadSnappedSchema(id=item.id, point=list(item.point), from_z=item.from_z, to_z=item.to_z) for item in data.snapped
        ],
        thresholds=[
            CadThresholdSchema(segments=[[list(a), list(b)] for a, b in item.segments], excess_m=item.excess_m)
            for item in roof.thresholds
        ],
        bench=CadSurfaceBenchSchema(
            floor_z_m=roof.floor_z_m, mean_height_m=roof.mean_height_m, needs_confirmation=roof.needs_confirmation
        ),
        volume=CadSurfaceVolumeSchema(
            volume_m3=roof.volume_m3,
            basis=roof.volume_basis,
            area_top_m2=roof.area_top_m2,
            area_bottom_m2=roof.area_bottom_m2,
            area_mean_m2=roof.area_mean_m2,
            mean_area_volume_m3=roof.mean_area_volume_m3,
        ),
    )
