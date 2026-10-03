"""Ситуация карьера на объекте (TASK-013, PR 4).

Ситуация — сущности роли «Ситуация» в источниках объекта работ. Источники с
одинаковым названием — версии одной серии («Положение горных работ» на 01.09
и на 01.10). Паспорт без ссылки показывает самую свежую версию каждой серии;
«Построить блок» запоминает в паспорте показанные версии
(`contour.cad.situation`), и паспорт показывает их и дальше.

Каталог отдаёт серии и версии без геометрии, геометрия — по одному
источнику: страница кэширует её по номеру правки источника.
"""
from __future__ import annotations

from collections import Counter

import numpy as np
import shapely

from api.schemas.cad import (
    CadCrsSchema,
    CadSiteSourceSchema,
    CadSiteSourcesResponse,
    CadSituationCatalogueResponse,
    CadSituationGeometryResponse,
    CadSituationLayerSchema,
    CadSituationLineSchema,
    CadSituationSeriesSchema,
    CadSituationVersionSchema,
    CadWarningSchema,
)
from api.services.cad_service import MAX_SITE_SOURCES, crs_named, layer_kinds, source_title
from design.spatial.cad.model import ROLE_SITUATION, SITUATION_KIND_OTHER, SITUATION_KINDS, CadEntity, ru_number
from design.spatial.cad.repository import CadRepository, CadSourceNotFound, CadSourceRecord
from design.spatial.cad.roles import layer_key
from design.spatial.cad.situation import order_versions, series_key

# Упрощение линий к показу — как допуск спрямления кривых при чтении.
SITUATION_SIMPLIFY_M = 0.05
# Предел вершин в ответе геометрии одного источника.
MAX_SITUATION_VERTICES = 200_000
# Сколько версий серии отдаёт каталог (свежие); версия из ссылки паспорта — всегда.
MAX_VERSIONS_PER_SERIES = 12
# Сколько источников с ситуацией просматривает каталог: граница запроса, а не версий.
MAX_SCANNED_SOURCES = 2000
KIND_LABELS = dict(SITUATION_KINDS)


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _version(record: CadSourceRecord, count: int) -> CadSituationVersionSchema:
    return CadSituationVersionSchema(
        source_id=record.id,
        title=source_title(record),
        file_name=record.file_name,
        survey_date=_iso(record.survey_date),
        uploaded_at=record.uploaded_at.isoformat(),
        situation_count=count,
        revision=record.revision,
    )


def catalogue(
    repository: CadRepository, organization_id: str, active_site_code: str, source_ids: list[str]
) -> CadSituationCatalogueResponse:
    """Серии ситуации объекта паспорта.

    Объект — по источникам ссылки паспорта (паспорт мог быть построен на
    другом объекте), иначе активный. Ссылка на удалённый или чужой источник
    попадает в `missing`, остальное отдаётся как обычно. Предел — версии на
    серию, а не файлы объекта: файлов блоков без ситуации сотни, и редкая
    серия (ЛЭП, контур карьера) не должна из-за них пропадать.
    """

    referenced: dict[str, CadSourceRecord] = {}
    missing: list[str] = []
    for source_id in dict.fromkeys(source_ids):
        record = repository.get_source(organization_id, source_id)
        if record is None:
            missing.append(source_id)
        else:
            referenced[source_id] = record
    site_code = next((item.site_code for item in referenced.values() if item.site_code), active_site_code)

    scanned = (
        repository.list_situation_sources(organization_id, site_code, limit=MAX_SCANNED_SOURCES + 1) if site_code else []
    )
    over_limit = len(scanned) > MAX_SCANNED_SOURCES
    scanned = scanned[:MAX_SCANNED_SOURCES]
    counts = {record.id: count for record, count in scanned}
    candidates = {record.id: record for record, _ in scanned}
    # Источник ссылки старше просмотренных или без объекта (файл загружен без
    # активного объекта) — всё равно в своём паспорте.
    extra = {source_id: record for source_id, record in referenced.items() if source_id not in candidates}
    counts.update(repository.count_entities_by_role(organization_id, set(extra), ROLE_SITUATION))
    candidates.update(extra)

    grouped: dict[str, list[CadSourceRecord]] = {}
    for record in candidates.values():
        if counts.get(record.id):
            grouped.setdefault(series_key(source_title(record)), []).append(record)

    truncated = over_limit
    series: list[CadSituationSeriesSchema] = []
    for key, records in grouped.items():
        ordered = order_versions(records)
        kept = [item for index, item in enumerate(ordered) if index < MAX_VERSIONS_PER_SERIES or item.id in referenced]
        truncated = truncated or len(kept) < len(ordered)
        pinned = next((item for item in kept if item.id in referenced), None)
        series.append(
            CadSituationSeriesSchema(
                key=key,
                title=source_title(ordered[0]),
                versions=[_version(item, counts[item.id]) for item in kept],
                default_source_id=(pinned or ordered[0]).id,
            )
        )
    series.sort(key=lambda item: item.key)

    crs = repository.get_site_crs(organization_id, site_code) if site_code else None
    return CadSituationCatalogueResponse(
        site_code=site_code,
        crs=CadCrsSchema(**crs) if crs_named(crs) else None,
        series=series,
        missing=missing,
        truncated=truncated,
    )


