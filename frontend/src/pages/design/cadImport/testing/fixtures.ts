// Источник импорта для тестов: «Горизонт +410» с верхней и нижней бровкой,
// контур блока, точка отметки и подпись — как в ответе `/design/cad/sources`.
import type { CadContourResult, CadEntity, CadMeta, CadSource } from "../../../../types/cad";

export function cadEntity(handle: string, layer: string, extra: Partial<CadEntity> = {}): CadEntity {
  const points = extra.points ?? [
    [100, 200, 420],
    [130, 205, 421],
  ];
  return {
    handle,
    layer,
    kind: "POLYLINE3D",
    geometry_type: "line",
    points,
    closed: false,
    closed_by_gap: false,
    vertex_count: points.length,
    length_m: 30.4,
    area_m2: 0,
    z_kind: "variable",
    z_min: Math.min(...points.map((point) => point[2])),
    z_max: Math.max(...points.map((point) => point[2])),
    z_from_label: false,
    text: "",
    color: null,
    role: "situation",
    role_origin: "auto",
    role_override: false,
    ...extra,
  };
}

export const CAD_META: CadMeta = {
  roles: [
    { code: "block_contour", label: "Контур блока", applies_to: ["line"] },
    { code: "design_line", label: "Проектная линия", applies_to: ["line"] },
    { code: "crest_top", label: "Бровка верхняя", applies_to: ["line"] },
    { code: "crest_bottom", label: "Бровка нижняя", applies_to: ["line"] },
    { code: "feature_line", label: "Характерная линия", applies_to: ["line"] },
    { code: "contour_line", label: "Горизонталь", applies_to: ["line"] },
    { code: "spot_heights", label: "Отметки поверхности", applies_to: ["line", "point", "text"] },
    { code: "situation", label: "Ситуация", applies_to: ["line", "point", "text"] },
    { code: "ignore", label: "Не использовать", applies_to: ["line", "point", "text"] },
  ],
  layer_roles: [{ code: "crests_by_z", label: "Бровки (по Z)", applies_to: ["line"] }],
  origins: [
    { code: "template", label: "шаблон" },
    { code: "auto", label: "авто" },
    { code: "z", label: "по Z" },
    { code: "manual", label: "вручную" },
  ],
  defaults: { label_radius_m: 3, closure_tolerance_m: 0.5, bench_height_m: 10, max_file_mb: 40, max_files: 10, area_basis: "mean" },
  area_bases: [
    { code: "top", label: "S верх", description: "площадь контура по верхней бровке" },
    { code: "bottom", label: "S низ", description: "площадь контура по нижней бровке" },
    { code: "mean", label: "S ср", description: "(S верх + S низ) / 2 — способ горизонтальных сечений" },
  ],
};

export function cadSource(extra: Partial<CadSource> = {}): CadSource {
  const entities = [
    cadEntity("6C3", "Горизонт +410", { role: "crest_top", role_origin: "z", length_m: 134.3 }),
    cadEntity("733", "Горизонт +410", {
      role: "crest_bottom",
      role_origin: "z",
      length_m: 42.4,
      points: [
        [100, 180, 410],
        [130, 182, 411.7],
      ],
    }),
    cadEntity("769", "блок 66 вар 2", {
      kind: "LWPOLYLINE",
      role: "block_contour",
      closed: true,
      closed_by_gap: true,
      z_kind: "const",
      points: [
        [90, 170, 419.8],
        [140, 170, 419.8],
        [140, 215, 419.8],
      ],
    }),
    cadEntity("51C", "Отметка", {
      kind: "POINT",
      geometry_type: "point",
      role: "spot_heights",
      z_kind: "const",
      points: [[110, 190, 410.84]],
    }),
    cadEntity("61A", "Отметка", {
      kind: "TEXT",
      geometry_type: "text",
      role: "spot_heights",
      z_kind: "zero",
      text: "410.84",
      points: [[110.2, 190.3, 0]],
    }),
  ];
  return {
    id: "src-1",
    file_name: "блок 66.dwg",
    format: "dwg",
    site_code: "SITE_ZK",
    work_object_name: "Жуков камень",
    uploaded_at: "2026-09-30T10:00:00+00:00",
    uploaded_by: "engineer@example.ru",
    survey_date: null,
    params: { scale: 1, label_radius_m: 3, floor_z_m: null, bench_height_m: 10 },
    insunits: 4,
    suggested_scale: null,
    extent: [90, 170, 140, 215],
    floor_z_m: 410,
    template_saved: true,
    area_basis: "mean",
    warnings: [
      { code: "units_declared", message: "В файле указаны единицы «миллиметры», но размеры похожи на метры — читаем в метрах.", level: "info" },
    ],
    layers: [
      {
        name: "блок 66 вар 2",
        role: "block_contour",
        origin: "auto",
        entity_count: 1,
        kinds: { LWPOLYLINE: 1 },
        z_min: 419.8,
        z_max: 419.8,
        color: null,
        counts_by_role: { block_contour: 1 },
      },
      {
        name: "Горизонт +410",
        role: "crests_by_z",
        origin: "auto",
        entity_count: 2,
        kinds: { POLYLINE3D: 2 },
        z_min: 410,
        z_max: 421,
        color: null,
        counts_by_role: { crest_bottom: 1, crest_top: 1 },
      },
      {
        name: "Отметка",
        role: "spot_heights",
        origin: "auto",
        entity_count: 2,
        kinds: { POINT: 1, TEXT: 1 },
        z_min: 410.84,
        z_max: 410.84,
        color: null,
        counts_by_role: { spot_heights: 2 },
      },
    ],
    entities,
    ...extra,
  };
}

/** Ответ предпросмотра контура блока 66 — как у `/design/cad/sources/{id}/contour`. */
export function contourResult(extra: Partial<CadContourResult> = {}): CadContourResult {
  return {
    ok: true,
    method: "ready",
    issues: [],
    warnings: [],
    top: { points: [[90, 170], [140, 170], [140, 215]], area_m2: 2789.93, perimeter_m: 341.08 },
    bottom: { points: [[90, 170], [145, 170], [145, 215]], area_m2: 4120.92, perimeter_m: 360 },
    mean_area_m2: 3455.42,
    free_faces: [[1, 2]],
    flanks: [
      { start: [140, 170], end: [145, 170], length_m: 5.29 },
      { start: [140, 215], end: [145, 215], length_m: 16.92 },
    ],
    closings: [],
    items: [{ kind: "part", handle: "769", start_m: 0, end_m: 341.08, points: [], flip: false, label: "" }],
    item_info: [{ kind: "part", handle: "769", layer: "блок 66 вар 2", length_m: 341.08, reversed: false, gap_to_next_m: 0, link: "joined" }],
    bench: { crest_z_m: 420.3, toe_z_m: 410, height_m: 10.3, crest_source: "crest_top", toe_source: "floor" },
    crest_line: null,
    ...extra,
  };
}
