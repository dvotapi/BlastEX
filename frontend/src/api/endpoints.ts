import { get, post, put, requestSvg } from "./client";
import type {
  AggregatedCostResult,
  BlastGeometryResponse,
  BlastVariant,
  CatalogItem,
  DefaultReferences,
  DrillingUnitCostInput,
  DrillingUnitCostResult,
  DrillRig,
  Explosive,
  FixedAssetDepreciation,
  InitiationConfig,
  JobPosition,
  LaborAssignment,
  LaborFOTResult,
  LaborFOTSettings,
  MaterialsSelection,
  Rock,
  ScenarioListItem,
  User,
  WorkObject,
  TeamReferences,
  WorkspaceSnapshot,
  WorkspaceState,
} from "../types";

const V1 = "/api/v1";

export const api = {
  // --- auth ---
  me: () => get<User>(`${V1}/auth/me`),
  login: (email: string, password: string) =>
    post<User>(`${V1}/auth/login`, { email, password }),
  logout: () => post<void>(`${V1}/auth/logout`, {}),

  // --- справочники (для расчёта) ---
  rocks: () => get<{ items: Rock[]; default_name: string }>(`${V1}/references/rocks`),
  putRocks: (items: Rock[]) => put<{ items: Rock[] }>(`${V1}/references/rocks`, items),
  explosives: () => get<{ items: Explosive[]; default_key: string }>(`${V1}/references/explosives`),
  putExplosives: (items: Explosive[]) =>
    put<{ items: Explosive[] }>(`${V1}/references/explosives`, items),
  workObjects: () => get<{ items: WorkObject[]; default_name: string }>(`${V1}/references/work-objects`),
  putWorkObjects: (items: WorkObject[]) =>
    put<{ items: WorkObject[] }>(`${V1}/references/work-objects`, items),
  drillRigs: () => get<{ items: DrillRig[]; default_name: string }>(`${V1}/references/drill-rigs`),
  putDrillRigs: (items: DrillRig[]) =>
    put<{ items: DrillRig[] }>(`${V1}/references/drill-rigs`, items),
  depreciationAssets: () =>
    get<{ items: FixedAssetDepreciation[] }>(`${V1}/references/depreciation-assets`),
  putDepreciationAssets: (items: FixedAssetDepreciation[]) =>
    put<{ items: FixedAssetDepreciation[] }>(`${V1}/references/depreciation-assets`, items),
  catalog: () => get<{ items: CatalogItem[] }>(`${V1}/references/catalog`),

  // --- рабочее пространство ---
  workspace: () => get<WorkspaceState>(`${V1}/workspace`),
  saveWorkspace: (payload: {
    snapshot: WorkspaceSnapshot;
    references: TeamReferences;
    active_work_object_name: string;
  }) => put<WorkspaceState>(`${V1}/workspace/snapshot`, payload),
  switchScenario: (scenario_id: string) =>
    put<WorkspaceState>(`${V1}/workspace/active-scenario`, { scenario_id }),
  workspaceDefaults: () => get<DefaultReferences>(`${V1}/workspace/defaults`),
  scenarios: () => get<ScenarioListItem[]>(`${V1}/scenarios`),

  // --- технологический расчёт ---
  blastOptions: () =>
    get<{ crown_diameters_mm: number[]; nsi_length_options_m: number[]; detonator_delay_ms_options: number[] }>(
      `${V1}/blast/options`
    ),
  optimize: (input: {
    rock: Rock;
    explosive: Explosive;
    lumpSize: number;
    benchHeight: number;
    overdrill: number;
    spacing: number;
    threshold: number;
    crownDiametersMm: number[];
  }) =>
    post<{ variants: BlastVariant[]; rock_name: string; explosive_name: string }>(`${V1}/blast/optimize`, {
      rock: input.rock,
      explosive: {
        name: input.explosive.name,
        density_t_m3: input.explosive.density_t_m3,
        power_mj_kg: input.explosive.power_mj_kg,
      },
      target: {
        lump_size_mm: input.lumpSize,
        hole_diameter_mm: 0,
        overdrill_m: input.overdrill,
        hole_oversize_coeff: 1.05,
        spacing_coeff_m: input.spacing,
        bench_height_m: input.benchHeight,
      },
      crown_diameters_mm: input.crownDiametersMm,
      max_oversize_threshold_pct: input.threshold,
    }),
  geometry: (payload: GeometryRequest) => post<BlastGeometryResponse>(`${V1}/blast/geometry`, payload),
  holeSchemeSvg: (payload: GeometryRequest) =>
    requestSvg(`${V1}/blast/hole-scheme`, { method: "POST", body: JSON.stringify(payload) }),

  // --- смета ---
  calculateCost: (payload: Record<string, unknown>) =>
    post<AggregatedCostResult>(`${V1}/cost/calculate`, payload),
  drillingUnit: (input: DrillingUnitCostInput) =>
    post<{ result: DrillingUnitCostResult; summary_rows: [string, string][] }>(`${V1}/cost/drilling-unit`, {
      input,
    }),
  labor: (payload: {
    labor_catalog: JobPosition[];
    labor_assignments: LaborAssignment[];
    settings: LaborFOTSettings;
  }) =>
    post<{ result: LaborFOTResult; table_rows: Record<string, string | number>[]; summary_rows: [string, string][] }>(
      `${V1}/cost/labor`,
      payload
    ),
  materialsAuto: (explosive_key: string, initiation: InitiationConfig) =>
    post<{ selection: MaterialsSelection }>(`${V1}/cost/materials-auto`, { explosive_key, initiation }),
};

export type GeometryRequest = {
  grid_a_m: number;
  grid_b_m: number;
  depth_m: number;
  overdrill_m: number;
  undercharge_m: number;
  crown_mm: number;
  hole_oversize_coeff: number;
  explosive_key: string;
  block_volume_m3: number;
  additional_holes_pct: number;
  intermediate_detonators_per_hole: number;
  nsi_per_hole: number;
  nsi_length_1_m: number;
  nsi_length_2_m: number;
  detonator_delay_ms: number;
  view: "charge" | "contour" | "drilling";
};
