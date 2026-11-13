// Проект МВ по форме ВМ.09.03 (TASK-018, контекст v2) — поля 1:1 с
// api/schemas/mass_blast.py. Значения из справочников окно берёт только из
// посчитанного сервером контекста (`POST /validate`), полей справочников не знает.
import type { MassBlastGuardPost, MassBlastProject, MassBlastResponsibility } from "./design";

export type MassBlastStatus = MassBlastProject["lifecycle_status"];

export type MassBlastPerson = { position: string; name: string };
export type MassBlastSigner = MassBlastPerson & { authority: string; is_head: boolean | null };

export type MassBlastRequisites = {
  project_no: string;
  project_date: string;
  tp_basis: string;
  made_by: MassBlastPerson;
  checked_by: MassBlastPerson;
  customer_name: string;
  contractor_name: string;
  customer_approver: MassBlastSigner;
  contractor_approver: MassBlastSigner;
  agreements: MassBlastPerson[];
  surveyor_name: string;
  drilled_by: "" | "CUSTOMER" | "CONTRACTOR";
};

export type MassBlastExplosives = {
  bit_mm: number | null;
  reaming_k: number | null;
  initiation: string;
  scheme: string;
  charge_design: string;
  stemming_material: string;
  starter_product: string;
  q_tp_kg_m3: number | null;
  q_just: string;
};

export type MassBlastSchedule = {
  charging_from: string;
  charging_shift_from: string;
  charging_shift_to: string;
  charging_order: string;
  network_order: string;
  station: string;
  shelter: string;
  gather: string;
  exit_route: string;
  siren: string;
  measures: string;
  other_conditions: string;
  airblast_buildings: string;
  transport: string;
  cleaning: string;
  briefing_date: string;
  szm_start_flank: "" | "left" | "right";
};

export type MassBlastPersonnel = { role_code: string; position: string; name: string };

export type MassBlastProtectedObject = {
  source: "MANUAL" | "SITUATION";
  key: string;
  name: string;
  kind: "" | "people" | "buildings" | "structures" | "mechanisms";
  distance_m: number | null;
  sensitive: boolean;
  measures: string;
  k_ground: number | null;
  k_structure: number | null;
};

export type LayoutPointKind = "guard_post" | "blast_station" | "shelter" | "gather";
export type MassBlastLayoutPoint = { kind: LayoutPointKind; ref: string; x: number; y: number; label: string };

export type MassBlastBlockDetails = {
  rock_text: string;
  hydro_text: string;
  purpose: "" | "MINING" | "STRIPPING";
  area_m2: number | null;
  hole_notes: Record<string, string>;
};

export type MassBlastBlockV2 = {
  design_id: string;
  technical_passport_id?: string | null;
  code: string;
  horizon: string;
  details?: MassBlastBlockDetails | null;
};

export type ManualZone = { value: number | null; reason: string };

export type MassBlastProjectV2 = Omit<MassBlastProject, "blocks"> & {
  context_version: number;
  blocks: Array<MassBlastBlockV2 & Record<string, unknown>>;
  requisites: Partial<MassBlastRequisites> | null;
  explosives: Partial<MassBlastExplosives> | null;
  schedule: Partial<MassBlastSchedule> | null;
  personnel: MassBlastPersonnel[];
  protected_objects: MassBlastProtectedObject[];
  safety_overrides: Record<string, number | boolean | null>;
  layout_points: MassBlastLayoutPoint[];
};

export type MassBlastProjectInputV2 = {
  name: string;
  site_code: string;
  object_name: string;
  customer_code: string;
  blast_date: string;
  blast_time: string;
  document_profile_code: string;
  reference_revision_id?: string | null;
  blocks: MassBlastBlockV2[];
  responsibilities: MassBlastResponsibility[];
  safety_plan: Record<string, unknown>;
  charging_schedule: Array<Record<string, unknown>>;
  signal_plan: Record<string, unknown>;
  guard_posts: MassBlastGuardPost[];
  notifications: Array<{ recipient: string; channel: string; sent_at: string }>;
  context_version: 2;
  requisites: MassBlastRequisites;
  explosives: MassBlastExplosives;
  schedule: MassBlastSchedule;
  personnel: MassBlastPersonnel[];
  protected_objects: MassBlastProtectedObject[];
  safety_overrides: Record<string, number | boolean | null>;
  layout_points: MassBlastLayoutPoint[];
  expected_version?: number;
};

export type MassBlastIssue = { level: "error" | "warning"; code: string; message: string; path: string };

/** Величина расчёта с формулой и источником (`SafetyValue`). */
export type MassBlastValue = {
  value: number | string | null;
  unit?: string;
  formula?: string;
  substitution?: string;
  basis?: string;
  source?: string;
  factor?: string;
  note?: string;
  label?: string;
};

