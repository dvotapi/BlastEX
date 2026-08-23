import { del, get, post, put, requestSvg } from "./client";
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
import type {
  AnalyzeResponse,
  BlastDesign,
  BlockContour,
  ChargeExplosive,
  ChargeGenerateResponse,
  ChargeRules,
  CoordinateSystem,
  CostScenarioId,
  DesignCostResult,
  DesignSummary,
  Hole,
  EngineeringMaps,
  PatternGenerateResponse,
  PpvRequest,
  SchemeType,
  SurfaceKind,
  SurfaceModel,
  SurfaceSet,
  SurfaceStats,
  TieGenerateResponse,
  TieParams,
  BlastDomain,
  GeologyInterceptResponse,
  FragmentationPredictResponse,
  Receptor,
  VibrationMeasurement,
  VibrationPredictResponse,
  AsDrilledHole,
  AsDrilledCompareResponse,
  MwdSchemaResponse,
} from "../types/design";

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
    oversizeCoeff: number;
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
        hole_oversize_coeff: input.oversizeCoeff,
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

  // --- проектирование БВР ---
  design: {
    pattern: (
      contour: BlockContour,
      params: Record<string, unknown>,
      existingHoles: Hole[] = [],
      surfaces?: SurfaceSet,
      domains: BlastDomain[] = [],
    ) =>
      post<PatternGenerateResponse>(`${V1}/design/pattern`, {
        contour,
        params,
        existing_holes: existingHoles,
        surfaces,
        domains,
      }),
    maps: (design: BlastDesign) => post<EngineeringMaps>(`${V1}/design/maps`, { design }),
    fragmentationModels: () => get<{ models: Array<{ id: string; version: string; label: string; distribution: string }> }>(
      `${V1}/design/fragmentation/models`,
    ),
    fragmentation: (payload: {
      design: BlastDesign;
      model: string;
      lump_size_mm: number;
      max_oversize_pct?: number;
      calibration?: Record<string, number | null>;
      rock?: { name: string; density_t_m3: number; ucs_mpa: number; fissuring_ff: number };
      explosive?: ChargeExplosive;
      explosives?: ChargeExplosive[];
      hole_oversize_coeff?: number;
    }) => post<FragmentationPredictResponse>(`${V1}/design/fragmentation`, payload),
    editHoleGeometry: (payload: {
      hole: Hole;
      patch: Record<string, unknown>;
      contour?: BlockContour;
      surfaces?: SurfaceSet;
    }) => post<{ hole: Hole }>(`${V1}/design/holes/geometry`, payload),
    insertHole: (payload: {
      contour: BlockContour;
      x: number;
      y: number;
      params?: Record<string, unknown>;
      existing_holes?: Hole[];
      surfaces?: SurfaceSet;
    }) => post<{ hole: Hole }>(`${V1}/design/holes/insert`, payload),
    importSurface: (payload: {
      content: string;
      filename: string;
      kind: SurfaceKind;
      format?: string;
      name?: string;
      coordinate_system?: CoordinateSystem;
    }) =>
      post<{ surface: SurfaceModel; stats: SurfaceStats }>(`${V1}/design/surfaces/import`, payload),
    sampleSurface: (surface: SurfaceModel, points: Array<[number, number]>) =>
      post<{ elevations: Array<number | null> }>(`${V1}/design/surfaces/sample`, { surface, points }),
    assignDomain: (domain: BlastDomain, polygon: BlastDomain["polygon"]) =>
      post<{ domain: BlastDomain }>(`${V1}/design/geology/assign`, { domain, polygon }),
    interceptGeology: (holes: Hole[], domains: BlastDomain[], waterTableZ: number | null) =>
      post<GeologyInterceptResponse>(`${V1}/design/geology/intercept`, {
        holes,
        domains,
        water_table_z_m: waterTableZ,
      }),
    charge: (
      holes: Hole[],
      rules: ChargeRules,
      explosive: ChargeExplosive,
      extras?: { contour?: BlockContour; explosives?: ChargeExplosive[] },
    ) =>
      post<ChargeGenerateResponse>(`${V1}/design/charge`, {
        holes,
        rules,
        explosive,
        contour: extras?.contour,
        explosives: extras?.explosives ?? [],
      }),
    tie: (holes: Hole[], scheme: SchemeType, params: TieParams & Record<string, unknown>) =>
      post<TieGenerateResponse>(`${V1}/design/tie/generate`, { holes, scheme, params }),
    analyze: (design: BlastDesign, isolineStepMs: number, micWindowMs: number, ppv: PpvRequest | null) =>
      post<AnalyzeResponse>(`${V1}/design/analyze`, {
        design,
        isoline_step_ms: isolineStepMs,
        mic_window_ms: micWindowMs,
        ppv,
      }),
    attachReceptor: (design: BlastDesign, receptor: Receptor) =>
      post<{ receptor: Receptor; receptors: Receptor[] }>(`${V1}/design/receptors`, { design, receptor }),
    vibrationConventions: () =>
      get<{ conventions: Array<{ id: string; label: string; formula: string }>; law: string }>(
        `${V1}/design/vibration/conventions`,
      ),
    vibration: (payload: {
      design: BlastDesign;
      model_id?: string;
      mic_window_ms?: number;
      measured?: VibrationMeasurement[];
    }) => post<VibrationPredictResponse>(`${V1}/design/vibration`, payload),
    mwdSchema: () => get<MwdSchemaResponse>(`${V1}/design/as-drilled/mwd-schema`),
    recordAsDrilled: (design: BlastDesign, holes: AsDrilledHole[], replace = false) =>
      post<AsDrilledCompareResponse & { holes: Hole[] }>(`${V1}/design/as-drilled`, { design, holes, replace }),
    compareAsDrilled: (design: BlastDesign) =>
      post<AsDrilledCompareResponse>(`${V1}/design/as-drilled/compare`, { design }),
    importMwd: (design: BlastDesign, design_hole_id: string, samples: Record<string, number | null>[], source = "") =>
      post<AsDrilledCompareResponse & { holes: Hole[] }>(`${V1}/design/as-drilled/mwd`, {
        design,
        design_hole_id,
        samples,
        source,
      }),
    cost: (design: BlastDesign, scenarioId: CostScenarioId) =>
      post<DesignCostResult>(`${V1}/design/cost`, { design, scenario_id: scenarioId }),
    passportUrl: (designId: string) => `${V1}/design/plans/${designId}/passport.html`,
    listPlans: () => get<{ items: DesignSummary[] }>(`${V1}/design/plans`),
    createPlan: (design: BlastDesign) => post<BlastDesign>(`${V1}/design/plans`, design),
    getPlan: (designId: string) => get<BlastDesign>(`${V1}/design/plans/${designId}`),
    savePlan: (designId: string, design: BlastDesign) =>
      put<BlastDesign>(`${V1}/design/plans/${designId}`, design),
    deletePlan: (designId: string) => del<void>(`${V1}/design/plans/${designId}`),
    exportCsv: async (designId: string, fileName: string) => {
      const response = await fetch(`${V1}/design/plans/${designId}/export.csv`, { credentials: "include" });
      if (!response.ok) throw new Error("Не удалось экспортировать паспорт.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    },
  },
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
