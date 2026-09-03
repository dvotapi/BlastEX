import { del, get, post, postFile, put, requestSvg } from "./client";
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
  LifecycleMeta,
  LifecycleState,
  WorkstationMeta,
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
  MovementPredictResponse,
  Receptor,
  VibrationMeasurement,
  VibrationPredictResponse,
  AsDrilledHole,
  AsDrilledCompareResponse,
  AsChargedHole,
  AsChargedCompareResponse,
  AsFiredHole,
  AsFiredCompareResponse,
  ExecutionCompareResponse,
  BlastPassport,
  BlastResult,
  BlastResultCompareResponse,
  DatasetSnapshot,
  DatasetSummary,
  SampleValidation,
  CalibrationAlgorithm,
  CalibrationModel,
  CalibrationModelType,
  CalibrationPredictResponse,
  CalibrationSummary,
  OutcomeModel,
  OutcomeModelType,
  OutcomePanelResponse,
  OutcomePredictResponse,
  OutcomeSummary,
  DesignScenario,
  DesignScenarioParams,
  DesignScenarioSummary,
  OptimizationResult,
  DesignRecommendation,
  ScenarioCompareResponse,
  PredictedFragmentation,
  PredictedVibrationSnapshot,
  PlannedCost,
  DesignedFragmentationTarget,
  DesignedMuckpile,
  DesignedBackbreak,
  MwdSchemaResponse,
  LearningModel,
  LearningPredictResponse,
  LearningSummary,
  RegistryRecord,
  DriftAlert,
  DriftReport,
  SpatialModel,
  SpatialOverlay,
  SpatialSummary,
  MassBlastDocument,
  MassBlastAttachment,
  MassBlastProject,
  MassBlastProjectSummary,
  MassBlastProjectInput,
  MassBlastRevision,
  MassBlastValidation,
  BenchDxfImport,
  DrawingScan,
  Point3,
} from "../types/design";
import type {
  CalculationRun,
  EconomicScenario,
  EconomicsReferenceItem,
  EconomicsReferenceSnapshot,
  ReferenceRevision,
  ReferenceValidation,
  StoredEconomicScenario,
  TechnicalDriverSnapshot,
} from "../types/economics";
import type {
  BlockEconomics,
  EconomicsRun,
  EconomicsRunSummary,
  ModelDefaults,
  ModelParameters,
  RunCompare,
  SensitivityRow,
  TechnicalPassport,
} from "../types/blockEconomics";
import type { ReferenceSchemaCatalog } from "../types/referenceSchema";

const V1 = "/api/v1";