export type ConsumptionLine = {
  kind: string;
  name: string;
  quantity: number;
  unit: string;
  mass_kg: number | null;
  delay_ms: number | null;
};

export type ParameterRow = { hole_id: string; first_row: boolean; note: string; lspp_m: number | null };

export type TechSection = { number: string; title: string; items?: MassBlastValue[] };

export type ProtectedObjectRow = {
  key: string;
  name: string;
  kind: string;
  kind_label?: string;
  source: string;
  distance_m: number | null;
  required_m: number | null;
  factor?: string;
  /** «В ЗОНЕ» или «вне зоны» (`design/safety/objects.py`). */
  position: string;
  measures?: string;
  sensitive?: boolean;
  k_ground?: number | null;
  k_structure?: number | null;
};

export type GraphicsZone = { kind: string; value_m: number; rings: Array<Array<[number, number]>> };
export type GraphicsSituationLayer = { name: string; kind: string; lines: Array<Array<[number, number]>> };
export type GraphicsPoint = {
  kind: LayoutPointKind;
  number: number | null;
  ref: string;
  label: string;
  x: number;
  y: number;
  distance_m: number | null;
};
export type ProjectGraphics = {
  outlines: Array<Array<[number, number]>>;
  zones: GraphicsZone[];
  situation: GraphicsSituationLayer[];
  has_situation: boolean;
  objects: Array<{ number: number; key: string; link?: Array<[number, number]> | null }>;
  points: GraphicsPoint[];
};

export type ScheduleSignalRow = { point: string; action: string; signal: string; time: string; not_earlier: boolean };

/** Контекст v2 в той части, которую показывает окно. */
export type MassBlastContextV2 = {
  document_context_version: number;
  requisites?: Partial<MassBlastRequisites> & Record<string, unknown>;
  explosives?: Partial<MassBlastExplosives>;
  personnel?: Array<MassBlastPersonnel & { role_label: string }>;
  zones?: Record<string, MassBlastValue & { block_index?: number }>;
  protected_objects?: ProtectedObjectRow[];
  q_tp?: { value: number | null; source: string; basis?: string; justification?: string } | null;
  network_intervals?: string[];
  schedule?: { signals?: { title?: string; rows: ScheduleSignalRow[] } };
  graphics?: ProjectGraphics;
  blocks_v2?: Array<{
    design_id: string;
    code: string;
    horizon: string;
    safety?: { params?: Record<string, unknown> & { sources?: Record<string, string> } };
    consumption?: ConsumptionLine[];
    technical_calculation?: TechSection[];
    parameter_table?: { rows: ParameterRow[]; common_note?: string };
    graphics?: unknown;
  }>;
};

/** Значение по умолчанию поля (§14 плана PR 6): что подставится в пустое поле и откуда. */
export type FieldDefault = { value: unknown; source: string };

export type MassBlastValidationV2 = {
  valid: boolean;
  issues: MassBlastIssue[];
  context: MassBlastContextV2;
  /** Путь поля payload → значение по умолчанию. */
  defaults?: Record<string, FieldDefault>;
  /** «Запомнить для объекта»: путь поля → значение в справочнике объекта (null — пусто). */
  rememberable?: Record<string, unknown>;
};

export type SuggestedLayout = {
  posts: Array<{ code: string; location: string }>;
  points: MassBlastLayoutPoint[];
  reason: string;
};

export type MassBlastHints = {
  previous_project_no: string;
  previous_project_date: string;
  previous_project_name: string;
  personnel_roles: Array<{ code: string; label: string }>;
};

export type LayerKind = "NARYAD" | "NOTIFICATION" | "READINESS_ACT" | "TALON" | "ACCEPTANCE_ACT" | "EXECUTION";

export type LayerAvailability = {
  kind: LayerKind;
  label: string;
  can_open: boolean;
  reason: string;
  multiple: boolean;
  count: number;
};

export type NaryadLine = {
  key: string;
  kind: string;
  name: string;
  unit: string;
  delay_ms: number | null;
  project_qty: number;
  reserve_qty: number;
  reserve_source: string;
  issue_qty: number;
  issue_kg: number | null;
  issued_qty?: number | null;
  consumed_qty?: number | null;
  returned_qty?: number | null;
  /** Откуда графы после взрыва: MAGEX — исполнение MagEX (TASK-018 PR 7), ручной ввод закрыт. */
  issued_source?: string;
  consumed_source?: string;
  returned_source?: string;
  outside_project?: boolean;
};

// --- Наряд-путёвка ↔ MagEX (TASK-018, PR 7) ---------------------------------

