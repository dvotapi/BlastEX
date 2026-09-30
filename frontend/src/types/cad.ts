// Импорт чертежа маркшейдера (TASK-013): схемы `api/schemas/cad.py`.

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
  };
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
  warnings: CadWarning[];
  layers: CadLayer[];
  entities: CadEntity[];
};

export type CadImportResponse = { sources: CadSource[] };

export type CadUploadParams = {
  workObjectName: string;
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