def _simplified(points: list[tuple[float, float, float]], closed: bool, origin: np.ndarray) -> list[list[float]]:
    """Линия без лишних вершин (отклонение ≤ 0,05 м) в мировых координатах.

    Упрощение идёт в локальной системе — как вся геометрия чертежа (PR 2).
    """

    coords = np.asarray(points, dtype=float) - origin
    if closed and len(coords) > 2 and not np.allclose(coords[0], coords[-1]):
        coords = np.vstack([coords, coords[:1]])
    if len(coords) < 3:
        kept = coords
    else:
        kept = shapely.get_coordinates(
            shapely.simplify(shapely.linestrings(coords), SITUATION_SIMPLIFY_M, preserve_topology=False),
            include_z=True,
        )
        if closed and len(kept) < 4:
            # Кольцо меньше допуска (опора, колодец) сжалось бы в точку или
            # отрезок туда-обратно — оставляем его вершины как есть.
            kept = coords
        elif len(kept) < 2:
            kept = coords[[0, -1]]
    if closed and len(kept) > 2 and np.allclose(kept[0], kept[-1]):
        kept = kept[:-1]
    return (kept + origin).round(4).tolist()


def _layer_color(members: list[CadEntity], fallback: str | None) -> str | None:
    colors = Counter(item.color for item in members if item.color)
    return colors.most_common(1)[0][0] if colors else fallback


def source_situation(repository: CadRepository, organization_id: str, source_id: str) -> CadSituationGeometryResponse:
    """Геометрия ситуации источника по слоям: линии (упрощённые) и точки.

    Подписи не отдаются — холст их не рисует. Слой, который не помещается в
    предел вершин, отдаётся без геометрии (`omitted`) с заметкой.
    """

    record = repository.get_source(organization_id, source_id)
    if record is None:
        raise CadSourceNotFound(source_id)
    entities = repository.list_entities(organization_id, source_id, roles={ROLE_SITUATION})
    summary = record.summary or {}
    kinds = layer_kinds(summary, entities)
    layer_colors = summary.get("layer_colors") or {}

    by_layer: dict[str, list[CadEntity]] = {}
    for item in entities:
        if item.geometry_type != "text":
            by_layer.setdefault(item.layer, []).append(item)
    origin = np.asarray(next((item.points[0] for item in entities if item.points), (0.0, 0.0, 0.0)), dtype=float)

    layers: list[CadSituationLayerSchema] = []
    budget = MAX_SITUATION_VERTICES
    omitted = 0
    for name in sorted(by_layer, key=layer_key):
        members = by_layer[name]
        lines = [
            CadSituationLineSchema(points=_simplified(item.points, item.closed, origin), closed=item.closed)
            for item in members
            if item.geometry_type == "line" and len(item.points) >= 2
        ]
        points = [list(item.points[0]) for item in members if item.geometry_type == "point" and item.points]
        count = sum(len(line.points) for line in lines) + len(points)
        kind = (kinds.get(name) or {}).get("kind") or SITUATION_KIND_OTHER
        layer = CadSituationLayerSchema(
            name=name,
            kind=kind,
            kind_label=KIND_LABELS.get(kind, ""),
            color=_layer_color(members, layer_colors.get(name)),
            vertex_count=count,
        )
        if count > budget:
            layer.omitted = True
            omitted += 1
        else:
            layer.lines, layer.points = lines, points
            budget -= count
        layers.append(layer)

    warnings: list[CadWarningSchema] = []
    if omitted:
        warnings.append(
            CadWarningSchema(
                code="situation_capped",
                message=(
                    f"Ситуация больше {ru_number(MAX_SITUATION_VERTICES, 0)} вершин: "
                    f"слоёв без геометрии — {omitted}. Оставьте в файле ситуации ближайшие к блокам слои."
                ),
            )
        )
    return CadSituationGeometryResponse(
        source_id=record.id,
        revision=record.revision,
        title=source_title(record),
        survey_date=_iso(record.survey_date),
        layers=layers,
        warnings=warnings,
    )


def list_sources(repository: CadRepository, organization_id: str, site_code: str) -> CadSiteSourcesResponse:
    """«Чертежи объекта»: загруженные файлы активного объекта, новые первыми."""

    if not site_code:
        return CadSiteSourcesResponse()
    # На один больше предела: ровно 50 файлов — ещё не «показаны не все».
    records = repository.list_site_sources(organization_id, site_code, limit=MAX_SITE_SOURCES + 1)
    counts = repository.count_entities_by_role(organization_id, {item.id for item in records}, ROLE_SITUATION)
    return CadSiteSourcesResponse(
        site_code=site_code,
        sources=[
            CadSiteSourceSchema(
                id=item.id,
                title=source_title(item),
                file_name=item.file_name,
                survey_date=_iso(item.survey_date),
                uploaded_at=item.uploaded_at.isoformat(),
                uploaded_by=item.uploaded_by,
                situation_count=counts.get(item.id, 0),
            )
            for item in records[:MAX_SITE_SOURCES]
        ],
        truncated=len(records) > MAX_SITE_SOURCES,
    )


def delete_source(repository: CadRepository, organization_id: str, source_id: str) -> None:
    """Удаление насовсем: источник и его сущности (решение владельца 03.10.2026)."""

    repository.delete_source(organization_id, source_id)