export type MagexOption = { value: string; label: string };

/** Вариант выпадающего списка наряда: подпись и поля наряда, которые выбор подставит (сервер). */
export type NaryadChoice = { value: string; label: string; fill: Record<string, string> };
export type NaryadOptions = {
  warehouses: NaryadChoice[];
  blasters: NaryadChoice[];
  vehicles: NaryadChoice[];
  drivers: NaryadChoice[];
  escorts: NaryadChoice[];
};

export type MagexVersion = {
  ver: number;
  status: "SENDING" | "PENDING" | "ACCEPTED" | "REJECTED" | "SUPERSEDED";
  response_code: number | null;
  response: { code?: string; message?: string; details?: Record<string, unknown> };
  attempts: number;
  next_attempt_at: string | null;
  created_at: string;
  created_by: string;
  accepted_at: string | null;
  layer_revision_id: string | null;
};

export type MagexExecutionLine = {
  material_id: string;
  ordered: string; issued: string; returned: string; consumed: string; lost: string; on_hand: string;
  ordered_kg: string | null; issued_kg: string | null; returned_kg: string | null; consumed_kg: string | null;
  lost_kg: string | null; on_hand_kg: string | null;
};

export type MagexExecution = {
  status: string;
  status_label: string;
  version: number;
  lines: MagexExecutionLine[];
  issued_batches: Array<{ material_id: string; batch_no: string; manufacturer: string; issued: string; issued_kg: string | null }>;
  cancellation: { at: string; reason: string } | null;
  fetched_at: string;
};

/** Состояние наряда в MagEX: режим, версии выписки, последнее исполнение. Собирает сервер. */
export type MagexState = {
  mode: "ONLINE" | "OFFLINE" | null;
  reason?: string;
  versions?: MagexVersion[];
  latest?: MagexVersion | null;
  accepted_ver?: number | null;
  /** Позиция MagEX → наименования строк наряда. */
  material_names?: Record<string, string>;
  execution?: MagexExecution;
  issued?: boolean;
  locked_fields?: string[];
  refresh_error?: string;
  blaster?: { code: string; name: string; index: string; source: string } | null;
};

export type MagexApproveResult = MagexState & {
  outcome: "ACCEPTED" | "REJECTED" | "PENDING" | "UNCHANGED" | "UNCHANGED_UNREACHABLE" | "NOTHING_PENDING";
  rejection?: { code: string; message: string; details: Record<string, unknown> };
  /** Выписка та же, но выпущена новая ревизия для печати (графы после взрыва). */
  reprinted?: boolean;
  /** Предупреждения выписки (округление до целых патронов, нет разрешения на ВР). */
  warnings?: MassBlastIssue[];
};

export type MagexAvailability = {
  items: Record<string, {
    available: number; short: boolean; shared: boolean; material_id?: string;
    /** Доступно в единице учёта MagEX, множитель строки к ней и «штучная позиция» (вверх до целого). */
    available_magex?: number; factor?: number; whole?: boolean;
  }>;
  shortages?: Array<{ material: string; required: number; available: number; unit: string }>;
  calculated_at?: string | null;
  error: string;
};

export type MagexBlasterStatus = {
  blaster: { code: string; name: string; index: string; ref: string } | null;
  reported: boolean | null;
  pending?: Array<{ id: string; number: string; issued_on: string; blast_on: string | null; site_name: string; status: string }>;
  error?: string;
};

export type MassBlastLayer = {
  id: string;
  project_id: string;
  kind: LayerKind;
  project_revision_id: string;
  status: "draft" | "issued";
  version: number;
  current_revision_id: string | null;
  stale: boolean;
  seed: Record<string, unknown>;
  payload: Record<string, unknown>;
  view: Record<string, unknown>;
  issues: MassBlastIssue[];
  created_at: string;
  updated_at: string;
};

/** Изменение переноса: подпись и тексты «было / станет» собирает сервер (`design/mass_blast_layer_diff.py`). */
export type LayerChange = { path: string; label: string; before_text: string; after_text: string };

export type LayerRefreshResponse = { applied: boolean; changes: LayerChange[]; layer: MassBlastLayer };

export type LayerRevision = {
  id: string;
  layer_id: string;
  revision_no: number;
  project_revision_id: string;
  content_sha256: string;
  created_at: string;
};

export type NotificationAddressees = {
  registry: boolean;
  items: Array<{ code: string; label: string; taken: boolean }>;
};

/** Документы проекта, которые печатает сервер (`design/reporting/mass_blast/project.DOCUMENTS` + «project»). */
export type ProjectDocument = "title" | "technical-calculation" | "parameter-table" | "schedule" | "graphics" | "project";