export const api = {
  /** Какие модули включены в этой установке (ML-слой за фича-флагом). */
  features: () => get<{ intelligence: boolean }>(`${V1}/features`),
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

  // --- Cost V2: экономика производственного юнита ---
  economics: {
    technicalDrivers: (
      block: Record<string, unknown>,
      existingPhysical: Record<string, number | string> = {},
      sourceId?: string,
    ) => post<TechnicalDriverSnapshot>(`${V1}/economics/technical-drivers`, {
      block,
      existing_physical: existingPhysical,
      source_id: sourceId ?? null,
    }),
    referenceSchema: () => get<ReferenceSchemaCatalog>(`${V1}/economics/references/schema`),
    referenceSnapshot: (revisionId?: string) =>
      get<EconomicsReferenceSnapshot>(
        `${V1}/economics/references/snapshot${revisionId ? `?revision_id=${encodeURIComponent(revisionId)}` : ""}`
      ),
    validateReferences: (sections: Record<string, EconomicsReferenceItem[]>) =>
      post<ReferenceValidation>(`${V1}/economics/references/validate`, { sections }),
    publishReferences: (payload: {
      base_revision: string;
      sections: Record<string, EconomicsReferenceItem[]>;
      comment: string;
    }) => post<EconomicsReferenceSnapshot>(`${V1}/economics/references/publish`, payload),
    revisions: () => get<ReferenceRevision[]>(`${V1}/economics/references/revisions`),
    scenarios: () => get<StoredEconomicScenario[]>(`${V1}/economics/scenarios`),
    scenario: (id: string) => get<StoredEconomicScenario>(`${V1}/economics/scenarios/${id}`),
    createScenario: (scenario: EconomicScenario) =>
      post<StoredEconomicScenario>(`${V1}/economics/scenarios`, scenario),
    updateScenario: (id: string, scenario: EconomicScenario) =>
      put<StoredEconomicScenario>(`${V1}/economics/scenarios/${id}`, scenario),
    cloneScenario: (id: string) =>
      post<StoredEconomicScenario>(`${V1}/economics/scenarios/${id}/clone`, {}),
    calculateScenario: (id: string) =>
      post<CalculationRun>(`${V1}/economics/scenarios/${id}/calculate`, {}),
    calculationRun: (id: string) =>
      get<CalculationRun>(`${V1}/economics/calculation-runs/${id}`),
    technicalPassports: (siteCode?: string) =>
      get<TechnicalPassport[]>(
        `${V1}/economics/technical-passports${siteCode ? `?site_code=${encodeURIComponent(siteCode)}` : ""}`
      ),
    technicalPassport: (id: string) =>
      get<TechnicalPassport>(`${V1}/economics/technical-passports/${id}`),
    createTechnicalPassport: (payload: {
      site_code: string;
      object_name: string;
      reference_revision_id?: string | null;
      previous_passport_id?: string | null;
      formula_version?: string;
      block: Record<string, unknown>;
      input_snapshot?: Record<string, unknown>;
      selected_variant?: Record<string, unknown>;
      existing_physical?: Record<string, number | string>;
    }) => post<TechnicalPassport>(`${V1}/economics/technical-passports`, payload),
  },

  // --- Cost V2: экономика блока (модель себестоимости) ---
  blockEconomics: {
    modelDefaults: (passportId: string, packageCode: string) =>
      get<ModelDefaults>(
        `${V1}/economics/model-defaults?technical_passport_id=${encodeURIComponent(passportId)}` +
          `&package_code=${encodeURIComponent(packageCode)}`
      ),
    compute: (technicalPassportId: string, parameters: ModelParameters) =>
      post<BlockEconomics>(`${V1}/economics/block-economics`, {
        technical_passport_id: technicalPassportId,
        parameters,
      }),
    sensitivity: (technicalPassportId: string, parameters: ModelParameters) =>
      post<{ rows: SensitivityRow[] }>(`${V1}/economics/block-economics/sensitivity`, {
        technical_passport_id: technicalPassportId,
        parameters,
      }),
    saveRun: (technicalPassportId: string, parameters: ModelParameters, name: string) =>
      post<EconomicsRun>(`${V1}/economics/runs`, {
        technical_passport_id: technicalPassportId,
        parameters,
        name,
      }),
    runs: (passportId?: string) =>
      get<EconomicsRunSummary[]>(
        `${V1}/economics/runs${passportId ? `?technical_passport_id=${encodeURIComponent(passportId)}` : ""}`
      ),
    run: (id: string) => get<EconomicsRun>(`${V1}/economics/runs/${id}`),
    compare: (runIds: string[]) => post<RunCompare>(`${V1}/economics/runs/compare`, { run_ids: runIds }),
    exportUrl: (id: string) => `${V1}/economics/runs/${id}/export.xlsx`,
  },

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
    movementModels: () => get<{
      models: Array<{ id: string; version: string; label: string }>;
      kind: string;
      label_ru: string;
      label_en: string;
      disclaimer: string;
      is_physics_simulation: boolean;
    }>(`${V1}/design/movement/models`),
    movement: (payload: { design: BlastDesign }) =>
      post<MovementPredictResponse>(`${V1}/design/movement`, payload),
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
    importBenchDxf: (payload: { content: string; filename: string; coordinate_system?: CoordinateSystem }) =>
      post<BenchDxfImport>(`${V1}/design/contour/import-dxf`, payload),
    scanDrawing: (file: File) => postFile<DrawingScan>(`${V1}/design/drawing/polylines`, file),
    benchFromPolylines: (payload: {
      crest: Point3[];
      toe: Point3[];
      crest_layer?: string;
      toe_layer?: string;
      filename?: string;
      coordinate_system?: CoordinateSystem;
    }) => post<BenchDxfImport>(`${V1}/design/contour/from-polylines`, payload),
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
    recordAsCharged: (design: BlastDesign, holes: AsChargedHole[], replace = false) =>
      post<AsChargedCompareResponse & { holes: Hole[]; loads: BlastDesign["loads"] }>(`${V1}/design/as-charged`, {
        design,
        holes,
        replace,
      }),
    compareAsCharged: (design: BlastDesign) =>
      post<AsChargedCompareResponse>(`${V1}/design/as-charged/compare`, { design }),
    recordAsFired: (design: BlastDesign, holes: AsFiredHole[], replace = false) =>
      post<AsFiredCompareResponse & { holes: Hole[]; network: BlastDesign["network"] }>(`${V1}/design/as-fired`, {
        design,
        holes,
        replace,
      }),
    compareAsFired: (design: BlastDesign) =>
      post<AsFiredCompareResponse>(`${V1}/design/as-fired/compare`, { design }),
    compareExecution: (design: BlastDesign) =>
      post<ExecutionCompareResponse>(`${V1}/design/execution/compare`, { design }),
    recordBlastResult: (
      design: BlastDesign,
      result: BlastResult,
      extras: {
        predicted_fragmentation?: PredictedFragmentation | null;
        predicted_vibration?: PredictedVibrationSnapshot[];
        planned_cost?: PlannedCost | null;
        designed_fragmentation?: DesignedFragmentationTarget | null;
        designed_muckpile?: DesignedMuckpile | null;
        designed_backbreak?: DesignedBackbreak | null;
        designed_toe_condition?: string;
      } = {},
    ) =>
      post<BlastResultCompareResponse & { holes: Hole[]; loads: BlastDesign["loads"]; network: BlastDesign["network"] }>(
        `${V1}/design/blast-result`,
        { design, result, ...extras },
      ),
    compareBlastResult: (design: BlastDesign) =>
      post<BlastResultCompareResponse>(`${V1}/design/blast-result/compare`, { design }),
    listDatasets: () => get<{ items: DatasetSummary[] }>(`${V1}/datasets`),
    buildDataset: (payload: {
      site_id: string;
      name?: string;
      design_ids?: string[];
      include_design?: BlastDesign;
    }) => post<DatasetSnapshot>(`${V1}/datasets`, payload),
    getDataset: (datasetId: string) => get<DatasetSnapshot>(`${V1}/datasets/${datasetId}`),
    previewDatasetSample: (site_id: string, design: BlastDesign) =>
      post<SampleValidation>(`${V1}/datasets/preview`, { site_id, design }),
    listCalibrationModels: () => get<{ items: CalibrationSummary[] }>(`${V1}/calibration/models`),
    trainCalibration: (payload: {
      dataset_id: string;
      model_type: CalibrationModelType | string;
      algorithm?: string;
      site_id?: string;
    }) => post<CalibrationModel>(`${V1}/calibration/models`, payload),
    getCalibrationModel: (modelId: string) => get<CalibrationModel>(`${V1}/calibration/models/${modelId}`),
    setCalibrationStatus: (modelId: string, status: string) =>
      post<CalibrationModel>(`${V1}/calibration/models/${modelId}/status`, { status }),
    predictCalibration: (payload: {
      model_type: CalibrationModelType | string;
      model_id?: string;
      site_id?: string;
      use_production?: boolean;
      baseline?: number | null;
      features?: Record<string, unknown>;
      design?: BlastDesign;
    }) => post<CalibrationPredictResponse>(`${V1}/calibration/predict`, payload),
    calibrationAlgorithms: () => get<{ items: CalibrationAlgorithm[]; default: string }>(`${V1}/calibration/algorithms`),
    listOutcomeModels: (modelType?: string) =>
      get<{ items: OutcomeSummary[] }>(`${V1}/outcomes/models${modelType ? `?model_type=${encodeURIComponent(modelType)}` : ""}`),
    trainOutcome: (payload: {
      dataset_id: string;
      model_type: OutcomeModelType | string;
      algorithm?: string;
      site_id?: string;
    }) => post<OutcomeModel>(`${V1}/outcomes/models`, payload),
    getOutcomeModel: (modelId: string) => get<OutcomeModel>(`${V1}/outcomes/models/${modelId}`),
    setOutcomeStatus: (modelId: string, status: string) =>
      post<OutcomeModel>(`${V1}/outcomes/models/${modelId}/status`, { status }),
    predictOutcome: (payload: {
      model_type: OutcomeModelType | string;
      model_id?: string;
      site_id?: string;
      use_production?: boolean;
      features?: Record<string, unknown>;
      design?: BlastDesign;
    }) => post<OutcomePredictResponse>(`${V1}/outcomes/predict`, payload),
    predictAllOutcomes: (payload: {
      site_id?: string;
      use_production?: boolean;
      model_ids?: Partial<Record<OutcomeModelType, string>>;
      features?: Record<string, unknown>;
      design?: BlastDesign;
    }) => post<OutcomePanelResponse>(`${V1}/outcomes/predict-all`, payload),
    outcomeAlgorithms: () => get<{ items: CalibrationAlgorithm[]; default: string }>(`${V1}/outcomes/algorithms`),
    outcomeModelTypes: () =>
      get<{ items: Array<{ name: string; class_name: string; label: string; primary_target: string }> }>(
        `${V1}/outcomes/model-types`,
      ),
    listLearningModels: (query?: { model_type?: string; scope?: string; site_id?: string }) => {
      const params = new URLSearchParams();
      if (query?.model_type) params.set("model_type", query.model_type);
      if (query?.scope) params.set("scope", query.scope);
      if (query?.site_id) params.set("site_id", query.site_id);
      const suffix = params.toString() ? `?${params.toString()}` : "";
      return get<{ items: LearningSummary[]; auto_approved: boolean }>(`${V1}/learning/models${suffix}`);
    },
    trainLearningGlobal: (payload: {
      dataset_ids: string[];
      model_type: OutcomeModelType | string;
      algorithm?: string;
    }) => post<LearningModel>(`${V1}/learning/global`, payload),
    trainLearningSite: (payload: {
      dataset_ids: string[];
      site_id: string;
      model_type: OutcomeModelType | string;
      algorithm?: string;
      prior_model_id?: string;
    }) => post<LearningModel>(`${V1}/learning/site`, payload),
    getLearningModel: (modelId: string) => get<LearningModel>(`${V1}/learning/models/${modelId}`),
    setLearningStatus: (modelId: string, status: string) =>
      post<LearningModel>(`${V1}/learning/models/${modelId}/status`, { status }),
    predictLearning: (payload: {
      model_type: OutcomeModelType | string;
      model_id?: string;
      site_id?: string;
      scope?: string;
      use_production?: boolean;
      features?: Record<string, unknown>;
      design?: BlastDesign;
    }) => post<LearningPredictResponse>(`${V1}/learning/predict`, payload),
    learningAlgorithms: () =>
      get<{ items: CalibrationAlgorithm[]; default: string }>(`${V1}/learning/algorithms`),
    listRegistryModels: (query?: { family?: string; status?: string; site_id?: string }) => {
      const params = new URLSearchParams();
      if (query?.family) params.set("family", query.family);
      if (query?.status) params.set("status", query.status);
      if (query?.site_id) params.set("site_id", query.site_id);
      const suffix = params.toString() ? `?${params.toString()}` : "";
      return get<{ items: RegistryRecord[]; auto_deployed: boolean }>(`${V1}/registry/models${suffix}`);
    },
    getRegistryModel: (family: string, modelId: string) =>
      get<RegistryRecord>(`${V1}/registry/models/${encodeURIComponent(family)}/${encodeURIComponent(modelId)}`),
    promoteRegistryModel: (family: string, modelId: string, payload: { to_status: string; confirm: boolean; note?: string }) =>
      post<RegistryRecord>(`${V1}/registry/models/${encodeURIComponent(family)}/${encodeURIComponent(modelId)}/promote`, payload),
    registryMeta: () =>
      get<{
        families: Array<{ name: string; label: string }>;
        statuses: Array<{ name: string; label: string; allowed_transitions: string[] }>;
        auto_deployed: boolean;
      }>(`${V1}/registry/meta`),
    checkDrift: (payload: { family: string; model_id: string; current_dataset_id: string }) =>
      post<DriftReport>(`${V1}/drift/check`, payload),
    listDriftReports: (query?: { family?: string; model_id?: string }) => {
      const params = new URLSearchParams();
      if (query?.family) params.set("family", query.family);
      if (query?.model_id) params.set("model_id", query.model_id);
      const suffix = params.toString() ? `?${params.toString()}` : "";
      return get<{ items: DriftReport[]; auto_deployed: boolean; auto_retrained: boolean }>(`${V1}/drift/reports${suffix}`);
    },
    getDriftReport: (reportId: string) =>
      get<DriftReport>(`${V1}/drift/reports/${encodeURIComponent(reportId)}`),
    listDriftAlerts: (query?: { family?: string; model_id?: string; acknowledged?: boolean }) => {
      const params = new URLSearchParams();
      if (query?.family) params.set("family", query.family);
      if (query?.model_id) params.set("model_id", query.model_id);
      if (query?.acknowledged != null) params.set("acknowledged", String(query.acknowledged));
      const suffix = params.toString() ? `?${params.toString()}` : "";
      return get<{ items: DriftAlert[]; auto_deployed: boolean; auto_retrained: boolean }>(`${V1}/drift/alerts${suffix}`);
    },
    acknowledgeDriftAlert: (alertId: string, payload: { confirm: boolean }) =>
      post<DriftAlert>(`${V1}/drift/alerts/${encodeURIComponent(alertId)}/acknowledge`, payload),
    driftMeta: () =>
      get<{
        kinds: Array<{ name: string; label: string }>;
        severities: Array<{ name: string; label: string }>;
        data_roles: Record<string, string>;
        auto_deployed: boolean;
        auto_retrained: boolean;
        action: string;
        next_step: string;
      }>(`${V1}/drift/meta`),
    listSpatialModels: (query?: { site_id?: string }) => {
      const params = new URLSearchParams();
      if (query?.site_id) params.set("site_id", query.site_id);
      const suffix = params.toString() ? `?${params.toString()}` : "";
      return get<{ items: SpatialSummary[]; modifies_design: boolean }>(`${V1}/spatial/models${suffix}`);
    },
    trainSpatial: (payload: {
      dataset_id: string;
      site_id?: string;
      algorithm?: string;
      neighbor_k?: number;
    }) => post<SpatialModel>(`${V1}/spatial/models`, payload),
    getSpatialModel: (modelId: string) =>
      get<SpatialModel>(`${V1}/spatial/models/${encodeURIComponent(modelId)}`),
    setSpatialStatus: (modelId: string, status: string) =>
      post<SpatialModel>(`${V1}/spatial/models/${encodeURIComponent(modelId)}/status`, { status }),
    predictSpatial: (payload: {
      design: BlastDesign;
      model_id?: string;
      site_id?: string;
      use_production?: boolean;
      block?: Record<string, number | null | undefined>;
      neighbor_k?: number;
    }) => post<SpatialOverlay>(`${V1}/spatial/predict`, payload),
    spatialMeta: () =>
      get<{
        metrics: Array<{ name: string; unit: string; label: string; role: string }>;
        map_metrics: Array<{ name: string; unit: string; label: string; role: string }>;
        data_roles: Record<string, string>;
        applied_as: string;
        modifies_design: boolean;
        role: string;
      }>(`${V1}/spatial/meta`),
    cost: (design: BlastDesign, scenarioId: CostScenarioId) =>
      post<DesignCostResult>(`${V1}/design/cost`, { design, scenario_id: scenarioId }),
    createScenario: (payload: {
      design: BlastDesign;
      name: string;
      params: DesignScenarioParams;
      persist?: boolean;
    }) => post<DesignScenario>(`${V1}/design/scenarios`, payload),
    listScenarios: (designId: string) =>
      get<{ items: DesignScenarioSummary[]; design_id: string; modifies_design: boolean }>(
        `${V1}/design/plans/${designId}/scenarios`,
      ),
    getScenario: (designId: string, scenarioId: string) =>
      get<DesignScenario>(`${V1}/design/plans/${designId}/scenarios/${scenarioId}`),
    compareScenarios: (payload: {
      design_id?: string;
      scenario_ids?: string[];
      include_baseline?: boolean;
      design?: BlastDesign;
      inline?: DesignScenario[];
    }) => post<ScenarioCompareResponse>(`${V1}/design/scenarios/compare`, payload),
    optimize: (payload: {
      design: BlastDesign;
      variables: Array<{
        name: string;
        values?: Array<number | string>;
        minimum?: number | null;
        maximum?: number | null;
        step?: number | null;
      }>;
      objectives?: string[];
      target_x50_mm?: number;
      max_candidates?: number;
      include_baseline?: boolean;
      persist?: boolean;
      persist_pareto_as_scenarios?: boolean;
      params?: DesignScenarioParams;
      constraints?: { max_ppv_mm_s?: number; max_oversize_pct?: number; max_cost_rub?: number };
    }) => post<OptimizationResult>(`${V1}/design/optimize`, payload),
    promoteOptimization: (payload: {
      design: BlastDesign;
      name: string;
      params: DesignScenarioParams;
      persist?: boolean;
    }) => post<DesignScenario>(`${V1}/design/optimize/promote`, payload),
    recommend: (payload: {
      design: BlastDesign;
      profile: string;
      variables?: Array<{
        name: string;
        values?: Array<number | string>;
        minimum?: number | null;
        maximum?: number | null;
        step?: number | null;
      }>;
      objectives?: string[];
      target_x50_mm?: number;
      max_candidates?: number;
      persist?: boolean;
      persist_as_scenario?: boolean;
      params?: DesignScenarioParams;
      constraints?: { max_ppv_mm_s?: number; max_oversize_pct?: number; max_cost_rub?: number };
    }) => post<DesignRecommendation>(`${V1}/design/recommend`, payload),
    promoteRecommendation: (payload: {
      design: BlastDesign;
      name: string;
      params: DesignScenarioParams;
      persist?: boolean;
    }) => post<DesignScenario>(`${V1}/design/recommend/promote`, payload),
    listRecommendations: (designId: string) =>
      get<{ items: Array<{ recommendation_id: string; profile: string; created_at: string }>; design_id: string; auto_applied: boolean }>(
        `${V1}/design/plans/${designId}/recommendations`,
      ),
    passportUrl: (designId: string) => `${V1}/design/plans/${designId}/passport.html`,
    passportRoles: () =>
      get<{
        roles: string[];
        labels_ru: Record<string, string>;
        labels_en: Record<string, string>;
        approved: boolean;
        auto_approved: boolean;
        disclaimer: string;
      }>(`${V1}/design/passport/roles`),
    buildPassport: (payload: {
      design: BlastDesign;
      lump_size_mm?: number;
      max_oversize_pct?: number;
      fragmentation_model?: string;
      include_predictions?: boolean;
      planned_cost?: {
        total_amount_rub?: number;
        cost_per_m3?: number;
        variable_total_rub?: number;
        labor_total_rub?: number;
        fixed_total_rub?: number;
        notes?: string;
      };
    }) => post<BlastPassport>(`${V1}/design/passport`, payload),
    renderPassportHtml: async (payload: {
      design: BlastDesign;
      lump_size_mm?: number;
      planned_cost?: { total_amount_rub?: number; cost_per_m3?: number };
    }) => {
      const response = await fetch(`${V1}/design/passport.html`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error("Не удалось собрать печатную форму паспорта.");
      return response.text();
    },
    getPlanPassport: (designId: string) => get<BlastPassport>(`${V1}/design/plans/${designId}/passport`),
    listPlans: () => get<{ items: DesignSummary[] }>(`${V1}/design/plans`),
    createPlan: (design: BlastDesign) => post<BlastDesign>(`${V1}/design/plans`, design),
    getPlan: (designId: string) => get<BlastDesign>(`${V1}/design/plans/${designId}`),
    savePlan: (designId: string, design: BlastDesign) =>
      put<BlastDesign>(`${V1}/design/plans/${designId}`, design),
    deletePlan: (designId: string) => del<void>(`${V1}/design/plans/${designId}`),
    lifecycleMeta: () => get<LifecycleMeta>(`${V1}/design/lifecycle/meta`),
    workstationMeta: () => get<WorkstationMeta>(`${V1}/design/workstation/meta`),
    getPlanLifecycle: (designId: string) =>
      get<LifecycleState>(`${V1}/design/plans/${designId}/lifecycle`),
    transitionPlan: (designId: string, payload: { to_status: string; confirm: boolean; note?: string }) =>
      post<LifecycleState>(`${V1}/design/plans/${designId}/lifecycle`, payload),
    forkPlan: (designId: string, name = "") =>
      post<BlastDesign>(`${V1}/design/plans/${designId}/fork`, { name }),
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

  // --- проект массового взрыва ---
  massBlast: {
    list: () => get<MassBlastProjectSummary[]>(`${V1}/design/mass-blast-projects`),
    create: (payload: MassBlastProjectInput) =>
      post<MassBlastProject>(`${V1}/design/mass-blast-projects`, payload),
    get: (id: string) => get<MassBlastProject>(`${V1}/design/mass-blast-projects/${id}`),
    save: (id: string, payload: MassBlastProjectInput) =>
      put<MassBlastProject>(`${V1}/design/mass-blast-projects/${id}`, payload),
    validate: (id: string, requireAttachments = false) =>
      post<MassBlastValidation>(`${V1}/design/mass-blast-projects/${id}/validate?require_attachments=${requireAttachments}`, {}),
    createRevision: (id: string, payload: { expected_version: number; require_attachments?: boolean }) =>
      post<MassBlastRevision>(`${V1}/design/mass-blast-projects/${id}/revisions`, payload),
    approveRevision: (revisionId: string, payload: { role_code: string; decision: "approved" | "rejected"; comment?: string }) =>
      post<{ id: string; role_code: string; decision: string }>(`${V1}/design/mass-blast-projects/revisions/${revisionId}/approvals`, payload),
    transition: (id: string, payload: { to_status: string; expected_version: number; confirm: boolean; note?: string }) =>
      post<MassBlastProject>(`${V1}/design/mass-blast-projects/${id}/lifecycle`, payload),
    documents: (id: string) => get<MassBlastDocument[]>(`${V1}/design/mass-blast-projects/${id}/documents`),
    attachments: (id: string) => get<MassBlastAttachment[]>(`${V1}/design/mass-blast-projects/${id}/attachments`),
    uploadAttachment: async (id: string, kind: string, file: File) => {
      const body = new FormData();
      body.append("kind", kind);
      body.append("file", file);
      const response = await fetch(`${V1}/design/mass-blast-projects/${id}/attachments`, { method: "POST", credentials: "include", body });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(typeof payload?.detail === "string" ? payload.detail : "Не удалось загрузить приложение.");
      }
      return response.json() as Promise<MassBlastAttachment>;
    },
    deleteAttachment: (id: string, attachmentId: string) => del<void>(`${V1}/design/mass-blast-projects/${id}/attachments/${attachmentId}`),
    attachmentUrl: (projectId: string, attachmentId: string) =>
      `${V1}/design/mass-blast-projects/${projectId}/attachments/${attachmentId}/download`,
    generateDocument: (id: string, payload: { revision_id: string; kind: "PROJECT" | "ORDER" | "SCHEDULE" | "PACKAGE"; format: "PDF" | "XLSX" | "ZIP" }) =>
      post<MassBlastDocument>(`${V1}/design/mass-blast-projects/${id}/documents`, payload),
    documentUrl: (documentId: string) => `${V1}/design/mass-blast-projects/documents/${documentId}/download`,
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
