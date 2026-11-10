// Паспорт на бурение (TASK-015): типы ответов `/design/drilling-passports`.
// Поля payload — `api/schemas/drilling_passport.py::DrillingPassportPayload`.

export type DrillSigner = { position: string; organization: string; name: string };
export type DrillPerson = { name: string; position: string };

export type DrillPassportPayload = {
  agreed_by: DrillSigner;
  approved_by: DrillSigner;
  compiled_by: DrillSigner;
  basis: string;
  site_code: string;
  object_name: string;
  customer: string;
  block: string;
  horizon: string;
  block_area_m2: number | null;
  rig_type_code: string;
  profile_code: string;
  rig_name: string;
  rig_number: string;
  bit_diameter_mm: number | null;
  drilling_start: string;
  drilling_end: string;
  site_preparation: string;
  stakeout: string;
  drilling_order: string;
  access_route: string;
  power_lines: string;
  adjacent_works: string;
  acceptance: string;
  extra_approvals: string[];
  tol_depth_m: number;
  tol_collar_m: number;
  personnel: DrillPerson[];
  alpha_deg: number | null;
  gamma_deg: number | null;
  axis_offset_m: number | null;
  bench_height_for_s_m: number | null;
};

export type DrillPassportStatus = "draft" | "approved" | "drilled" | "accepted";

export type DrillPassport = {
  id: string;
  design_id: string;
  passport_no: string;
  passport_date: string;
  status: DrillPassportStatus;
  version: number;
  current_revision_id: string | null;
  payload: DrillPassportPayload;
  created_at: string;
  created_by: string;
  updated_at: string;
  updated_by: string;
};

export type DrillPassportUpdate = {
  passport_no: string;
  passport_date: string;
  payload: DrillPassportPayload;
  expected_version: number;
};

export type DrillPassportIssue = { level: "error" | "warning"; code: string; message: string; path: string };

/** Происхождение величины (`FIELD_SOURCES`). */
export type Provenance = "MANUAL_OVERRIDE" | "REFERENCE" | "DESIGN" | "CALCULATED";

/** `design/drilling_passport.py::FirstRowCheck.to_dict`. */
export type FirstRowCheck = {
  h1_m: number | null;
  prism_m: number | null;
  s_m: number | null;
  c_min_m: number | null;
  /** Наименьшее расстояние устья первого ряда до верхней бровки по проекту. */
  c_m: number | null;
  /** Наибольшее расстояние устья первого ряда до верхней бровки по проекту. */
  c_max_m?: number | null;
  w_m: number | null;
  w_max_m: number | null;
  hs_m: number | null;
  hs_source: Provenance | null;
  issues: DrillPassportIssue[];
};

export type DrillPassportValidation = {
  valid: boolean;
  issues: DrillPassportIssue[];
  summary: Record<string, unknown>;
  first_row_check: FirstRowCheck;
  inputs: Record<string, number | null>;
  provenance: Record<string, Provenance | null>;
};

export type StakeoutProfile = { name: string; format: string };

export type DrillPassportRevision = {
  id: string;
  passport_id: string;
  revision_no: number;
  content_sha256: string;
  created_at: string;
  created_by: string;
  /** Снимок ревизии; интерфейсу из него нужны только профили файла выноса (PR 5). */
  context: {
    stakeout?: { default: string; profiles: Record<string, StakeoutProfile> };
    [key: string]: unknown;
  };
};

/** Файлы ревизии (кроме файла выноса — у него профиль). */
export type DrillPassportFile = "passport.pdf" | "holes.dxf" | "holes.dwg" | "coords.pdf" | "coords.xlsx" | "package.zip";
