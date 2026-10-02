// Импорт чертежа маркшейдера (TASK-013): схемы `api/schemas/cad.py`.
import type { CadContourItem } from "./design";

export type CadRoleCode =
  | "block_contour"
  | "design_line"
  | "crest_top"
  | "crest_bottom"
  | "feature_line"
  | "contour_line"
  | "spot_heights"
  | "situation"
  | "ignore";

/** Роль слоя: любая роль сущности или «Бровки (по Z)» — деление по отметкам. */
export type CadLayerRoleCode = CadRoleCode | "crests_by_z";

export type CadOrigin = "template" | "auto" | "z" | "manual";

export type CadWarning = { code: string; message: string; level: "info" | "warning" };

export type CadRoleInfo = { code: CadLayerRoleCode; label: string; applies_to: string[] };

/** Какая площадь — площадь блока: S верх, S низ или S ср (соглашение маркшейдера объекта). */
export type CadAreaBasis = "top" | "bottom" | "mean";

export type CadMeta = {
  roles: CadRoleInfo[];
  layer_roles: CadRoleInfo[];
  origins: Array<{ code: CadOrigin; label: string }>;
  defaults: {
    label_radius_m: number;
    closure_tolerance_m: number;
    bench_height_m: number;
    max_file_mb: number;
    max_files: number;
    area_basis: CadAreaBasis;
  };
  area_bases: Array<{ code: CadAreaBasis; label: string; description: string }>;
};

export type CadParams = {
  scale: number;
  label_radius_m: number;
  floor_z_m: number | null;
  bench_height_m: number;
};

export type CadPoint = [number, number, number];

export type CadEntity = {
  handle: string;
  layer: string;
  kind: string;
  geometry_type: "line" | "point" | "text";
  points: CadPoint[];
  closed: boolean;
  closed_by_gap: boolean;
  vertex_count: number;
  length_m: number;
  area_m2: number;
  z_kind: "const" | "variable" | "zero";
  z_min: number;
  z_max: number;
  z_from_label: boolean;
  text: string;
  color: string | null;
  role: CadRoleCode;
  role_origin: CadOrigin;
  /** Роль задана этому объекту явно, а не унаследована от слоя. */
  role_override: boolean;
};

export type CadLayer = {
  name: string;
  role: CadLayerRoleCode;
  origin: CadOrigin;
  entity_count: number;
  kinds: Record<string, number>;
  z_min: number | null;
  z_max: number | null;
  color: string | null;
  counts_by_role: Partial<Record<CadRoleCode, number>>;
};

export type CadSource = {
  id: string;
  file_name: string;
  format: "dxf" | "dwg";
  site_code: string;
  work_object_name: string;
  uploaded_at: string;
  uploaded_by: string;
  survey_date: string | null;
  params: CadParams;
  insunits: number | null;
  suggested_scale: number | null;
  extent: [number, number, number, number] | null;
  floor_z_m: number | null;
  template_saved: boolean;
  /** Площадь блока по соглашению маркшейдера объекта (по умолчанию S ср). */
  area_basis: CadAreaBasis;
  warnings: CadWarning[];
  layers: CadLayer[];
  entities: CadEntity[];
};

export type CadImportResponse = { sources: CadSource[] };

/** Объекта работ здесь нет: его берёт сервер — активный объект организации. */
export type CadUploadParams = {
  benchHeightM?: number;
  scale?: number;
  labelRadiusM?: number;
  floorZM?: number | null;
  surveyDate?: string;
};

/** Ручные роли: слою — роль, сущности — роль или null (вернуть роль слоя). */
export type CadRolesPayload = {
  layers?: Record<string, CadLayerRoleCode>;
  entities?: Record<string, CadRoleCode | null>;
};

/** Ответ на правку ролей: без геометрии — слои и только изменившиеся роли объектов. */
export type CadRolesResponse = {
  id: string;
  template_saved: boolean;
  floor_z_m: number | null;
  warnings: CadWarning[];
  layers: CadLayer[];
  roles: Record<string, [CadRoleCode, CadOrigin]>;
  /** Все объекты с явной ролью после правки. */
  overrides: string[];
};

// --- контур блока (PR 2): `/design/cad/sources/{id}/contour` ---

export type CadStitchPart = { handle: string; reversed: boolean; length_m: number; chain_start_m: number };

/** Бровка, сшитая из фрагментов: точки и из каких объектов она состоит. */
export type CadStitchedLine = { points: CadPoint[]; parts: CadStitchPart[]; length_m: number };

/** Несшитый стык бровки: `gap` — разрыв больше 1 м, `turn` — излом больше 60°. */
export type CadGap = { role: string; a: number[]; b: number[]; distance_m: number; reason: "gap" | "turn" };

export type CadContourLines = {
  /** Места разреза линий в пересечениях: handle → расстояния по линии. */
  splits: Record<string, number[]>;
  intersections: number[][];
  crests_top: CadStitchedLine[];
  crests_bottom: CadStitchedLine[];
  gaps: CadGap[];
  /** Разрезы не посчитаны (слишком много линий): «Щелчок внутри» и «Сборка» без них не работают. */
  splits_error: string;
};

export type CadContourMethod = "ready" | "click" | "assembly" | "crest";

export type CadCrestSide = "auto" | "left" | "right";

export type CadContourRequest = {
  method: CadContourMethod;
  handle?: string;
  point?: number[] | null;
  roles?: CadRoleCode[];
  items?: CadContourItem[];
  crest?: { start: number[]; end: number[]; width_m: number; side: CadCrestSide } | null;
  tolerance_m?: number;
  bridge_m?: number;
  /** Отметки уступа паспорта: остаются, если в чертеже их нет, и проверяются вместе с найденными. */
  passport_bench?: CadPassportBench;
};

export type CadPassportBench = { crest_z_m: number; toe_z_m: number };

export type CadContourIssue = { code: string; message: string; point: number[] | null };

export type CadRing = { points: number[][]; area_m2: number; perimeter_m: number };

export type CadFlank = { start: number[]; end: number[] | null; length_m: number | null };

export type CadItemInfo = {
  kind: CadContourItem["kind"];
  handle: string;
  layer: string;
  length_m: number;
  reversed: boolean;
  gap_to_next_m: number;
  /** `joined` — концы сведены, `closing` — замыкающий отрезок до следующего участка. */
  link: "joined" | "closing";
};

export type CadBench = {
  crest_z_m: number | null;
  toe_z_m: number | null;
  height_m: number | null;
  crest_source: string;
  toe_source: string;
};

export type CadContourResult = {
  ok: boolean;
  method: CadContourMethod;
  issues: CadContourIssue[];
  warnings: CadWarning[];
  top: CadRing | null;
  bottom: CadRing | null;
  mean_area_m2: number | null;
  free_faces: number[][];
  flanks: CadFlank[];
  closings: number[][][];
  items: CadContourItem[];
  item_info: CadItemInfo[];
  bench: CadBench;
  crest_line: number[][] | null;
};

export type CadAreaBasisResponse = { area_basis: CadAreaBasis; saved: boolean };
