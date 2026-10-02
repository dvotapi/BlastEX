"""Схемы API импорта чертежа маркшейдера (TASK-013)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from design.spatial.cad.contour import MAX_CONTOUR_SEGMENTS


class CadWarningSchema(BaseModel):
    code: str
    message: str
    level: str = "warning"


class CadRoleSchema(BaseModel):
    code: str
    label: str
    applies_to: list[str] = Field(default_factory=list)


class CadOriginSchema(BaseModel):
    code: str
    label: str


class CadDefaultsSchema(BaseModel):
    label_radius_m: float
    closure_tolerance_m: float
    bench_height_m: float
    max_file_mb: int
    max_files: int
    area_basis: str = "mean"


class CadAreaBasisInfoSchema(BaseModel):
    """Какая площадь считается площадью блока: S верх, S низ или S ср."""

    code: str
    label: str
    description: str


class CadSituationKindSchema(BaseModel):
    """Вид объекта ситуации: контур карьера, дорога, ЛЭП, склад, здание, прочее."""

    code: str
    label: str


class CadMetaResponse(BaseModel):
    roles: list[CadRoleSchema]
    layer_roles: list[CadRoleSchema]
    origins: list[CadOriginSchema]
    defaults: CadDefaultsSchema
    area_bases: list[CadAreaBasisInfoSchema] = Field(default_factory=list)
    situation_kinds: list[CadSituationKindSchema] = Field(default_factory=list)


class CadCrsSchema(BaseModel):
    """Система координат объекта: местная без EPSG — полноценный вариант (§2)."""

    name: str = Field(default="", max_length=120)
    height_system: str = Field(default="", max_length=120)
    epsg: int | None = Field(default=None, gt=0)


class CadSeriesVersionSchema(BaseModel):
    """Другая версия той же серии ситуации (то же название на объекте)."""

    id: str
    title: str
    file_name: str
    survey_date: str | None = None
    uploaded_at: str


class CadParamsSchema(BaseModel):
    """Параметры разбора: масштаб координат, радиус подписей, подошва для бровок."""

    scale: float = Field(default=1.0, gt=0, le=1000)
    label_radius_m: float = Field(default=3.0, ge=0, le=50)
    floor_z_m: float | None = None
    bench_height_m: float = Field(default=10.0, gt=0, le=100)


class CadEntitySchema(BaseModel):
    handle: str
    layer: str
    kind: str
    geometry_type: str
    points: list[list[float]]
    closed: bool = False
    closed_by_gap: bool = False
    vertex_count: int
    length_m: float
    area_m2: float
    z_kind: str
    z_min: float
    z_max: float
    z_from_label: bool = False
    text: str = ""
    color: str | None = None
    role: str
    role_origin: str
    # Роль задана этому объекту явно (а не унаследована от слоя).
    role_override: bool = False


class CadLayerSchema(BaseModel):
    name: str
    role: str
    origin: str
    entity_count: int
    kinds: dict[str, int] = Field(default_factory=dict)
    z_min: float | None = None
    z_max: float | None = None
    color: str | None = None
    counts_by_role: dict[str, int] = Field(default_factory=dict)
    # Вид объектов ситуации слоя (есть только у слоёв с объектами ситуации).
    situation_kind: str | None = None
    situation_kind_origin: str | None = None


class CadSourceSchema(BaseModel):
    id: str
    file_name: str
    # Название источника: источники объекта с одинаковым названием — версии серии.
    title: str = ""
    format: str
    site_code: str = ""
    work_object_name: str = ""
    uploaded_at: str
    uploaded_by: str = ""
    survey_date: str | None = None
    params: CadParamsSchema
    insunits: int | None = None
    suggested_scale: float | None = None
    extent: list[float] | None = None
    floor_z_m: float | None = None
    template_saved: bool = False
    # Площадь блока по соглашению маркшейдера объекта (по умолчанию S ср).
    area_basis: str = "mean"
    # СК объекта (None — не задана) и другие версии той же серии ситуации.
    crs: CadCrsSchema | None = None
    series: list[CadSeriesVersionSchema] = Field(default_factory=list)
    warnings: list[CadWarningSchema] = Field(default_factory=list)
    layers: list[CadLayerSchema] = Field(default_factory=list)
    entities: list[CadEntitySchema] = Field(default_factory=list)


class CadImportResponse(BaseModel):
    sources: list[CadSourceSchema]


class CadRolesRequest(BaseModel):
    """Ручные роли: слою — роль, сущности — роль или null (вернуть роль слоя).

    `kinds` — вид объектов ситуации слоя; null — вид по имени слоя.
    """

    layers: dict[str, str] = Field(default_factory=dict)
    entities: dict[str, str | None] = Field(default_factory=dict)
    kinds: dict[str, str | None] = Field(default_factory=dict)


class CadSourceMetaRequest(BaseModel):
    """Название и дата съёмки источника; поле, которого нет в запросе, не меняется."""

    title: str | None = Field(default=None, max_length=300)
    survey_date: str | None = None


class CadSourceMetaResponse(BaseModel):
    id: str
    title: str
    survey_date: str | None = None
    series: list[CadSeriesVersionSchema] = Field(default_factory=list)


class CadCrsResponse(BaseModel):
    crs: CadCrsSchema | None = None
    # Без объекта работ СК хранить негде.
    saved: bool
    warnings: list[CadWarningSchema] = Field(default_factory=list)


class CadRolesResponse(BaseModel):
    """Ответ на правку ролей — без геометрии: слои и только изменившиеся роли.

    На чертеже с десятками тысяч объектов полный источник весит десятки
    мегабайт, а смена роли в списке случается часто.
    """

    id: str
    template_saved: bool = False
    floor_z_m: float | None = None
    warnings: list[CadWarningSchema] = Field(default_factory=list)
    layers: list[CadLayerSchema] = Field(default_factory=list)
    roles: dict[str, list[str]] = Field(default_factory=dict)
    # Все объекты с явной ролью после правки — чтобы фронт знал, где «По слою».
    overrides: list[str] = Field(default_factory=list)


# --- контур блока (PR 2) --------------------------------------------------

DEFAULT_CONTOUR_ROLES = ["block_contour", "design_line", "crest_top"]


class CadContourLinesRequest(BaseModel):
    """Роли линий, из которых собирается контур (щелчок внутри, сборка)."""

    roles: list[str] = Field(default_factory=lambda: list(DEFAULT_CONTOUR_ROLES))


class CadStitchPartSchema(BaseModel):
    handle: str
    reversed: bool
    length_m: float
    chain_start_m: float


class CadStitchedLineSchema(BaseModel):
    points: list[list[float]]
    parts: list[CadStitchPartSchema]
    length_m: float


class CadGapSchema(BaseModel):
    role: str
    a: list[float]
    b: list[float]
    distance_m: float
    # `gap` — разрыв больше 1 м, `turn` — стык с изломом больше 60°.
    reason: str


class CadContourLinesResponse(BaseModel):
    # Места разреза линий выбранных ролей в пересечениях: handle → расстояния по линии.
    splits: dict[str, list[float]] = Field(default_factory=dict)
    intersections: list[list[float]] = Field(default_factory=list)
    crests_top: list[CadStitchedLineSchema] = Field(default_factory=list)
    crests_bottom: list[CadStitchedLineSchema] = Field(default_factory=list)
    gaps: list[CadGapSchema] = Field(default_factory=list)
    # Разрезы не посчитаны (слишком много линий выбранных ролей): щелчок внутри
    # и сборка без них не работают, а бровки для «блока по бровке» — есть.
    splits_error: str = ""


class CadContourItemSchema(BaseModel):
    """Участок контура: кусок линии чертежа, прямой отрезок или построенная линия."""

    kind: Literal["part", "segment", "polyline"]
    handle: str = ""
    start_m: float = 0.0
    end_m: float = 0.0
    points: list[list[float]] = Field(default_factory=list)
    flip: bool = False
    label: str = ""


class CadCrestBlockSchema(BaseModel):
    start: list[float] = Field(min_length=2, max_length=3)
    end: list[float] = Field(min_length=2, max_length=3)
    width_m: float = Field(gt=0, le=500)
    side: Literal["auto", "left", "right"] = "auto"


class CadPassportBenchSchema(BaseModel):
    """Отметки уступа паспорта: остаются, если в чертеже их нет, и проверяются вместе с найденными."""

    crest_z_m: float
    toe_z_m: float


class CadContourRequest(BaseModel):
    method: Literal["ready", "click", "assembly", "crest"]
    handle: str = ""
    point: list[float] | None = Field(default=None, min_length=2, max_length=3)
    roles: list[str] = Field(default_factory=lambda: list(DEFAULT_CONTOUR_ROLES))
    # Сколько участков может дать сам предпросмотр (граница «Щелчка внутри»):
    # «Править как сборку» отправляет их обратно.
    items: list[CadContourItemSchema] = Field(default_factory=list, max_length=MAX_CONTOUR_SEGMENTS)
    crest: CadCrestBlockSchema | None = None
    tolerance_m: float = Field(default=0.5, gt=0, le=10)
    bridge_m: float = Field(default=5.0, ge=0, le=50)
    passport_bench: CadPassportBenchSchema | None = None


class CadContourIssueSchema(BaseModel):
    code: str
    message: str
    point: list[float] | None = None


class CadRingSchema(BaseModel):
    points: list[list[float]]
    area_m2: float
    perimeter_m: float


class CadFlankSchema(BaseModel):
    start: list[float]
    end: list[float] | None = None
    length_m: float | None = None


class CadItemInfoSchema(BaseModel):
    kind: str
    handle: str = ""
    layer: str = ""
    length_m: float
    reversed: bool
    gap_to_next_m: float
    # `joined` — концы сведены, `closing` — замыкающий отрезок до следующего.
    link: str


class CadBenchSchema(BaseModel):
    crest_z_m: float | None = None
    toe_z_m: float | None = None
    height_m: float | None = None
    crest_source: str = ""
    toe_source: str = ""


class CadContourResponse(BaseModel):
    ok: bool
    method: str
    issues: list[CadContourIssueSchema] = Field(default_factory=list)
    warnings: list[CadWarningSchema] = Field(default_factory=list)
    top: CadRingSchema | None = None
    bottom: CadRingSchema | None = None
    mean_area_m2: float | None = None
    free_faces: list[list[int]] = Field(default_factory=list)
    flanks: list[CadFlankSchema] = Field(default_factory=list)
    closings: list[list[list[float]]] = Field(default_factory=list)
    items: list[CadContourItemSchema] = Field(default_factory=list)
    item_info: list[CadItemInfoSchema] = Field(default_factory=list)
    bench: CadBenchSchema = Field(default_factory=CadBenchSchema)
    # Блок по бровке: выбранный участок верхней бровки.
    crest_line: list[list[float]] | None = None


class CadAreaBasisRequest(BaseModel):
    area_basis: Literal["top", "bottom", "mean"]


class CadAreaBasisResponse(BaseModel):
    area_basis: str
    # Сохранено на объекте работ; без объекта выбор действует только в окне.
    saved: bool


# --- кровля блока (PR 3) ----------------------------------------------------

DEFAULT_SURFACE_ROLES = ["crest_top", "crest_bottom", "feature_line", "contour_line", "spot_heights"]
# Точек контура из окна — не больше, чем может дать сам предпросмотр контура.
MAX_RING_POINTS = MAX_CONTOUR_SEGMENTS
MAX_EXCLUDED_POINTS = 50_000


class CadSurfaceRequest(BaseModel):
    """Предпросмотр кровли: контур по верхней и нижней бровке, роли в поверхности,
    исключённые отметки, подошва и отметка бровки (для части вне кровли)."""

    top: list[list[float]] = Field(min_length=3, max_length=MAX_RING_POINTS)
    bottom: list[list[float]] | None = Field(default=None, max_length=MAX_RING_POINTS)
    roles: list[str] = Field(default_factory=lambda: list(DEFAULT_SURFACE_ROLES))
    excluded: list[str] = Field(default_factory=list, max_length=MAX_EXCLUDED_POINTS)
    floor_z_m: float | None = None
    crest_z_m: float | None = None


class CadTinSchema(BaseModel):
    vertices: list[list[float]] = Field(default_factory=list)
    triangles: list[list[int]] = Field(default_factory=list)


class CadSurfaceQualitySchema(BaseModel):
    spot_count: int = 0
    coverage_pct: float = 0.0
    # Наибольшее расстояние от точки контура до ближайшей отметки и где оно.
    max_gap_m: float | None = None
    max_gap_point: list[float] | None = None
    outlier_count: int = 0
    conflict_count: int = 0
    snapped_count: int = 0
    vertex_count: int = 0
    triangle_count: int = 0
    # Сколько плоских треугольников горизонталей получили точку в центре.
    flat_fixed: int = 0


class CadOutlierSchema(BaseModel):
    id: str
    handle: str
    point: list[float]
    deviation_m: float


class CadExcludedPointSchema(BaseModel):
    id: str
    point: list[float]


class CadConflictValueSchema(BaseModel):
    role: str
    handle: str
    z: float


class CadConflictSchema(BaseModel):
    # `crossing` — пересечение ограничителей, `duplicate` — дубль отметки.
    kind: str
    point: list[float]
    values: list[CadConflictValueSchema]
    accepted_z: float


class CadSnappedSchema(BaseModel):
    id: str
    point: list[float]
    from_z: float
    to_z: float


class CadThresholdSchema(BaseModel):
    segments: list[list[list[float]]]
    excess_m: float


class CadSurfaceBenchSchema(BaseModel):
    floor_z_m: float | None = None
    mean_height_m: float | None = None
    # Высота вне 2–25 м: блок строится только после подтверждения.
    needs_confirmation: bool = False


class CadSurfaceVolumeSchema(BaseModel):
    volume_m3: float | None = None
    # Как посчитан объём: `bottom` — в контуре по нижней бровке, `top` — по
    # верхней, `mean` — S ср × H (кровля-плоскость не описывает откос).
    basis: str = "top"
    area_top_m2: float = 0.0
    area_bottom_m2: float = 0.0
    area_mean_m2: float = 0.0
    mean_area_volume_m3: float | None = None


class CadSurfaceResponse(BaseModel):
    ok: bool
    builder: str
    plane: bool = False
    issues: list[CadContourIssueSchema] = Field(default_factory=list)
    warnings: list[CadWarningSchema] = Field(default_factory=list)
    tin: CadTinSchema = Field(default_factory=CadTinSchema)
    quality: CadSurfaceQualitySchema = Field(default_factory=CadSurfaceQualitySchema)
    outliers: list[CadOutlierSchema] = Field(default_factory=list)
    excluded_points: list[CadExcludedPointSchema] = Field(default_factory=list)
    conflicts: list[CadConflictSchema] = Field(default_factory=list)
    snapped: list[CadSnappedSchema] = Field(default_factory=list)
    thresholds: list[CadThresholdSchema] = Field(default_factory=list)
    bench: CadSurfaceBenchSchema = Field(default_factory=CadSurfaceBenchSchema)
    volume: CadSurfaceVolumeSchema = Field(default_factory=CadSurfaceVolumeSchema)


# --- ситуация карьера (PR 4) ------------------------------------------------

MAX_SITUATION_REFERENCES = 50


class CadSituationVersionSchema(BaseModel):
    """Версия серии ситуации — один загруженный файл."""

    source_id: str
    title: str
    file_name: str
    survey_date: str | None = None
    uploaded_at: str
    situation_count: int
    # Номер правки источника: кэш геометрии на клиенте сбрасывается по нему.
    revision: int


class CadSituationSeriesSchema(BaseModel):
    key: str
    title: str
    versions: list[CadSituationVersionSchema]
    # Версия из ссылки паспорта, иначе самая свежая.
    default_source_id: str


class CadSituationCatalogueResponse(BaseModel):
    site_code: str = ""
    crs: CadCrsSchema | None = None
    series: list[CadSituationSeriesSchema] = Field(default_factory=list)
    # Ссылки паспорта, которых больше нет (удалены или чужие).
    missing: list[str] = Field(default_factory=list)
    truncated: bool = False


class CadSituationLineSchema(BaseModel):
    points: list[list[float]]
    closed: bool = False


class CadSituationLayerSchema(BaseModel):
    name: str
    kind: str
    color: str | None = None
    lines: list[CadSituationLineSchema] = Field(default_factory=list)
    points: list[list[float]] = Field(default_factory=list)
    vertex_count: int = 0
    # Слой не уместился в предел ответа — геометрии нет, только имя.
    omitted: bool = False


class CadSituationGeometryResponse(BaseModel):
    source_id: str
    revision: int
    title: str
    survey_date: str | None = None
    layers: list[CadSituationLayerSchema] = Field(default_factory=list)
    warnings: list[CadWarningSchema] = Field(default_factory=list)


class CadSiteSourceSchema(BaseModel):
    """Строка списка «Чертежи объекта»."""

    id: str
    title: str
    file_name: str
    survey_date: str | None = None
    uploaded_at: str
    uploaded_by: str = ""
    situation_count: int = 0


class CadSiteSourcesResponse(BaseModel):
    site_code: str = ""
    sources: list[CadSiteSourceSchema] = Field(default_factory=list)
    truncated: bool = False
