import { Suspense, lazy, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { api } from "../../api/endpoints";
import { holeFromCollar, type Camera, type Vec2 } from "../../lib/geometry2d";
import { collarZFromSurfaces, surfaceElevation } from "../../lib/surfaces";
import type { BlastVariant, Explosive, User } from "../../types";
import {
  DEFAULT_CHARGE_RULES,
  DEFAULT_PATTERN_PARAMS,
  DEFAULT_PPV_REQUEST,
  DEFAULT_TIE_PARAMS,
  FRAGMENTATION_MAP_METRIC_LABELS,
  MAP_METRIC_LABELS,
  MAP_METRIC_UNITS,
  SPATIAL_MAP_METRIC_LABELS,
  MOVEMENT_MAP_METRIC_LABELS,
  emptyDesign,
  emptyReceptor,
  isFragmentationMapMetric,
  isSpatialMapMetric,
  isMovementMapMetric,
  networkTies,
  normalizeNetwork,
  type AnalyzeResponse,
  type ChargeRules,
  type CostScenarioId,
  type DesignCostResult,
  type DesignSummary,
  type EngineeringMaps,
  type FragmentationModelId,
  type FragmentationPredictResponse,
  type Hole,
  type HoleKind,
  type HoleLoad,
  type OverlayMetric,
  type PatternParams,
  type Point3,
  type PpvRequest,
  type ReceptorKind,
  type VibrationModel,
  type VibrationPredictResponse,
  type AsDrilledCompareResponse,
  type AsDrilledHole,
  type AsChargedCompareResponse,
  type AsChargedHole,
  type AsFiredCompareResponse,
  type AsFiredHole,
  type ExecutionCompareResponse,
  type BlastResult,
  type BlastResultCompareResponse,
  type DatasetSnapshot,
  type DatasetSummary,
  type SampleValidation,
  type CalibrationAlgorithm,
  type CalibrationModel,
  type CalibrationModelType,
  type CalibrationPredictResponse,
  type CalibrationSummary,
  type OutcomeModel,
  type OutcomeModelType,
  type OutcomePanelResponse,
  type OutcomePredictResponse,
  type OutcomeSummary,
  type DesignScenario,
  type DesignScenarioSummary,
  type DesignRecommendation,
  type OptimizationCandidate,
  type OptimizationResult,
  type ScenarioCompareResponse,
  type SchemeType,
  type SurfaceConnector,
  type SurfaceKind,
  type TieParams,
  type LearningModel,
  type LearningPredictResponse,
  type LearningSummary,
  type RegistryFamily,
  type RegistryRecord,
  type DriftAlert,
  type DriftReport,
  type SpatialModel,
  type SpatialOverlay,
  type SpatialSummary,
  type MovementPredictResponse,
  type BlastPassport,
  type DesignLifecycleStatus,
} from "../../types/design";
import { emptyHoleGeology } from "../../types/design";
import {
  canEditDesigned,
  canEditExecution,
  canEditMeasured,
  canEditMetadata,
  freezeMessage,
  isRecordFrozen,
  overlayRole,
  statusLabel,
  WORKFLOW_STAGES,
  type WorkflowStageId,
} from "../../lib/lifecycle";
import { RoleBadge } from "./RoleBadge";
import { LifecyclePanel } from "./LifecyclePanel";
import { WorkflowNav } from "./WorkflowNav";
import { ChargePanel } from "./ChargePanel";
import { designReducer, initDesignState } from "./designReducer";
import { FragmentationPanel } from "./FragmentationPanel";
import { exampleLayeredDomains, GeologyPanel } from "./GeologyPanel";
import { HoleInspector } from "./HoleInspector";
import { layersToMapLegend } from "./MapLegend";
import { PatternPanel } from "./PatternPanel";
import { PlanCanvas, type PlanMeasureState } from "./PlanCanvas";
import { StageInspector } from "./StageInspector";
import { VisibilityPanel } from "./VisibilityPanel";
import { MapStatusBar } from "./MapStatusBar";
import { HoleContextMenu, type HoleContextMenuState } from "./HoleContextMenu";
import { CommandPalette, buildCameraCommands, buildPresetCommands, type DesignCommand } from "./CommandPalette";
import { computeAllHoleHealth, healthColor, summarizeHealth } from "./holeHealth";
import {
  applyPresetToState,
  applyViewPreset,
  defaultDesignViewState,
  resetLayersToPreset,
  stageDefaultPreset,
  type DesignViewState,
  type LayerId,
  type ViewPresetId,
} from "./viewPresets";
import {
  holeSourceLabel,
  isCrsUnconfirmed,
  statusesForDocument,
  volumeSourceLabel,
} from "./workflowStatus";
import { PlansPanel } from "./PlansPanel";
import { SectionView } from "./SectionView";
import { SummaryPanel } from "./SummaryPanel";
import { SurfacePanel } from "./SurfacePanel";
import { TiePanel } from "./TiePanel";
import { TimingPanel } from "./TimingPanel";
import { VibrationPanel } from "./VibrationPanel";
import { AsDrilledPanel } from "./AsDrilledPanel";
import { AsChargedPanel } from "./AsChargedPanel";
import { AsFiredPanel } from "./AsFiredPanel";
import { ExecutionComparePanel } from "./ExecutionComparePanel";
import { PostBlastPanel } from "./PostBlastPanel";
import { DatasetPanel } from "./DatasetPanel";
import { CalibrationPanel } from "./CalibrationPanel";
import { OutcomePanel } from "./OutcomePanel";
import { ScenarioPanel } from "./ScenarioPanel";
import { OptimizationPanel, type OptimizationVariableDraft } from "./OptimizationPanel";
import { RecommendationPanel } from "./RecommendationPanel";
import { LearningPanel } from "./LearningPanel";
import { RegistryPanel } from "./RegistryPanel";
import { DriftPanel } from "./DriftPanel";
import { SpatialPanel } from "./SpatialPanel";
import { MovementPanel } from "./MovementPanel";
import { PassportPanel } from "./PassportPanel";
import { MassBlastPanel } from "./MassBlastPanel";

// three.js — крупная зависимость, нужная только вкладке «3D»: грузим лениво,
// чтобы не раздувать основной бандл для остальных режимов редактора.
const Scene3D = lazy(() => import("./Scene3D").then((m) => ({ default: m.Scene3D })));

let manualHoleCounter = 0;

async function readSurveyFile(file: File): Promise<string> {
  const bytes = await file.arrayBuffer();
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return new TextDecoder("windows-1251").decode(bytes);
  }
}

export function DesignPage({
  user,
  incomingVariant,
  onVariantConsumed,
}: {
  user: User;
  incomingVariant: BlastVariant | null;
  onVariantConsumed: () => void;
}) {
  const [state, dispatch] = useReducer(designReducer, emptyDesign(), initDesignState);
  const document = state.present;

  const [mode, setMode] = useState<"contour" | "holes" | "charge" | "tie" | "timing">("contour");
  const [viewMode, setViewMode] = useState<"plan" | "3d" | "section">("plan");
  const [workflowStage, setWorkflowStage] = useState<WorkflowStageId>("survey");
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [inspectHoleId, setInspectHoleId] = useState<string | null>(null);
  const [designView, setDesignView] = useState<DesignViewState>(() => defaultDesignViewState());
  const [visibilityCollapsed, setVisibilityCollapsed] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [holeMenu, setHoleMenu] = useState<HoleContextMenuState>(null);
  const [measureState, setMeasureState] = useState<PlanMeasureState>({ points: [], holeIds: [], result: null });
  const [mapCursor, setMapCursor] = useState<Vec2 | null>(null);
  const [zoomRequest, setZoomRequest] = useState<{ kind: "fit" | "selection"; tick: number } | null>(null);
  const [toolRequest, setToolRequest] = useState<{ tool: "measure"; tick: number } | null>(null);
  const [lifecycleConfirm, setLifecycleConfirm] = useState(false);
  const [lifecycleNote, setLifecycleNote] = useState("");
  const designedLocked = !canEditDesigned(document.lifecycle_status);
  const executionLocked = !canEditExecution(document.lifecycle_status);
  const measuredLocked = !canEditMeasured(document.lifecycle_status);
  const metadataLocked = !canEditMetadata(document.lifecycle_status);
  const recordFrozen = isRecordFrozen(document.lifecycle_status);
  const [camera, setCamera] = useState<Camera>({ x: 0, y: 0, scale: 6 });
  // Флаг «геометрию подменили целиком»: план вписывается в окно заново. Именно
  // флаг, а не счётчик, — запрос переживает уход на вкладку «3D» и обратно
  // (холст там размонтируется), но не срабатывает повторно.
  const [pendingFit, setPendingFit] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [patternParams, setPatternParams] = useState<PatternParams>(DEFAULT_PATTERN_PARAMS);
  const [blockVolumeM3, setBlockVolumeM3] = useState<number | null>(null);
  const [plans, setPlans] = useState<DesignSummary[]>([]);
  const [patternBusy, setPatternBusy] = useState(false);
  const [surfaceBusy, setSurfaceBusy] = useState(false);
  const [geologyBusy, setGeologyBusy] = useState(false);
  const [selectedDomainId, setSelectedDomainId] = useState<string | null>(null);
  const [drawingDomain, setDrawingDomain] = useState(false);
  const [saveBusy, setSaveBusy] = useState(false);
  const [error, setError] = useState("");

  const [explosives, setExplosives] = useState<Explosive[]>([]);
  const [explosiveKey, setExplosiveKey] = useState("");
  const [chargeRules, setChargeRules] = useState<ChargeRules>(DEFAULT_CHARGE_RULES);
  const [chargeBusy, setChargeBusy] = useState(false);
  const [selectedRow, setSelectedRow] = useState<number | null>(null);

  const [tieScheme, setTieScheme] = useState<SchemeType>("row");
  const [tieParams, setTieParams] = useState<TieParams>(DEFAULT_TIE_PARAMS);
  const [tieBusy, setTieBusy] = useState(false);
  const [pendingTieFromId, setPendingTieFromId] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [analyzeBusy, setAnalyzeBusy] = useState(false);
  const [isolineStepMs, setIsolineStepMs] = useState(25);
  const [showIsolines, setShowIsolines] = useState(true);
  const [micWindowMs, setMicWindowMs] = useState(8);
  const [ppv, setPpv] = useState<PpvRequest>(DEFAULT_PPV_REQUEST);
  const [placingReceptor, setPlacingReceptor] = useState(false);
  const [selectedReceptorId, setSelectedReceptorId] = useState<string | null>(null);
  const [vibResult, setVibResult] = useState<VibrationPredictResponse | null>(null);
  const [vibBusy, setVibBusy] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [currentMs, setCurrentMs] = useState(0);
  const animationFrameRef = useRef<number | null>(null);

  const [scenarioId, setScenarioId] = useState<CostScenarioId>("drill_blast");
  const [costResult, setCostResult] = useState<DesignCostResult | null>(null);
  const [costBusy, setCostBusy] = useState(false);
  const [insertKind, setInsertKind] = useState<HoleKind>("production");
  const [maps, setMaps] = useState<EngineeringMaps | null>(null);
  const [mapMetric, setMapMetric] = useState<OverlayMetric | "">("");
  const [fragModel, setFragModel] = useState<FragmentationModelId>("kuzram");
  const [lumpSizeMm, setLumpSizeMm] = useState(400);
  const [fragResult, setFragResult] = useState<FragmentationPredictResponse | null>(null);
  const [fragBusy, setFragBusy] = useState(false);
  const [asDrilledBusy, setAsDrilledBusy] = useState(false);
  const [asDrilledResult, setAsDrilledResult] = useState<AsDrilledCompareResponse | null>(null);
  const [showAsDrilled, setShowAsDrilled] = useState(true);
  const [asChargedBusy, setAsChargedBusy] = useState(false);
  const [asChargedResult, setAsChargedResult] = useState<AsChargedCompareResponse | null>(null);
  const [asFiredBusy, setAsFiredBusy] = useState(false);
  const [asFiredResult, setAsFiredResult] = useState<AsFiredCompareResponse | null>(null);
  const [executionBusy, setExecutionBusy] = useState(false);
  const [executionResult, setExecutionResult] = useState<ExecutionCompareResponse | null>(null);
  const [blastResultBusy, setBlastResultBusy] = useState(false);
  const [blastResultCompare, setBlastResultCompare] = useState<BlastResultCompareResponse | null>(null);
  const [datasetBusy, setDatasetBusy] = useState(false);
  const [datasetSiteId, setDatasetSiteId] = useState("");
  const [datasetName, setDatasetName] = useState("");
  const [datasetItems, setDatasetItems] = useState<DatasetSummary[]>([]);
  const [datasetSelected, setDatasetSelected] = useState<DatasetSnapshot | null>(null);
  const [datasetPreview, setDatasetPreview] = useState<SampleValidation | null>(null);
  const [calibrationBusy, setCalibrationBusy] = useState(false);
  const [calibrationType, setCalibrationType] = useState<CalibrationModelType>("kuzram_residual");
  const [calibrationAlgorithm, setCalibrationAlgorithm] = useState("random_forest");
  const [calibrationAlgorithms, setCalibrationAlgorithms] = useState<CalibrationAlgorithm[]>([]);
  const [calibrationItems, setCalibrationItems] = useState<CalibrationSummary[]>([]);
  const [calibrationSelected, setCalibrationSelected] = useState<CalibrationModel | null>(null);
  const [calibrationOverlay, setCalibrationOverlay] = useState<CalibrationPredictResponse | null>(null);
  const [outcomeBusy, setOutcomeBusy] = useState(false);
  const [outcomeType, setOutcomeType] = useState<OutcomeModelType>("fragmentation");
  const [outcomeAlgorithm, setOutcomeAlgorithm] = useState("random_forest");
  const [outcomeAlgorithms, setOutcomeAlgorithms] = useState<CalibrationAlgorithm[]>([]);
  const [outcomeItems, setOutcomeItems] = useState<OutcomeSummary[]>([]);
  const [outcomeSelected, setOutcomeSelected] = useState<OutcomeModel | null>(null);
  const [outcomeOverlay, setOutcomeOverlay] = useState<OutcomePredictResponse | null>(null);
  const [outcomePanel, setOutcomePanel] = useState<OutcomePanelResponse | null>(null);
  const [scenarioBusy, setScenarioBusy] = useState(false);
  const [scenarioName, setScenarioName] = useState("Сценарий A");
  const [scenarioDiameterMm, setScenarioDiameterMm] = useState(165);
  const [scenarioSpacingM, setScenarioSpacingM] = useState(6);
  const [scenarioBurdenM, setScenarioBurdenM] = useState(5);
  const [scenarioPowderFactor, setScenarioPowderFactor] = useState(0.65);
  const [scenarioUseOverlays, setScenarioUseOverlays] = useState(false);
  const [scenarioItems, setScenarioItems] = useState<DesignScenarioSummary[]>([]);
  const [scenarioInline, setScenarioInline] = useState<DesignScenario[]>([]);
  const [scenarioCompare, setScenarioCompare] = useState<ScenarioCompareResponse | null>(null);
  const [optBusy, setOptBusy] = useState(false);
  const [optResult, setOptResult] = useState<OptimizationResult | null>(null);
  const [optTargetX50Mm, setOptTargetX50Mm] = useState(200);
  const [optMaxCandidates, setOptMaxCandidates] = useState(24);
  const [optObjectives, setOptObjectives] = useState<string[]>([
    "cost", "oversize", "drilling_metres", "ppv", "target_x50",
  ]);
  const [optVariables, setOptVariables] = useState<OptimizationVariableDraft[]>([
    { name: "diameter_mm", label: "Диаметр", unit: "мм", enabled: true, valuesText: "152, 165" },
    { name: "burden_b_m", label: "ЛНС", unit: "м", enabled: true, valuesText: "3.5, 4.0, 4.5" },
    { name: "spacing_a_m", label: "Шаг", unit: "м", enabled: true, valuesText: "4.5, 5.0, 5.5" },
    { name: "subdrill_m", label: "Перебур", unit: "м", enabled: false, valuesText: "0.8, 1.0, 1.2" },
    { name: "stemming_m", label: "Забойка", unit: "м", enabled: false, valuesText: "2.5, 3.0, 3.5" },
    { name: "explosive_key", label: "Тип ВВ", unit: "", enabled: false, valuesText: "ПВВ Гранулит-РП, ПЭВВ ЭВЕРСИН Э-100" },
    { name: "inclination_deg", label: "Наклон", unit: "°", enabled: false, valuesText: "0, 10" },
    { name: "delay_interval_ms", label: "Замедление", unit: "мс", enabled: false, valuesText: "17, 25, 42" },
  ]);
  const [recBusy, setRecBusy] = useState(false);
  const [recResult, setRecResult] = useState<DesignRecommendation | null>(null);
  const [recProfile, setRecProfile] = useState("BALANCED");
  const [recUseOverlays, setRecUseOverlays] = useState(false);
  const [learningBusy, setLearningBusy] = useState(false);
  const [learningType, setLearningType] = useState<OutcomeModelType>("fragmentation");
  const [learningAlgorithm, setLearningAlgorithm] = useState("random_forest");
  const [learningAlgorithms, setLearningAlgorithms] = useState<CalibrationAlgorithm[]>([]);
  const [learningItems, setLearningItems] = useState<LearningSummary[]>([]);
  const [learningSelected, setLearningSelected] = useState<LearningModel | null>(null);
  const [learningOverlay, setLearningOverlay] = useState<LearningPredictResponse | null>(null);
  const [registryBusy, setRegistryBusy] = useState(false);
  const [registryFamily, setRegistryFamily] = useState<RegistryFamily | "">("");
  const [registryItems, setRegistryItems] = useState<RegistryRecord[]>([]);
  const [registrySelected, setRegistrySelected] = useState<RegistryRecord | null>(null);
  const [driftBusy, setDriftBusy] = useState(false);
  const [driftFamily, setDriftFamily] = useState("");
  const [driftModelId, setDriftModelId] = useState("");
  const [driftDatasetId, setDriftDatasetId] = useState("");
  const [driftReport, setDriftReport] = useState<DriftReport | null>(null);
  const [driftAlerts, setDriftAlerts] = useState<DriftAlert[]>([]);
  const [spatialBusy, setSpatialBusy] = useState(false);
  const [spatialItems, setSpatialItems] = useState<SpatialSummary[]>([]);
  const [spatialSelected, setSpatialSelected] = useState<SpatialModel | null>(null);
  const [spatialOverlay, setSpatialOverlay] = useState<SpatialOverlay | null>(null);
  const [movementResult, setMovementResult] = useState<MovementPredictResponse | null>(null);
  const [passportResult, setPassportResult] = useState<BlastPassport | null>(null);
  const [passportBusy, setPassportBusy] = useState(false);
  const [movementBusy, setMovementBusy] = useState(false);
  const [showMovementVectors, setShowMovementVectors] = useState(true);

  const maxAnimationMs = useMemo(() => {
    const values = analysis ? Object.values(analysis.times_ms) : [];
    return values.length ? Math.max(...values) : 0;
  }, [analysis]);

  useEffect(() => {
    if (!playing || !analysis) return;
    let lastReal = performance.now();
    const rate = maxAnimationMs > 0 ? maxAnimationMs / 6000 : 1; // ~6с на всю анимацию
    function tick(now: number) {
      const deltaReal = now - lastReal;
      lastReal = now;
      setCurrentMs((prev) => {
        const next = prev + deltaReal * rate;
        if (next >= maxAnimationMs) {
          setPlaying(false);
          return maxAnimationMs;
        }
        return next;
      });
      animationFrameRef.current = requestAnimationFrame(tick);
    }
    animationFrameRef.current = requestAnimationFrame(tick);
    return () => {
      if (animationFrameRef.current !== null) cancelAnimationFrame(animationFrameRef.current);
    };
  }, [playing, analysis, maxAnimationMs]);

  useEffect(() => { refreshPlans(); refreshDatasets(); refreshCalibrations(); refreshOutcomes(); refreshLearning(); refreshDriftAlerts(); refreshSpatial(); }, []);
  useEffect(() => { refreshRegistry(); }, [registryFamily]);

  useEffect(() => {
    api.explosives()
      .then((data) => {
        setExplosives(data.items);
        setExplosiveKey((prev) => prev || data.default_key);
      })
      .catch(() => {
        // Справочник ВВ не критичен для геометрии сетки — молча пропускаем.
      });
  }, []);

  const loadsById = useMemo(() => {
    const map: Record<string, HoleLoad> = {};
    for (const load of document.loads) map[load.hole_id] = load;
    return map;
  }, [document.loads]);

  const mapOverlay = useMemo(() => {
    if (!mapMetric) return { values: undefined as Record<string, number> | undefined, range: null as { min: number; max: number } | null };
    if (isFragmentationMapMetric(mapMetric)) {
      if (!fragResult?.maps) return { values: undefined, range: null };
      const values: Record<string, number> = {};
      for (const sample of fragResult.maps.holes) {
        const raw = sample[mapMetric];
        if (raw !== null && raw !== undefined) values[sample.hole_id] = raw;
      }
      const stat = fragResult.maps.stats[mapMetric];
      return { values, range: stat ? { min: stat.min, max: stat.max } : null };
    }
    if (isSpatialMapMetric(mapMetric)) {
      if (!spatialOverlay?.maps) return { values: undefined, range: null };
      const key = mapMetric.replace(/^ml_/, "");
      const values: Record<string, number> = {};
      for (const sample of spatialOverlay.maps.holes) {
        const raw = sample[key];
        if (typeof raw === "number") values[String(sample.hole_id)] = raw;
      }
      const stat = spatialOverlay.maps.stats[key];
      return { values, range: stat ? { min: stat.min, max: stat.max } : null };
    }
    if (isMovementMapMetric(mapMetric)) {
      if (!movementResult?.maps) return { values: undefined, range: null };
      const values: Record<string, number> = {};
      for (const sample of movementResult.maps.holes) {
        const raw = sample[mapMetric];
        if (raw !== null && raw !== undefined) values[sample.hole_id] = raw;
      }
      const stat = movementResult.maps.stats[mapMetric];
      return { values, range: stat ? { min: stat.min, max: stat.max } : null };
    }
    if (!maps) return { values: undefined, range: null };
    const values: Record<string, number> = {};
    for (const sample of maps.holes) {
      const raw = sample[mapMetric];
      if (raw !== null && raw !== undefined) values[sample.hole_id] = raw;
    }
    const stat = maps.stats[mapMetric];
    return { values, range: stat ? { min: stat.min, max: stat.max } : null };
  }, [mapMetric, maps, fragResult, spatialOverlay, movementResult]);

  useEffect(() => {
    if (!incomingVariant) return;
    setPatternParams((prev) => ({
      ...prev,
      spacing_a_m: incomingVariant.grid_a_m,
      burden_b_m: incomingVariant.grid_b_m,
      diameter_mm: incomingVariant.crown_mm,
    }));
    onVariantConsumed();
  }, [incomingVariant]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      const typing = target.tagName === "INPUT" || target.tagName === "SELECT" || target.tagName === "TEXTAREA";
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !typing) {
        e.preventDefault();
        dispatch({ type: e.shiftKey ? "REDO" : "UNDO" });
        return;
      }
      // В режиме контура Delete относится к вершинам блока (их обрабатывает
      // сам холст), и выделенные ранее скважины трогать нельзя.
      if ((e.key === "Delete" || e.key === "Backspace") && !typing && mode !== "contour" && selected.size > 0) {
        e.preventDefault();
        deleteSelected();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  function rejectLocked(kind: "designed" | "execution" | "measured"): boolean {
    const allowed = kind === "designed" ? !designedLocked : kind === "execution" ? !executionLocked : !measuredLocked;
    if (allowed) return false;
    setError(freezeMessage(document.lifecycle_status, kind));
    return true;
  }

  function selectStage(next: WorkflowStageId) {
    if (next === workflowStage) {
      setInspectorOpen((open) => !open);
      return;
    }
    setWorkflowStage(next);
    setInspectorOpen(true);
    if (!designView.presetLocked) {
      const preset = stageDefaultPreset(next);
      setDesignView((prev) => applyPresetToState(prev, preset, false));
    }
    if (next === "survey" || next === "geology") setMode("contour");
    else if (next === "pattern") setMode("holes");
    else if (next === "charge") setMode("charge");
    else if (next === "timing") setMode("timing");
    else setMode("holes");
  }

  function setViewPreset(preset: ViewPresetId) {
    setDesignView(applyViewPreset(preset, true));
  }

  function zoomToHole(holeId: string) {
    setSelected(new Set([holeId]));
    setZoomRequest({ kind: "selection", tick: Date.now() });
    const hole = document.holes.find((h) => h.id === holeId);
    if (hole && viewMode === "section") setSelectedRow(hole.row);
  }

  function copyHoleParams(holeId: string) {
    const hole = document.holes.find((h) => h.id === holeId);
    if (!hole) return;
    const payload = JSON.stringify({
      diameter_mm: hole.diameter_mm,
      subdrill_m: hole.subdrill_m,
      kind: hole.kind,
      row: hole.row,
      col: hole.col,
    });
    void navigator.clipboard?.writeText(payload);
  }

  function toggleStarterForHole(holeId: string) {
    if (rejectLocked("designed")) return;
    const network = normalizeNetwork(document.network);
    const starterItems = network.starter_items.length
      ? [...network.starter_items]
      : network.starters.map((id) => ({ id: `st-${id}`, hole_id: id, delay_ms: 0, kind: "starter" }));
    const index = starterItems.findIndex((item) => item.hole_id === holeId);
    if (index >= 0) starterItems.splice(index, 1);
    else starterItems.push({ id: `st-${holeId}`, hole_id: holeId, delay_ms: 0, kind: "starter" });
    dispatch({
      type: "SET_NETWORK",
      network: {
        ...network,
        starter_items: starterItems,
        starters: starterItems.map((item) => item.hole_id),
      },
    });
  }

  async function refreshPlans() {
    try {
      const result = await api.design.listPlans();
      setPlans(result.items);
    } catch {
      // Список паспортов не критичен для работы редактора — молча пропускаем.
    }
  }

  async function generatePattern() {
    if (rejectLocked("designed")) return;
    if (document.contour.vertices.length < 3) {
      setError("Нарисуйте контур блока (не менее трёх точек) перед раскладкой сетки.");
      return;
    }
    setPatternBusy(true);
    setError("");
    try {
      const result = await api.design.pattern(document.contour, patternParams, document.holes, document.surfaces, document.domains);
      dispatch({ type: "SET_HOLES", holes: result.holes });
      setBlockVolumeM3(result.block_volume_m3);
      setFragResult(null);
      setAsDrilledResult(null);
      setAsChargedResult(null);
      setAsFiredResult(null);
      setExecutionResult(null);
      setBlastResultCompare(null);
      await refreshMaps({ ...document, holes: result.holes, pattern_params: patternParams as unknown as Record<string, unknown> });
      setSelected(new Set());
      setPendingFit(true);
      setChargeRules((prev) => ({ ...prev, grid_a_m: patternParams.spacing_a_m, grid_b_m: patternParams.burden_b_m }));
      if (document.domains.length) {
        await interceptHoles(result.holes, document.domains, document.water_table_z_m);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось построить сетку.");
    } finally {
      setPatternBusy(false);
    }
  }

  function onContourChange(vertices: Point3[], freeFaces?: number[][], coalesce?: boolean) {
    if (rejectLocked("designed")) return;
    const draped = vertices.map((v) => ({
      ...v,
      z: collarZFromSurfaces(document.surfaces, v.x, v.y, document.contour.bench.crest_z_m),
    }));
    dispatch({ type: "SET_CONTOUR_VERTICES", vertices: draped, free_faces: freeFaces, coalesce });
  }

  async function importSurface(kind: SurfaceKind, file: File) {
    if (rejectLocked("designed")) return;
    setSurfaceBusy(true);
    setError("");
    try {
      const content = await readSurveyFile(file);
      const result = await api.design.importSurface({
        content,
        filename: file.name,
        kind,
        coordinate_system: document.coordinate_system,
      });
      dispatch({ type: "SET_SURFACE", surface: result.surface });
      if (kind === "top" && result.stats.z_max !== null) {
        dispatch({ type: "SET_BENCH", bench: { crest_z_m: result.stats.z_max } });
      }
      if (kind === "floor" && result.stats.z_min !== null) {
        dispatch({ type: "SET_BENCH", bench: { toe_z_m: result.stats.z_min } });
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось импортировать съёмку.");
    } finally {
      setSurfaceBusy(false);
    }
  }

  async function importBenchDxf(file: File) {
    if (rejectLocked("designed")) return;
    if (document.holes.length && !window.confirm("Импорт заменит контур и очистит скважины, заряды и сеть. Продолжить?")) return;
    setSurfaceBusy(true);
    setError("");
    try {
      const result = await api.design.importBenchDxf({
        content: await readSurveyFile(file), filename: file.name, coordinate_system: document.coordinate_system,
      });
      dispatch({ type: "SET_BENCH", bench: result.contour.bench });
      if (result.surfaces.top) dispatch({ type: "SET_SURFACE", surface: result.surfaces.top });
      if (result.surfaces.floor) dispatch({ type: "SET_SURFACE", surface: result.surfaces.floor });
      if (result.surfaces.face) dispatch({ type: "SET_SURFACE", surface: result.surfaces.face });
      dispatch({ type: "SET_CONTOUR_VERTICES", vertices: result.contour.vertices.map((point) => ({ ...point, z: result.crest_z_m })), free_faces: [] });
      dispatch({ type: "SET_HOLES", holes: [] });
      setSelected(new Set());
      setPendingFit(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось импортировать DXF-каркас блока.");
    } finally {
      setSurfaceBusy(false);
    }
  }

  function onToggleFreeFace(edgeIndex: number) {
    if (rejectLocked("designed")) return;
    dispatch({ type: "TOGGLE_FREE_FACE", edgeIndex });
  }

  function onMoveHoles(ids: string[], dx: number, dy: number) {
    if (rejectLocked("designed")) return;
    dispatch({ type: "MOVE_HOLES", ids, dx, dy });
  }

  function onUpdateHole(id: string, patch: Partial<Hole>) {
    if (rejectLocked("designed")) return;
    dispatch({ type: "UPDATE_HOLE", id, patch });
  }

  async function refreshMaps(design = document) {
    if (!design.holes.length) {
      setMaps(null);
      return;
    }
    try {
      const result = await api.design.maps({
        ...design,
        pattern_params: patternParams as unknown as Record<string, unknown>,
        charge_rules: chargeRules as unknown as Record<string, unknown>,
        explosive_key: explosiveKey,
      });
      setMaps(result);
    } catch {
      setMaps(null);
    }
  }

  async function predictMovement() {
    if (!document.holes.length) {
      setError("Сначала постройте сетку скважин.");
      return;
    }
    setMovementBusy(true);
    setError("");
    try {
      const result = await api.design.movement({
        design: {
          ...document,
          pattern_params: patternParams as unknown as Record<string, unknown>,
          charge_rules: chargeRules as unknown as Record<string, unknown>,
          explosive_key: explosiveKey,
        },
      });
      setMovementResult(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось оценить развал и вывал.");
      setMovementResult(null);
    } finally {
      setMovementBusy(false);
    }
  }

  async function predictFragmentation() {
    if (!document.holes.length) {
      setError("Сначала постройте сетку скважин.");
      return;
    }
    const explosive = explosives.find((item) => item.key === explosiveKey);
    setFragBusy(true);
    setError("");
    try {
      const result = await api.design.fragmentation({
        design: {
          ...document,
          pattern_params: patternParams as unknown as Record<string, unknown>,
          charge_rules: chargeRules as unknown as Record<string, unknown>,
          explosive_key: explosiveKey,
        },
        model: fragModel,
        lump_size_mm: lumpSizeMm,
        max_oversize_pct: 5,
        explosive: explosive
          ? { name: explosive.name, density_t_m3: explosive.density_t_m3, power_mj_kg: explosive.power_mj_kg }
          : undefined,
        explosives: explosives.map((item) => ({
          name: item.name,
          density_t_m3: item.density_t_m3,
          power_mj_kg: item.power_mj_kg,
        })),
        hole_oversize_coeff: chargeRules.hole_oversize_coeff,
      });
      setFragResult(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось рассчитать дробление.");
      setFragResult(null);
    } finally {
      setFragBusy(false);
    }
  }

  async function onAddHole(world: Vec2) {
    if (rejectLocked("designed")) return;
    const x = Math.round(world.x * 100) / 100;
    const y = Math.round(world.y * 100) / 100;
    try {
      const result = await api.design.insertHole({
        contour: document.contour,
        x,
        y,
        params: {
          kind: insertKind,
          diameter_mm: patternParams.diameter_mm,
          subdrill_m: patternParams.subdrill_m,
          angle_deg: patternParams.angle_deg,
          azimuth_deg: patternParams.azimuth_deg,
        },
        existing_holes: document.holes,
        surfaces: document.surfaces,
      });
      dispatch({ type: "ADD_HOLE", hole: { ...emptyHoleGeology(), ...result.hole } });
      return;
    } catch {
      // Local fallback keeps the editor usable if the insert endpoint is unavailable.
    }
    manualHoleCounter += 1;
    const z = collarZFromSurfaces(document.surfaces, x, y, document.contour.bench.crest_z_m);
    const collar: Point3 = { x, y, z };
    const floorZ = surfaceElevation(document.surfaces.floor, x, y) ?? document.contour.bench.toe_z_m;
    const depth = z - floorZ + patternParams.subdrill_m;
    const toe = holeFromCollar(collar, depth, patternParams.angle_deg, patternParams.azimuth_deg);
    const hole: Hole = {
      id: `M-${manualHoleCounter}`,
      row: -1000,
      col: manualHoleCounter,
      collar,
      toe,
      diameter_mm: patternParams.diameter_mm,
      subdrill_m: patternParams.subdrill_m,
      kind: insertKind,
      source: "manual",
      enabled: true,
      ...emptyHoleGeology(),
    };
    dispatch({ type: "ADD_HOLE", hole });
  }

  function deleteHoles(ids: string[]) {
    if (!ids.length) return;
    dispatch({ type: "DELETE_HOLES", ids });
    setSelected((prev) => {
      const next = new Set(prev);
      for (const id of ids) next.delete(id);
      return next;
    });
  }

  function setHolesEnabled(ids: string[], enabled: boolean) {
    dispatch({ type: "SET_HOLES_ENABLED", ids, enabled });
  }

  function deleteSelected() {
    if (rejectLocked("designed")) return;
    deleteHoles(Array.from(selected));
  }

  function onSelectHole3D(id: string, additive: boolean) {
    setSelected((prev) => {
      if (additive) {
        const next = new Set(prev);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      }
      return new Set([id]);
    });
  }

  async function calculateCharge() {
    if (rejectLocked("designed")) return;
    if (!document.holes.length) {
      setError("Сначала постройте сетку скважин.");
      return;
    }
    const explosive = explosives.find((item) => item.key === explosiveKey);
    if (!explosive) {
      setError("Выберите взрывчатое вещество.");
      return;
    }
    setChargeBusy(true);
    setError("");
    try {
      const catalog = explosives.map((item) => ({
        name: item.name,
        density_t_m3: item.density_t_m3,
        power_mj_kg: item.power_mj_kg,
      }));
      const result = await api.design.charge(document.holes, chargeRules, explosive, {
        contour: document.contour,
        explosives: catalog,
      });
      dispatch({ type: "SET_LOADS", loads: result.loads });
      setFragResult(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось рассчитать заряжание.");
    } finally {
      setChargeBusy(false);
    }
  }

  function addManualTie(fromId: string, toId: string) {
    if (rejectLocked("designed")) return;
    const network = normalizeNetwork(document.network);
    const delay = tieParams.interval_ms || 25;
    const kind = network.system === "detcord" ? "ds_relay" : network.system === "electronic" ? "electronic" : "surface_nsi";
    const id = `sc-${fromId}-${toId}`;
    const nextTies = networkTies(network).filter((item) => !(item.from_hole === fromId && item.to_hole === toId));
    nextTies.push({ id, from_hole: fromId, to_hole: toId, delay_ms: delay, kind, product: "" });
    const starterItems = network.starter_items.length ? [...network.starter_items] : network.starters.map((holeId) => ({ id: `st-${holeId}`, hole_id: holeId, delay_ms: 0, kind: "starter" }));
    if (!starterItems.some((item) => item.hole_id === fromId) && !nextTies.some((item) => item.to_hole === fromId)) {
      starterItems.push({ id: `st-${fromId}`, hole_id: fromId, delay_ms: 0, kind: "starter" });
    }
    dispatch({
      type: "SET_NETWORK",
      network: {
        ...network,
        surface_connectors: nextTies,
        connectors: nextTies.map((item) => ({ from_hole: item.from_hole, to_hole: item.to_hole, delay_ms: item.delay_ms, kind: item.kind })),
        starter_items: starterItems,
        starters: starterItems.map((item) => item.hole_id),
      },
    });
    setPendingTieFromId(null);
    setAnalysis(null);
  }

  function updateManualTie(tie: SurfaceConnector, delayMs: number) {
    if (rejectLocked("designed")) return;
    const network = normalizeNetwork(document.network);
    const nextTies = networkTies(network).map((item) => (item.id === tie.id ? { ...item, delay_ms: delayMs } : item));
    dispatch({
      type: "SET_NETWORK",
      network: {
        ...network,
        surface_connectors: nextTies,
        connectors: nextTies.map((item) => ({ from_hole: item.from_hole, to_hole: item.to_hole, delay_ms: item.delay_ms, kind: item.kind })),
      },
    });
    setAnalysis(null);
  }

  function removeManualTie(connectorId: string) {
    if (rejectLocked("designed")) return;
    const network = normalizeNetwork(document.network);
    const nextTies = networkTies(network).filter((item) => item.id !== connectorId);
    dispatch({
      type: "SET_NETWORK",
      network: {
        ...network,
        surface_connectors: nextTies,
        connectors: nextTies.map((item) => ({ from_hole: item.from_hole, to_hole: item.to_hole, delay_ms: item.delay_ms, kind: item.kind })),
      },
    });
    setAnalysis(null);
  }

  function toggleStartersFromSelection() {
    if (rejectLocked("designed")) return;
    if (!selected.size) return;
    const network = normalizeNetwork(document.network);
    const current = new Set(
      (network.starter_items.length ? network.starter_items.map((item) => item.hole_id) : network.starters),
    );
    const selectedIds = Array.from(selected);
    const allSelectedAreStarters = selectedIds.every((id) => current.has(id));
    for (const id of selectedIds) {
      if (allSelectedAreStarters) current.delete(id);
      else current.add(id);
    }
    const starterItems = Array.from(current).map((holeId) => ({ id: `st-${holeId}`, hole_id: holeId, delay_ms: 0, kind: "starter" }));
    dispatch({
      type: "SET_NETWORK",
      network: { ...network, starter_items: starterItems, starters: starterItems.map((item) => item.hole_id) },
    });
    setAnalysis(null);
  }

  async function generateTie() {
    if (rejectLocked("designed")) return;
    if (!document.holes.length) {
      setError("Сначала постройте сетку скважин.");
      return;
    }
    setTieBusy(true);
    setError("");
    try {
      const result = await api.design.tie(document.holes, tieScheme, {
        ...tieParams,
        selected_hole_ids: Array.from(selected),
      });
      dispatch({ type: "SET_NETWORK", network: result.network });
      setAnalysis(null);
      setCurrentMs(0);
      setPlaying(false);
      setPendingTieFromId(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось построить схему коммутации.");
    } finally {
      setTieBusy(false);
    }
  }

  async function runAnalyze() {
    const network = normalizeNetwork(document.network);
    const hasNetwork = Boolean(
      network.starters.length
      || network.starter_items.length
      || network.connectors.length
      || network.surface_connectors.length
      || Object.keys(network.electronic_times_ms).length
      || network.electronic_channels.length,
    );
    if (!hasNetwork) {
      setError("Сначала постройте схему коммутации.");
      return;
    }
    setAnalyzeBusy(true);
    setError("");
    try {
      const designForAnalysis = {
        ...document,
        pattern_params: patternParams as unknown as Record<string, unknown>,
        charge_rules: chargeRules as unknown as Record<string, unknown>,
        explosive_key: explosiveKey,
      };
      const result = await api.design.analyze(designForAnalysis, isolineStepMs, micWindowMs, ppv);
      setAnalysis(result);
      if (result.firing_events) {
        dispatch({ type: "SET_NETWORK", network: { ...normalizeNetwork(document.network), firing_events: result.firing_events } });
      }
      if (result.maps) setMaps(result.maps);
      setCurrentMs(0);
      setPlaying(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось рассчитать тайминг.");
    } finally {
      setAnalyzeBusy(false);
    }
  }

  async function calculateCost() {
    if (!document.holes.length) {
      setError("Сначала постройте сетку скважин.");
      return;
    }
    setCostBusy(true);
    setError("");
    try {
      const designForCost = {
        ...document,
        pattern_params: patternParams as unknown as Record<string, unknown>,
        charge_rules: chargeRules as unknown as Record<string, unknown>,
        explosive_key: explosiveKey,
      };
      const result = await api.design.cost(designForCost, scenarioId);
      setCostResult(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось рассчитать смету.");
    } finally {
      setCostBusy(false);
    }
  }

  async function interceptHoles(
    holes = document.holes,
    domains = document.domains,
    waterTable = document.water_table_z_m,
  ) {
    if (rejectLocked("designed")) return;
    if (!domains.length || !holes.length) {
      setError("Задайте домены и скважины, затем пересеките ось с геологией.");
      return;
    }
    setGeologyBusy(true);
    setError("");
    try {
      const result = await api.design.interceptGeology(holes, domains, waterTable);
      dispatch({ type: "SET_HOLE_GEOLOGY", holes: result.holes });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось пересечь скважины с доменами.");
    } finally {
      setGeologyBusy(false);
    }
  }

  function upsertDomain(domain: typeof document.domains[number]) {
    if (rejectLocked("designed")) return;
    dispatch({ type: "UPSERT_DOMAIN", domain });
  }

  function deleteDomain(id: string) {
    if (rejectLocked("designed")) return;
    dispatch({ type: "DELETE_DOMAIN", id });
    if (selectedDomainId === id) {
      setSelectedDomainId(null);
      setDrawingDomain(false);
    }
  }

  function copyContourToDomain(id: string) {
    if (rejectLocked("designed")) return;
    const domain = document.domains.find((item) => item.id === id);
    if (!domain) return;
    if (document.contour.vertices.length < 3) {
      setError("Сначала нарисуйте контур блока — его можно взять как регион домена.");
      return;
    }
    dispatch({
      type: "UPSERT_DOMAIN",
      domain: { ...domain, polygon: document.contour.vertices.map((v) => ({ ...v })) },
    });
  }

  function loadExampleLayers() {
    if (rejectLocked("designed")) return;
    const layers = exampleLayeredDomains(document.contour);
    dispatch({ type: "SET_DOMAINS", domains: layers });
    setSelectedDomainId(layers[0]?.id ?? null);
    setDrawingDomain(false);
  }

  function addDomainVertex(domainId: string, point: Point3) {
    if (rejectLocked("designed")) return;
    const domain = document.domains.find((item) => item.id === domainId);
    if (!domain) return;
    dispatch({ type: "UPSERT_DOMAIN", domain: { ...domain, polygon: [...domain.polygon, point] } });
  }

  function siteModel(): VibrationModel {
    return document.vibration_models[0] ?? {
      id: "vm-site",
      name: "Площадочный закон",
      k: 200,
      n: 1.6,
      scaled_distance: "q_cube_over_r",
      calibration_source: "ориентировочно",
      confidence: 0.3,
      notes: "",
    };
  }

  function addReceptorAt(world: { x: number; y: number }) {
    if (rejectLocked("designed")) return;
    const kind: ReceptorKind = "building";
    const created = emptyReceptor(document.receptors, kind);
    created.location = { x: world.x, y: world.y, z: document.contour.bench.crest_z_m };
    dispatch({ type: "UPSERT_RECEPTOR", receptor: created });
    setSelectedReceptorId(created.id);
    setPlacingReceptor(false);
    setDrawingDomain(false);
    setVibResult(null);
  }

  async function predictVibration() {
    if (!document.receptors.length) {
      setError("Поставьте хотя бы один рецептор на план.");
      return;
    }
    setVibBusy(true);
    setError("");
    try {
      const result = await api.design.vibration({
        design: {
          ...document,
          pattern_params: patternParams as unknown as Record<string, unknown>,
          charge_rules: chargeRules as unknown as Record<string, unknown>,
          explosive_key: explosiveKey,
        },
        model_id: siteModel().id,
        mic_window_ms: micWindowMs,
        measured: document.vibration_measurements,
      });
      setVibResult(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось рассчитать сейсмику.");
      setVibResult(null);
    } finally {
      setVibBusy(false);
    }
  }

  function designPayload() {
    return {
      ...document,
      pattern_params: patternParams as unknown as Record<string, unknown>,
      charge_rules: chargeRules as unknown as Record<string, unknown>,
      explosive_key: explosiveKey,
    };
  }

  async function recordAsDrilled(item: AsDrilledHole) {
    if (rejectLocked("execution")) return;
    if (!document.holes.some((hole) => hole.id === item.design_hole_id)) {
      setError("Сначала выберите проектную скважину.");
      return;
    }
    const designedBefore = document.holes.map((hole) => JSON.stringify(hole));
    setAsDrilledBusy(true);
    setError("");
    try {
      const result = await api.design.recordAsDrilled(designPayload(), [item]);
      if (result.holes && result.holes.some((hole, index) => JSON.stringify(hole) !== designedBefore[index])) {
        setError("Сервер не должен менять проектные скважины при записи факта.");
      }
      dispatch({ type: "SET_AS_DRILLED", holes: result.as_drilled_holes });
      setAsDrilledResult(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось записать факт бурения.");
    } finally {
      setAsDrilledBusy(false);
    }
  }

  async function compareAsDrilled() {
    setAsDrilledBusy(true);
    setError("");
    try {
      const result = await api.design.compareAsDrilled(designPayload());
      setAsDrilledResult(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сравнить факт с проектом.");
      setAsDrilledResult(null);
    } finally {
      setAsDrilledBusy(false);
    }
  }

  async function importMwd(designHoleId: string, samples: Record<string, number | null>[]) {
    if (rejectLocked("execution")) return;
    if (!samples.length) {
      setError("MWD: нужен JSON-массив отсчётов с полем depth / depth_m.");
      return;
    }
    const designedBefore = document.holes.map((hole) => JSON.stringify({ collar: hole.collar, toe: hole.toe }));
    setAsDrilledBusy(true);
    setError("");
    try {
      const result = await api.design.importMwd(designPayload(), designHoleId, samples, "manual-json");
      if (result.holes && result.holes.some((hole, index) => JSON.stringify({ collar: hole.collar, toe: hole.toe }) !== designedBefore[index])) {
        setError("Импорт MWD не должен менять проектные устье и забой.");
      }
      dispatch({ type: "SET_AS_DRILLED", holes: result.as_drilled_holes });
      setAsDrilledResult(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось импортировать MWD.");
    } finally {
      setAsDrilledBusy(false);
    }
  }

  async function recordAsCharged(item: AsChargedHole) {
    if (rejectLocked("execution")) return;
    if (!document.holes.some((hole) => hole.id === item.design_hole_id)) {
      setError("Сначала выберите проектную скважину.");
      return;
    }
    const designedBefore = {
      holes: document.holes.map((hole) => JSON.stringify(hole)),
      loads: document.loads.map((load) => JSON.stringify(load)),
    };
    setAsChargedBusy(true);
    setError("");
    try {
      const result = await api.design.recordAsCharged(designPayload(), [item]);
      if (
        result.holes?.some((hole, index) => JSON.stringify(hole) !== designedBefore.holes[index])
        || result.loads?.some((load, index) => JSON.stringify(load) !== designedBefore.loads[index])
      ) {
        setError("Сервер не должен менять проектные скважины или заряд при записи факта.");
      }
      dispatch({ type: "SET_AS_CHARGED", holes: result.as_charged_holes });
      setAsChargedResult(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось записать факт заряжания.");
    } finally {
      setAsChargedBusy(false);
    }
  }

  async function compareAsCharged() {
    setAsChargedBusy(true);
    setError("");
    try {
      const result = await api.design.compareAsCharged(designPayload());
      setAsChargedResult(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сравнить факт заряжания с проектом.");
      setAsChargedResult(null);
    } finally {
      setAsChargedBusy(false);
    }
  }

  async function recordAsFired(item: AsFiredHole) {
    if (rejectLocked("execution")) return;
    if (!document.holes.some((hole) => hole.id === item.design_hole_id)) {
      setError("Сначала выберите проектную скважину.");
      return;
    }
    const designedBefore = {
      holes: document.holes.map((hole) => JSON.stringify(hole)),
    };
    setAsFiredBusy(true);
    setError("");
    try {
      const result = await api.design.recordAsFired(designPayload(), [item]);
      if (
        result.holes?.some((hole, index) => JSON.stringify(hole) !== designedBefore.holes[index])
        || (result.network && JSON.stringify(result.network.detonators) !== JSON.stringify(document.network.detonators))
      ) {
        setError("Сервер не должен менять проектные скважины или сеть при записи факта взрыва.");
      }
      dispatch({ type: "SET_AS_FIRED", holes: result.as_fired_holes });
      setAsFiredResult(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось записать факт взрыва.");
    } finally {
      setAsFiredBusy(false);
    }
  }

  async function compareAsFired() {
    setAsFiredBusy(true);
    setError("");
    try {
      const result = await api.design.compareAsFired(designPayload());
      setAsFiredResult(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сравнить факт взрыва с проектом.");
      setAsFiredResult(null);
    } finally {
      setAsFiredBusy(false);
    }
  }

  async function compareExecution() {
    setExecutionBusy(true);
    setError("");
    try {
      const result = await api.design.compareExecution(designPayload());
      setExecutionResult(result);
      setAsDrilledResult(result.design_vs_drilled);
      setAsChargedResult(result.design_vs_charged);
      setAsFiredResult(result.design_vs_fired);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сравнить исполнение с проектом.");
      setExecutionResult(null);
    } finally {
      setExecutionBusy(false);
    }
  }

  async function recordBlastResult(item: BlastResult, extras: Parameters<typeof api.design.recordBlastResult>[2]) {
    if (rejectLocked("measured")) return;
    const designedBefore = {
      holes: document.holes.map((hole) => JSON.stringify(hole)),
      loads: document.loads.map((load) => JSON.stringify(load)),
      detonators: JSON.stringify(document.network.detonators),
    };
    setBlastResultBusy(true);
    setError("");
    try {
      const result = await api.design.recordBlastResult(designPayload(), item, extras);
      if (
        result.holes?.some((hole, index) => JSON.stringify(hole) !== designedBefore.holes[index])
        || result.loads?.some((load, index) => JSON.stringify(load) !== designedBefore.loads[index])
        || (result.network && JSON.stringify(result.network.detonators) !== designedBefore.detonators)
      ) {
        setError("Сервер не должен менять проект при записи результатов взрыва.");
      }
      dispatch({ type: "SET_BLAST_RESULT", result: result.result });
      setBlastResultCompare(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось записать результаты взрыва.");
    } finally {
      setBlastResultBusy(false);
    }
  }

  async function compareBlastResult() {
    setBlastResultBusy(true);
    setError("");
    try {
      const result = await api.design.compareBlastResult(designPayload());
      setBlastResultCompare(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сравнить результаты взрыва.");
      setBlastResultCompare(null);
    } finally {
      setBlastResultBusy(false);
    }
  }

  async function refreshDatasets() {
    try {
      const data = await api.design.listDatasets();
      setDatasetItems(data.items);
    } catch {
      setDatasetItems([]);
    }
  }

  async function previewDataset() {
    if (!datasetSiteId.trim()) {
      setDatasetPreview(null);
      return;
    }
    try {
      const result = await api.design.previewDatasetSample(datasetSiteId.trim(), designPayload());
      setDatasetPreview(result);
    } catch {
      setDatasetPreview(null);
    }
  }

  async function buildDataset() {
    if (!datasetSiteId.trim()) {
      setError("Укажите площадку (site_id), чтобы собрать снимок датасета.");
      return;
    }
    setDatasetBusy(true);
    setError("");
    try {
      const snapshot = await api.design.buildDataset({
        site_id: datasetSiteId.trim(),
        name: datasetName.trim(),
        include_design: designPayload(),
      });
      setDatasetSelected(snapshot);
      await refreshDatasets();
      await previewDataset();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось собрать снимок датасета.");
    } finally {
      setDatasetBusy(false);
    }
  }

  async function openDataset(datasetId: string) {
    setDatasetBusy(true);
    setError("");
    try {
      setDatasetSelected(await api.design.getDataset(datasetId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось открыть снимок датасета.");
    } finally {
      setDatasetBusy(false);
    }
  }

  async function refreshCalibrations() {
    try {
      const [models, algos] = await Promise.all([
        api.design.listCalibrationModels(),
        api.design.calibrationAlgorithms(),
      ]);
      setCalibrationItems(models.items);
      setCalibrationAlgorithms(algos.items);
      if (!algos.items.some((item) => item.name === calibrationAlgorithm && item.available)) {
        setCalibrationAlgorithm(algos.default || "random_forest");
      }
    } catch {
      setCalibrationItems([]);
    }
  }

  async function trainCalibration() {
    if (!datasetSelected?.dataset_id) {
      setError("Сначала соберите или откройте снимок датасета.");
      return;
    }
    setCalibrationBusy(true);
    setError("");
    try {
      const trained = await api.design.trainCalibration({
        dataset_id: datasetSelected.dataset_id,
        model_type: calibrationType,
        algorithm: calibrationAlgorithm,
        site_id: datasetSiteId.trim() || datasetSelected.site_id,
      });
      setCalibrationSelected(trained);
      setCalibrationOverlay(null);
      await refreshCalibrations();
      await refreshRegistry();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось обучить модель калибровки.");
    } finally {
      setCalibrationBusy(false);
    }
  }

  async function openCalibration(modelId: string) {
    setCalibrationBusy(true);
    setError("");
    try {
      setCalibrationSelected(await api.design.getCalibrationModel(modelId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось открыть модель калибровки.");
    } finally {
      setCalibrationBusy(false);
    }
  }

  async function markCalibrationProduction() {
    if (!calibrationSelected) return;
    setCalibrationBusy(true);
    setError("");
    try {
      const updated = await api.design.setCalibrationStatus(calibrationSelected.model_id, "production");
      setCalibrationSelected(updated);
      await refreshCalibrations();
      await refreshRegistry();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сменить статус модели.");
    } finally {
      setCalibrationBusy(false);
    }
  }

  function overlayBaseline(): number | null {
    if (calibrationType === "ppv_residual") {
      const values = (vibResult?.predictions ?? []).map((item) => item.ppv_mm_s).filter((value) => value != null);
      return values.length ? Math.max(...values) : null;
    }
    const prediction = fragResult?.site.prediction;
    if (!prediction) return null;
    if (calibrationType === "oversize_residual") return prediction.oversize_pct;
    return prediction.x50_mm;
  }

  async function applyCalibrationOverlay() {
    if (!calibrationSelected) {
      setError("Выберите модель калибровки, чтобы показать рекомендацию.");
      return;
    }
    setCalibrationBusy(true);
    setError("");
    try {
      const overlay = await api.design.predictCalibration({
        model_type: calibrationType,
        model_id: calibrationSelected.model_id,
        site_id: datasetSiteId.trim() || calibrationSelected.site_id,
        baseline: overlayBaseline(),
        design: designPayload(),
      });
      setCalibrationOverlay(overlay);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось применить калибровку.");
    } finally {
      setCalibrationBusy(false);
    }
  }

  async function refreshOutcomes() {
    try {
      const [models, algos] = await Promise.all([
        api.design.listOutcomeModels(),
        api.design.outcomeAlgorithms(),
      ]);
      setOutcomeItems(models.items);
      setOutcomeAlgorithms(algos.items);
      if (!algos.items.some((item) => item.name === outcomeAlgorithm && item.available)) {
        setOutcomeAlgorithm(algos.default || "random_forest");
      }
    } catch {
      setOutcomeItems([]);
    }
  }

  async function trainOutcome() {
    if (!datasetSelected?.dataset_id) {
      setError("Сначала соберите или откройте снимок датасета.");
      return;
    }
    setOutcomeBusy(true);
    setError("");
    try {
      const trained = await api.design.trainOutcome({
        dataset_id: datasetSelected.dataset_id,
        model_type: outcomeType,
        algorithm: outcomeAlgorithm,
        site_id: datasetSiteId.trim() || datasetSelected.site_id,
      });
      setOutcomeSelected(trained);
      setOutcomeOverlay(null);
      await refreshOutcomes();
      await refreshRegistry();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось обучить модель исхода.");
    } finally {
      setOutcomeBusy(false);
    }
  }

  async function openOutcome(modelId: string) {
    setOutcomeBusy(true);
    setError("");
    try {
      setOutcomeSelected(await api.design.getOutcomeModel(modelId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось открыть модель исхода.");
    } finally {
      setOutcomeBusy(false);
    }
  }

  async function markOutcomeProduction() {
    if (!outcomeSelected) return;
    setOutcomeBusy(true);
    setError("");
    try {
      const updated = await api.design.setOutcomeStatus(outcomeSelected.model_id, "production");
      setOutcomeSelected(updated);
      await refreshOutcomes();
      await refreshRegistry();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сменить статус модели.");
    } finally {
      setOutcomeBusy(false);
    }
  }

  async function predictOutcomeType() {
    if (!outcomeSelected) {
      setError("Выберите модель исхода, чтобы показать рекомендацию.");
      return;
    }
    setOutcomeBusy(true);
    setError("");
    try {
      const overlay = await api.design.predictOutcome({
        model_type: outcomeType,
        model_id: outcomeSelected.model_id,
        site_id: datasetSiteId.trim() || outcomeSelected.site_id,
        design: designPayload(),
      });
      setOutcomeOverlay(overlay);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось получить прогноз исхода.");
    } finally {
      setOutcomeBusy(false);
    }
  }

  async function predictAllOutcomes() {
    setOutcomeBusy(true);
    setError("");
    try {
      const modelIds = outcomeSelected
        ? { [outcomeSelected.model_type as OutcomeModelType]: outcomeSelected.model_id }
        : undefined;
      const panel = await api.design.predictAllOutcomes({
        site_id: datasetSiteId.trim() || outcomeSelected?.site_id || "",
        use_production: true,
        model_ids: modelIds,
        design: designPayload(),
      });
      setOutcomePanel(panel);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось получить прогноз исходов.");
    } finally {
      setOutcomeBusy(false);
    }
  }

  function learningSnapshotIds(scope: "global" | "site"): string[] {
    const site = datasetSiteId.trim() || datasetSelected?.site_id || "";
    if (scope === "site") {
      const matching = datasetItems.filter((item) => item.site_id === site);
      if (matching.length) return matching.map((item) => item.dataset_id);
      if (datasetSelected && (!site || datasetSelected.site_id === site)) {
        return [datasetSelected.dataset_id];
      }
      return [];
    }
    if (datasetItems.length) return datasetItems.map((item) => item.dataset_id);
    return datasetSelected ? [datasetSelected.dataset_id] : [];
  }

  async function refreshLearning() {
    try {
      const [models, algos] = await Promise.all([
        api.design.listLearningModels(),
        api.design.learningAlgorithms(),
      ]);
      setLearningItems(models.items);
      setLearningAlgorithms(algos.items);
      if (!algos.items.some((item) => item.name === learningAlgorithm && item.available)) {
        setLearningAlgorithm(algos.default || "random_forest");
      }
    } catch {
      setLearningItems([]);
    }
  }

  async function trainLearningGlobal() {
    const datasetIds = learningSnapshotIds("global");
    if (!datasetIds.length) {
      setError("Сначала соберите или откройте снимок датасета.");
      return;
    }
    setLearningBusy(true);
    setError("");
    try {
      const trained = await api.design.trainLearningGlobal({
        dataset_ids: datasetIds,
        model_type: learningType,
        algorithm: learningAlgorithm,
      });
      setLearningSelected(trained);
      setLearningOverlay(null);
      await refreshLearning();
      await refreshRegistry();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось обучить глобальный prior.");
    } finally {
      setLearningBusy(false);
    }
  }

  async function trainLearningSite() {
    const site = datasetSiteId.trim() || datasetSelected?.site_id || "";
    const datasetIds = learningSnapshotIds("site");
    if (!site) {
      setError("Укажите площадку (site_id) для адаптации.");
      return;
    }
    if (!datasetIds.length) {
      setError("Для адаптации нужны снимки этой площадки.");
      return;
    }
    setLearningBusy(true);
    setError("");
    try {
      const priorId = learningSelected?.scope === "global" && learningSelected.model_type === learningType
        ? learningSelected.model_id
        : learningItems.find((item) => item.scope === "global" && item.model_type === learningType)?.model_id;
      const trained = await api.design.trainLearningSite({
        dataset_ids: datasetIds,
        site_id: site,
        model_type: learningType,
        algorithm: learningAlgorithm,
        prior_model_id: priorId,
      });
      setLearningSelected(trained);
      setLearningOverlay(null);
      await refreshLearning();
      await refreshRegistry();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось адаптировать модель площадки.");
    } finally {
      setLearningBusy(false);
    }
  }

  async function openLearning(modelId: string) {
    setLearningBusy(true);
    setError("");
    try {
      setLearningSelected(await api.design.getLearningModel(modelId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось открыть модель обучения.");
    } finally {
      setLearningBusy(false);
    }
  }

  async function markLearningProduction() {
    if (!learningSelected) return;
    setLearningBusy(true);
    setError("");
    try {
      const updated = await api.design.setLearningStatus(learningSelected.model_id, "production");
      setLearningSelected(updated);
      await refreshLearning();
      await refreshRegistry();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сменить статус модели.");
    } finally {
      setLearningBusy(false);
    }
  }

  async function predictLearning() {
    if (!learningSelected) {
      setError("Выберите модель обучения, чтобы показать рекомендацию.");
      return;
    }
    setLearningBusy(true);
    setError("");
    try {
      const overlay = await api.design.predictLearning({
        model_type: learningType,
        model_id: learningSelected.model_id,
        site_id: datasetSiteId.trim() || learningSelected.site_id,
        scope: learningSelected.scope,
        design: designPayload(),
      });
      setLearningOverlay(overlay);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось получить прогноз обучения.");
    } finally {
      setLearningBusy(false);
    }
  }

  async function refreshRegistry() {
    try {
      const listed = await api.design.listRegistryModels(
        registryFamily ? { family: registryFamily } : undefined,
      );
      setRegistryItems(listed.items);
      if (registrySelected) {
        const fresh = listed.items.find(
          (item) => item.family === registrySelected.family && item.model_id === registrySelected.model_id,
        );
        if (fresh) setRegistrySelected(fresh);
      }
    } catch {
      setRegistryItems([]);
    }
  }

  async function openRegistry(family: string, modelId: string) {
    setRegistryBusy(true);
    setError("");
    try {
      setRegistrySelected(await api.design.getRegistryModel(family, modelId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось открыть карточку реестра.");
    } finally {
      setRegistryBusy(false);
    }
  }

  async function promoteRegistry(toStatus: string) {
    if (!registrySelected) return;
    setRegistryBusy(true);
    setError("");
    try {
      const updated = await api.design.promoteRegistryModel(registrySelected.family, registrySelected.model_id, {
        to_status: toStatus,
        confirm: true,
      });
      setRegistrySelected(updated);
      await refreshRegistry();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось продвинуть модель.");
    } finally {
      setRegistryBusy(false);
    }
  }

  async function refreshDriftAlerts() {
    try {
      const listed = await api.design.listDriftAlerts({ acknowledged: false });
      setDriftAlerts(listed.items);
    } catch {
      setDriftAlerts([]);
    }
  }

  function selectDriftModel(family: string, modelId: string) {
    setDriftFamily(family);
    setDriftModelId(modelId);
  }

  async function runDriftCheck() {
    if (!driftFamily || !driftModelId || !driftDatasetId) {
      setError("Выберите производственную модель и текущий снимок наблюдений.");
      return;
    }
    setDriftBusy(true);
    setError("");
    try {
      const report = await api.design.checkDrift({
        family: driftFamily,
        model_id: driftModelId,
        current_dataset_id: driftDatasetId,
      });
      setDriftReport(report);
      setDriftAlerts(report.alerts.filter((item) => !item.acknowledged));
      await refreshRegistry();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось проверить дрифт.");
    } finally {
      setDriftBusy(false);
    }
  }

  async function acknowledgeDrift(alertId: string) {
    setDriftBusy(true);
    setError("");
    try {
      await api.design.acknowledgeDriftAlert(alertId, { confirm: true });
      await refreshDriftAlerts();
      if (driftReport) {
        setDriftReport({
          ...driftReport,
          alerts: driftReport.alerts.map((item) =>
            item.alert_id === alertId ? { ...item, acknowledged: true, auto_deployed: false } : item,
          ),
        });
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось подтвердить сигнал дрифта.");
    } finally {
      setDriftBusy(false);
    }
  }

  async function refreshSpatial() {
    try {
      const listed = await api.design.listSpatialModels({
        site_id: datasetSiteId.trim() || datasetSelected?.site_id || undefined,
      });
      setSpatialItems(listed.items);
    } catch {
      setSpatialItems([]);
    }
  }

  async function trainSpatial() {
    if (!datasetSelected?.dataset_id) {
      setError("Выберите неизменяемый снимок датасета для обучения скважинной модели.");
      return;
    }
    setSpatialBusy(true);
    setError("");
    try {
      const trained = await api.design.trainSpatial({
        dataset_id: datasetSelected.dataset_id,
        site_id: datasetSiteId.trim() || datasetSelected.site_id,
      });
      setSpatialSelected(trained);
      await refreshSpatial();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось обучить скважинную модель.");
    } finally {
      setSpatialBusy(false);
    }
  }

  async function openSpatial(modelId: string) {
    setSpatialBusy(true);
    setError("");
    try {
      setSpatialSelected(await api.design.getSpatialModel(modelId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось открыть скважинную модель.");
    } finally {
      setSpatialBusy(false);
    }
  }

  async function markSpatialProduction() {
    if (!spatialSelected) return;
    setSpatialBusy(true);
    setError("");
    try {
      const updated = await api.design.setSpatialStatus(spatialSelected.model_id, "production");
      setSpatialSelected(updated);
      await refreshSpatial();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сменить статус скважинной модели.");
    } finally {
      setSpatialBusy(false);
    }
  }

  async function predictSpatial() {
    if (!document.holes.length) {
      setError("Сначала постройте сетку скважин.");
      return;
    }
    setSpatialBusy(true);
    setError("");
    try {
      const overlay = await api.design.predictSpatial({
        design: designPayload(),
        model_id: spatialSelected?.model_id,
        site_id: datasetSiteId.trim() || spatialSelected?.site_id || "",
        use_production: !spatialSelected,
        block: {
          x50_mm: outcomePanel?.x50_mm?.value ?? outcomeOverlay?.predicted ?? undefined,
          oversize_pct: outcomePanel?.oversize_pct?.value ?? undefined,
          toe_probability: outcomePanel?.toe_risk?.value ?? undefined,
        },
      });
      setSpatialOverlay(overlay);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось построить скважинную карту.");
    } finally {
      setSpatialBusy(false);
    }
  }

  async function createDesignScenario() {
    if (!document.holes.length) {
      setError("Сначала постройте сетку скважин.");
      return;
    }
    if (!scenarioName.trim()) {
      setError("Задайте имя сценария.");
      return;
    }
    setScenarioBusy(true);
    setError("");
    try {
      const created = await api.design.createScenario({
        design: designPayload(),
        name: scenarioName.trim(),
        persist: Boolean(document.design_id),
        params: {
          diameter_mm: scenarioDiameterMm,
          spacing_a_m: scenarioSpacingM,
          burden_b_m: scenarioBurdenM,
          powder_factor_kg_m3: scenarioPowderFactor,
          cost_scenario_id: scenarioId,
          site_id: datasetSiteId.trim(),
          use_production_overlays: scenarioUseOverlays,
        },
      });
      if (document.design_id) {
        const listed = await api.design.listScenarios(document.design_id);
        setScenarioItems(listed.items);
      } else {
        setScenarioInline((prev) => [...prev, created]);
        setScenarioItems((prev) => [
          ...prev,
          {
            scenario_id: created.scenario_id,
            design_id: created.design_id,
            name: created.name,
            kind: created.kind,
            created_at: created.created_at,
            diameter_mm: created.outcomes.diameter_mm,
            spacing_a_m: created.outcomes.spacing_a_m,
            burden_b_m: created.outcomes.burden_b_m,
            powder_factor_kg_m3: created.outcomes.powder_factor_kg_m3,
            hole_count: created.outcomes.hole_count,
          },
        ]);
      }
      setScenarioCompare(null);
      if (scenarioName.trim() === "Сценарий A") setScenarioName("Сценарий B");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось построить сценарий.");
    } finally {
      setScenarioBusy(false);
    }
  }

  function parseOptValues(name: string, text: string): Array<number | string> {
    return text.split(/[,;]+/).map((part) => part.trim()).filter(Boolean).map((part) => {
      if (name === "explosive_key") return part;
      const value = Number(part.replace(",", "."));
      return Number.isFinite(value) ? value : part;
    });
  }

  async function runOptimization() {
    if (!document.holes.length) {
      setError("Сначала постройте сетку скважин.");
      return;
    }
    const variables = optVariables
      .filter((item) => item.enabled)
      .map((item) => ({ name: item.name, values: parseOptValues(item.name, item.valuesText) }));
    if (!variables.length) {
      setError("Включите хотя бы одну переменную поиска.");
      return;
    }
    if (!optObjectives.length) {
      setError("Включите хотя бы одну цель.");
      return;
    }
    setOptBusy(true);
    setError("");
    try {
      const result = await api.design.optimize({
        design: designPayload(),
        variables,
        objectives: optObjectives,
        target_x50_mm: optTargetX50Mm,
        max_candidates: optMaxCandidates,
        include_baseline: true,
        persist: Boolean(document.design_id),
        params: { cost_scenario_id: scenarioId, site_id: datasetSiteId.trim() },
      });
      setOptResult(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось выполнить поиск Парето.");
    } finally {
      setOptBusy(false);
    }
  }

  async function promoteOptimizationCandidate(candidate: OptimizationCandidate) {
    setOptBusy(true);
    setError("");
    try {
      const created = await api.design.promoteOptimization({
        design: designPayload(),
        name: `Парето ${candidate.candidate_id}`,
        persist: Boolean(document.design_id),
        params: candidate.params,
      });
      if (document.design_id) {
        const listed = await api.design.listScenarios(document.design_id);
        setScenarioItems(listed.items);
      } else {
        setScenarioInline((prev) => [...prev, created]);
        setScenarioItems((prev) => [
          ...prev,
          {
            scenario_id: created.scenario_id,
            design_id: created.design_id,
            name: created.name,
            kind: created.kind,
            created_at: created.created_at,
            diameter_mm: created.outcomes.diameter_mm,
            spacing_a_m: created.outcomes.spacing_a_m,
            burden_b_m: created.outcomes.burden_b_m,
            powder_factor_kg_m3: created.outcomes.powder_factor_kg_m3,
            hole_count: created.outcomes.hole_count,
          },
        ]);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сохранить кандидат как сценарий.");
    } finally {
      setOptBusy(false);
    }
  }

  async function runRecommendation() {
    if (!document.holes.length) {
      setError("Сначала постройте сетку скважин.");
      return;
    }
    const variables = optVariables
      .filter((item) => item.enabled)
      .map((item) => ({ name: item.name, values: parseOptValues(item.name, item.valuesText) }));
    setRecBusy(true);
    setError("");
    try {
      const result = await api.design.recommend({
        design: designPayload(),
        profile: recProfile,
        variables,
        objectives: optObjectives,
        target_x50_mm: optTargetX50Mm,
        max_candidates: optMaxCandidates,
        persist: Boolean(document.design_id),
        params: {
          cost_scenario_id: scenarioId,
          site_id: datasetSiteId.trim(),
          use_production_overlays: recUseOverlays,
        },
      });
      setRecResult(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось получить рекомендацию.");
    } finally {
      setRecBusy(false);
    }
  }

  async function promoteRecommendation(candidate: OptimizationCandidate) {
    setRecBusy(true);
    setError("");
    try {
      const created = await api.design.promoteRecommendation({
        design: designPayload(),
        name: `Рекомендация ${recProfile}`,
        persist: Boolean(document.design_id),
        params: candidate.params,
      });
      if (document.design_id) {
        const listed = await api.design.listScenarios(document.design_id);
        setScenarioItems(listed.items);
      } else {
        setScenarioInline((prev) => [...prev, created]);
        setScenarioItems((prev) => [
          ...prev,
          {
            scenario_id: created.scenario_id,
            design_id: created.design_id,
            name: created.name,
            kind: created.kind,
            created_at: created.created_at,
            diameter_mm: created.outcomes.diameter_mm,
            spacing_a_m: created.outcomes.spacing_a_m,
            burden_b_m: created.outcomes.burden_b_m,
            powder_factor_kg_m3: created.outcomes.powder_factor_kg_m3,
            hole_count: created.outcomes.hole_count,
          },
        ]);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сохранить рекомендацию как сценарий.");
    } finally {
      setRecBusy(false);
    }
  }

  async function compareDesignScenarios() {
    if (!scenarioItems.length && !scenarioInline.length) {
      setError("Сначала добавьте хотя бы один сценарий.");
      return;
    }
    setScenarioBusy(true);
    setError("");
    try {
      const table = await api.design.compareScenarios({
        design_id: document.design_id,
        include_baseline: true,
        design: designPayload(),
        inline: document.design_id ? [] : scenarioInline,
      });
      setScenarioCompare(table);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сравнить сценарии.");
    } finally {
      setScenarioBusy(false);
    }
  }

  function currentDesignPayload() {
    return {
      ...document,
      pattern_params: patternParams as unknown as Record<string, unknown>,
      charge_rules: chargeRules as unknown as Record<string, unknown>,
      explosive_key: explosiveKey,
    };
  }

  async function assemblePassport() {
    if (!document.holes.length) {
      setError("Сначала постройте сетку скважин.");
      return;
    }
    setPassportBusy(true);
    setError("");
    try {
      const result = await api.design.buildPassport({
        design: currentDesignPayload(),
        lump_size_mm: lumpSizeMm,
        planned_cost: costResult
          ? {
              total_amount_rub: costResult.total_amount_rub,
              cost_per_m3: costResult.cost_per_m3,
              variable_total_rub: costResult.variable_total_rub,
              labor_total_rub: costResult.labor_total_rub,
              fixed_total_rub: costResult.fixed_total_rub,
            }
          : undefined,
      });
      setPassportResult(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось собрать паспорт.");
      setPassportResult(null);
    } finally {
      setPassportBusy(false);
    }
  }

  async function printPassport() {
    setError("");
    try {
      if (document.holes.length) {
        const htmlText = await api.design.renderPassportHtml({
          design: currentDesignPayload(),
          lump_size_mm: lumpSizeMm,
          planned_cost: costResult
            ? { total_amount_rub: costResult.total_amount_rub, cost_per_m3: costResult.cost_per_m3 }
            : undefined,
        });
        const blob = new Blob([htmlText], { type: "text/html;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        window.open(url, "_blank");
        return;
      }
      if (document.design_id) {
        window.open(api.design.passportUrl(document.design_id), "_blank");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось открыть паспорт.");
    }
  }

  function togglePlay() {
    if (!analysis) return;
    if (!playing && currentMs >= maxAnimationMs) setCurrentMs(0);
    setPlaying((prev) => !prev);
  }

  function scrub(ms: number) {
    setPlaying(false);
    setCurrentMs(ms);
  }

  async function transitionLifecycle(toStatus: DesignLifecycleStatus) {
    if (!document.design_id) {
      setError("Сначала сохраните паспорт.");
      return;
    }
    if (!lifecycleConfirm) {
      setError("Смена статуса требует явного подтверждения.");
      return;
    }
    setSaveBusy(true);
    setError("");
    try {
      await api.design.transitionPlan(document.design_id, {
        to_status: toStatus,
        confirm: true,
        note: lifecycleNote,
      });
      const design = await api.design.getPlan(document.design_id);
      dispatch({ type: "LOAD", design });
      setLifecycleConfirm(false);
      setLifecycleNote("");
      await refreshPlans();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сменить статус паспорта.");
    } finally {
      setSaveBusy(false);
    }
  }

  async function forkPlan() {
    if (!document.design_id) {
      setError("Сначала сохраните паспорт.");
      return;
    }
    setSaveBusy(true);
    setError("");
    try {
      const forked = await api.design.forkPlan(document.design_id, `${document.name} · ревизия`);
      dispatch({ type: "LOAD", design: forked });
      setLifecycleConfirm(false);
      setLifecycleNote("");
      setWorkflowStage("survey");
      setMode("contour");
      await refreshPlans();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось создать ревизию.");
    } finally {
      setSaveBusy(false);
    }
  }

  async function savePlan() {
    if (document.design_id && recordFrozen) {
      setError(freezeMessage(document.lifecycle_status));
      return;
    }
    setSaveBusy(true);
    setError("");
    try {
      const toSave = {
        ...document,
        pattern_params: patternParams as unknown as Record<string, unknown>,
        charge_rules: chargeRules as unknown as Record<string, unknown>,
        explosive_key: explosiveKey,
      };
      const saved = document.design_id ? await api.design.savePlan(document.design_id, toSave) : await api.design.createPlan(toSave);
      dispatch({ type: "LOAD", design: saved });
      await refreshPlans();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сохранить паспорт.");
    } finally {
      setSaveBusy(false);
    }
  }

  async function openPlan(id: string) {
    setSaveBusy(true);
    setError("");
    try {
      const design = await api.design.getPlan(id);
      dispatch({ type: "LOAD", design });
      if (design.pattern_params && Object.keys(design.pattern_params).length) {
        setPatternParams({ ...DEFAULT_PATTERN_PARAMS, ...(design.pattern_params as Partial<PatternParams>) });
      }
      if (design.charge_rules && Object.keys(design.charge_rules).length) {
        setChargeRules({ ...DEFAULT_CHARGE_RULES, ...(design.charge_rules as Partial<ChargeRules>) });
      }
      if (design.explosive_key) setExplosiveKey(design.explosive_key);
      setBlockVolumeM3(null);
      setPendingFit(true);
      setSelected(new Set());
      setSelectedRow(null);
      setAnalysis(null);
      setCurrentMs(0);
      setPlaying(false);
      setCostResult(null);
      setSelectedDomainId(design.domains[0]?.id ?? null);
      setDrawingDomain(false);
      setMaps(null);
      setFragResult(null);
      setVibResult(null);
      setSelectedReceptorId(design.receptors[0]?.id ?? null);
      setPlacingReceptor(false);
      setPendingTieFromId(null);
      setAsDrilledResult(null);
      setAsChargedResult(null);
      setAsFiredResult(null);
      setExecutionResult(null);
      setBlastResultCompare(null);
      setCalibrationOverlay(null);
      setOutcomeOverlay(null);
      setOutcomePanel(null);
      setLearningOverlay(null);
      setSpatialOverlay(null);
      setSpatialSelected(null);
      setScenarioItems([]);
      setScenarioInline([]);
      setScenarioCompare(null);
      setOptResult(null);
      if (design.design_id) {
        const listed = await api.design.listScenarios(design.design_id);
        setScenarioItems(listed.items);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось открыть паспорт.");
    } finally {
      setSaveBusy(false);
    }
  }

  async function deletePlan(id: string) {
    try {
      await api.design.deletePlan(id);
      if (id === document.design_id) {
        dispatch({ type: "LOAD", design: emptyDesign() });
        setBlockVolumeM3(null);
        setPendingFit(true);
      }
      await refreshPlans();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось удалить паспорт.");
    }
  }

  function newPlan() {
    dispatch({ type: "LOAD", design: emptyDesign() });
    setPendingFit(true);
    setPatternParams(DEFAULT_PATTERN_PARAMS);
    setChargeRules(DEFAULT_CHARGE_RULES);
    setTieParams(DEFAULT_TIE_PARAMS);
    setBlockVolumeM3(null);
    setSelected(new Set());
    setSelectedRow(null);
    setAnalysis(null);
    setCurrentMs(0);
    setPlaying(false);
    setCostResult(null);
    setSelectedDomainId(null);
    setDrawingDomain(false);
    setMaps(null);
    setFragResult(null);
    setVibResult(null);
    setSelectedReceptorId(null);
    setPlacingReceptor(false);
    setPendingTieFromId(null);
    setAsDrilledResult(null);
    setAsChargedResult(null);
    setAsFiredResult(null);
    setExecutionResult(null);
    setBlastResultCompare(null);
    setScenarioItems([]);
    setScenarioInline([]);
    setScenarioCompare(null);
    setOptResult(null);
  }

  async function exportCsv() {
    if (!document.design_id) return;
    try {
      await api.design.exportCsv(document.design_id, `${document.name || "passport"}.csv`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось выгрузить CSV.");
    }
  }

  const hasImportedSurvey = Boolean(document.surfaces.top || document.surfaces.floor || document.surfaces.face);
  const crsUnconfirmed = isCrsUnconfirmed(document.coordinate_system, hasImportedSurvey);
  const stageStatuses = statusesForDocument(document, { crsUnconfirmed });
  const inspectHole = document.holes.find((h) => h.id === inspectHoleId) ?? null;
  const stageTitle = WORKFLOW_STAGES.find((item) => item.id === workflowStage)?.label ?? "Параметры";
  // Стрелка выброса на плане: если тайминг задан «по направлению», показываем
  // именно его азимут (применённый, иначе настраиваемый); азимут рядов —
  // только как запасной вариант для рядных схем.
  const appliedDirectionDeg = Number(document.network.timing_params?.direction_azimuth_deg);
  const throwAzimuthDeg = document.network.timing_mode === "direction" && Number.isFinite(appliedDirectionDeg)
    ? appliedDirectionDeg
    : tieParams.timing_mode === "direction"
      ? tieParams.direction_azimuth_deg
      : patternParams.row_azimuth_deg;
  const mapContourLayers = useMemo(() => layersToMapLegend(designView.layers), [designView.layers]);
  const holeHealthMap = useMemo(
    () => computeAllHoleHealth({
      holes: document.holes,
      loadsById,
      network: document.network,
      analysis,
      contour: document.contour,
      asDrilled: document.as_drilled_holes,
      designHoleIds: new Set(document.holes.map((h) => h.id)),
    }),
    [document.holes, document.network, document.contour, document.as_drilled_holes, loadsById, analysis],
  );
  const healthSummary = useMemo(
    () => summarizeHealth(holeHealthMap, document.holes),
    [holeHealthMap, document.holes],
  );
  const holeColors3d = useMemo(() => {
    const colors: Record<string, number> = {};
    for (const hole of document.holes) {
      let hex = "#2d7556";
      if (designView.colorMode === "health" && holeHealthMap[hole.id] && holeHealthMap[hole.id] !== "ok") {
        hex = healthColor(holeHealthMap[hole.id]);
      } else if (designView.colorMode === "charge_kg") {
        const load = loadsById[hole.id];
        hex = load && load.total_charge_kg > 0 ? "#c45a2c" : "#9aa8a1";
      } else if (designView.colorMode === "delay_ms" && analysis?.times_ms?.[hole.id] !== undefined) {
        hex = "#7a6ee0";
      } else if (designView.colorMode === "as_drilled") {
        hex = document.as_drilled_holes.some((item) => item.design_hole_id === hole.id) ? "#d07a2d" : "#9aa8a1";
      } else {
        const palette: Record<string, string> = { production: "#2d7556", contour: "#c9a227", presplit: "#7a6ee0", trim: "#7a6ee0" };
        hex = palette[hole.kind] ?? "#2d7556";
      }
      colors[hole.id] = Number.parseInt(hex.replace("#", ""), 16);
    }
    return colors;
  }, [document.holes, document.as_drilled_holes, designView.colorMode, holeHealthMap, loadsById, analysis]);
  const designCommands = useMemo<DesignCommand[]>(() => [
    ...buildPresetCommands(setViewPreset),
    ...buildCameraCommands((mode) => {
      setDesignView((prev) => ({ ...prev, cameraMode3d: mode }));
      setViewMode("3d");
    }),
    { id: "measure", label: "Измерить расстояние", keywords: ["линейка", "измерить", "шаг"], run: () => {
      setViewMode("plan");
      setToolRequest({ tool: "measure", tick: Date.now() });
    } },
    { id: "fit", label: "Вписать блок", keywords: ["вписать", "размер"], run: () => setZoomRequest({ kind: "fit", tick: Date.now() }) },
    { id: "zoom-selection", label: "Зум к выбору", keywords: ["выбор", "зум"], run: () => setZoomRequest({ kind: "selection", tick: Date.now() }) },
    { id: "review", label: "Проверить проект", keywords: ["проверка", "замечания"], run: () => setViewPreset("review") },
    { id: "isolines", label: "Показать изолинии", keywords: ["изолинии", "тайминг"], run: () => setDesignView((prev) => ({ ...prev, layers: { ...prev.layers, isolines: true } })) },
    { id: "reset-view", label: "Сбросить вид к пресету", keywords: ["сброс", "вид"], run: () => setDesignView((prev) => resetLayersToPreset(prev)) },
    { id: "open-inspector", label: "Открыть карточку скважины", keywords: ["карточка", "скважина"], run: () => {
      const id = selected.size === 1 ? Array.from(selected)[0] : null;
      if (id) setInspectHoleId(id);
    } },
  ], [selected]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCommandOpen(true);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <div className="design-workstation">
      <header className="design-chrome">
        <input
          className="design-name-input"
          value={document.name}
          disabled={metadataLocked}
          onChange={(e) => {
            if (metadataLocked) {
              setError(freezeMessage(document.lifecycle_status));
              return;
            }
            dispatch({ type: "SET_NAME", name: e.target.value });
          }}
          aria-label="Название паспорта"
        />
        <span className={`save-status lifecycle-pill status-${document.lifecycle_status}`}>
          ● {statusLabel(document.lifecycle_status)}
        </span>
        {crsUnconfirmed && (
          <span className="crs-warning" role="status">Система координат не подтверждена</span>
        )}
        <WorkflowNav stage={workflowStage} statuses={stageStatuses} onStageChange={selectStage} />
        <div className="history-controls">
          <button onClick={savePlan} disabled={saveBusy || recordFrozen}>{saveBusy ? "Сохраняю…" : "Сохранить"}</button>
          <button onClick={() => dispatch({ type: "UNDO" })} disabled={!state.past.length || designedLocked} title="Отменить (Ctrl+Z)">↶</button>
          <button onClick={() => dispatch({ type: "REDO" })} disabled={!state.future.length || designedLocked} title="Повторить (Ctrl+Shift+Z)">↷</button>
        </div>
      </header>
      {error && <div className="page-error" role="alert">{error}</div>}
      {designedLocked && (
        <div className="lifecycle-banner compact" role="status">
          {recordFrozen
            ? "Паспорт закрыт. Создайте ревизию, чтобы править дальше."
            : "Слой DESIGNED заморожен. Исполнение и замер — отдельно, сценарии остаются оверлеями."}
        </div>
      )}
      <div className="design-map-stage">
        <div className="map-chrome-row">
          <div className="view-switch">
            <button type="button" className={viewMode === "plan" ? "active" : ""} onClick={() => setViewMode("plan")}>План</button>
            <button type="button" className={viewMode === "3d" ? "active" : ""} onClick={() => setViewMode("3d")}>3D</button>
            <button type="button" className={viewMode === "section" ? "active" : ""} onClick={() => setViewMode("section")}>Разрез</button>
          </div>
          {viewMode === "3d" && (
            <div className="camera-mode-switch" role="group" aria-label="Режим 3D">
              {(["collar", "shaft", "toe"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  className={designView.cameraMode3d === mode ? "active" : ""}
                  onClick={() => setDesignView((prev) => ({ ...prev, cameraMode3d: mode }))}
                >
                  {mode === "collar" ? "Устье" : mode === "shaft" ? "Ствол" : "Подошва"}
                </button>
              ))}
            </div>
          )}
          <button type="button" className="review-project-btn" onClick={() => setViewPreset("review")}>
            Проверить проект
          </button>
          <button type="button" className="command-palette-btn" onClick={() => setCommandOpen(true)} title="Поиск команд (Ctrl+K)">
            ⌘K
          </button>
          {viewMode === "plan" && (
            <div className="map-toolbar">
              <label>
                Карта
                <select value={mapMetric} onChange={(e) => {
                  const next = e.target.value as OverlayMetric | "";
                  setMapMetric(next);
                  if (!next) return;
                  if (isFragmentationMapMetric(next)) {
                    if (!fragResult && !fragBusy) predictFragmentation();
                    return;
                  }
                  if (isSpatialMapMetric(next)) {
                    if (!spatialOverlay && !spatialBusy) predictSpatial();
                    return;
                  }
                  if (isMovementMapMetric(next)) {
                    if (!movementResult && !movementBusy) predictMovement();
                    return;
                  }
                  if (!maps) refreshMaps();
                }}>
                  <option value="">тип скважины</option>
                  {Object.entries(MAP_METRIC_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  {Object.entries(FRAGMENTATION_MAP_METRIC_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  {Object.entries(SPATIAL_MAP_METRIC_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  {Object.entries(MOVEMENT_MAP_METRIC_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>
              {mapMetric && mapOverlay.range && (
                <span className="map-legend">
                  <small>{mapOverlay.range.min.toFixed(1)}</small>
                  <i />
                  <small>{mapOverlay.range.max.toFixed(1)} {MAP_METRIC_UNITS[mapMetric]}</small>
                </span>
              )}
              <RoleBadge role={showAsDrilled && document.as_drilled_holes.length > 0 && !mapMetric ? "executed" : overlayRole(mapMetric)} />
            </div>
          )}
          <div className="map-chrome-metrics">
            <SummaryPanel
              holes={document.holes}
              blockVolumeM3={blockVolumeM3}
              loads={document.loads.length ? document.loads : undefined}
              holesSource={holeSourceLabel(document)}
              volumeSource={volumeSourceLabel(document.surfaces, document.contour.vertices.length >= 3)}
            />
          </div>
        </div>
        <div className="design-map-body">
          {inspectorOpen && (
            <StageInspector title={stageTitle} onClose={() => setInspectorOpen(false)}>
        <div className="design-sidebar">
          {workflowStage === "report" && <LifecyclePanel
            designId={document.design_id}
            status={document.lifecycle_status}
            revision={document.revision}
            parentDesignId={document.parent_design_id}
            designedSha256={document.designed_sha256}
            events={document.lifecycle_events}
            busy={saveBusy}
            confirm={lifecycleConfirm}
            note={lifecycleNote}
            onConfirmChange={setLifecycleConfirm}
            onNoteChange={setLifecycleNote}
            onTransition={transitionLifecycle}
            onFork={forkPlan}
          />}
          {workflowStage === "report" && <PlansPanel
            plans={plans}
            currentDesignId={document.design_id}
            currentName={document.name}
            currentStatus={document.lifecycle_status}
            onNameChange={(name) => {
              if (metadataLocked) {
                setError(freezeMessage(document.lifecycle_status));
                return;
              }
              dispatch({ type: "SET_NAME", name });
            }}
            onSave={savePlan}
            onOpen={openPlan}
            onDelete={deletePlan}
            onNew={newPlan}
            onExportCsv={exportCsv}
            onPrintPassport={printPassport}
            busy={saveBusy}
            nameLocked={metadataLocked}
            saveLocked={recordFrozen}
          />}
          {workflowStage === "survey" && (
            <fieldset className="workstation-lock" disabled={designedLocked}>
              <SurfacePanel
                surfaces={document.surfaces}
                bench={document.contour.bench}
                coordinateSystem={document.coordinate_system}
                onBenchChange={(bench) => dispatch({ type: "SET_BENCH", bench })}
                onCoordinateSystemChange={(patch) => dispatch({ type: "SET_COORDINATE_SYSTEM", patch })}
                onImport={importSurface}
                onImportBlock={importBenchDxf}
                onClear={(kind) => dispatch({ type: "CLEAR_SURFACE", kind })}
                busy={surfaceBusy}
              />
            </fieldset>
          )}
          {workflowStage === "geology" && (
            <fieldset className="workstation-lock" disabled={designedLocked}>
              <GeologyPanel
                domains={document.domains}
                selectedDomainId={selectedDomainId}
                onSelectedDomainIdChange={(id) => {
                  setSelectedDomainId(id);
                  setDrawingDomain(false);
                }}
                drawing={drawingDomain}
                onToggleDrawing={() => setDrawingDomain((prev) => !prev)}
                waterTableZ={document.water_table_z_m}
                holes={document.holes}
                selectedHoleIds={selected}
                busy={geologyBusy}
                onUpsert={upsertDomain}
                onDelete={deleteDomain}
                onCopyContour={copyContourToDomain}
                onExampleLayers={loadExampleLayers}
                onWaterTableChange={(value) => dispatch({ type: "SET_WATER_TABLE", water_table_z_m: value })}
                onIntercept={() => interceptHoles()}
              />
            </fieldset>
          )}
          {workflowStage === "pattern" && (
            <fieldset className="workstation-lock" disabled={designedLocked}>
              <PatternPanel params={patternParams} onChange={(patch) => setPatternParams((prev) => ({ ...prev, ...patch }))} onGenerate={generatePattern} busy={patternBusy} />
            </fieldset>
          )}
          {workflowStage === "charge" && (
            <fieldset className="workstation-lock" disabled={designedLocked}>
              <ChargePanel
                rules={chargeRules}
                explosives={explosives}
                explosiveKey={explosiveKey}
                domains={document.domains}
                onExplosiveKeyChange={setExplosiveKey}
                onChange={(patch) => setChargeRules((prev) => ({ ...prev, ...patch }))}
                onCalculate={calculateCharge}
                busy={chargeBusy}
              />
            </fieldset>
          )}
          {workflowStage === "timing" && (
            <fieldset className="workstation-lock" disabled={designedLocked}>
              <TiePanel
                scheme={tieScheme}
                params={tieParams}
                network={document.network}
                selectedCount={selected.size}
                pendingFromId={pendingTieFromId}
                onSchemeChange={setTieScheme}
                onParamsChange={(patch) => setTieParams((prev) => ({ ...prev, ...patch }))}
                onGenerate={generateTie}
                onUpdateTie={updateManualTie}
                onRemoveTie={removeManualTie}
                onToggleStarters={toggleStartersFromSelection}
                busy={tieBusy}
              />
              <TimingPanel
                analysis={analysis}
                busy={analyzeBusy}
                onAnalyze={runAnalyze}
                isolineStepMs={isolineStepMs}
                onIsolineStepChange={setIsolineStepMs}
                showIsolines={showIsolines}
                onToggleIsolines={() => setShowIsolines((prev) => !prev)}
                ppv={ppv}
                onPpvChange={(patch) => setPpv((prev) => ({ ...prev, ...patch }))}
                playing={playing}
                onPlayToggle={togglePlay}
                currentMs={currentMs}
                maxMs={maxAnimationMs}
                onScrub={scrub}
              />
            </fieldset>
          )}
          {workflowStage === "simulation" && <>
          <FragmentationPanel
            model={fragModel}
            onModelChange={setFragModel}
            lumpSizeMm={lumpSizeMm}
            onLumpSizeChange={setLumpSizeMm}
            onPredict={predictFragmentation}
            busy={fragBusy}
            result={fragResult}
            selectedHoleId={selected.size === 1 ? Array.from(selected)[0] : null}
          />
          <VibrationPanel
            model={siteModel()}
            onModelChange={(patch) => {
              if (rejectLocked("designed")) return;
              dispatch({ type: "UPSERT_VIBRATION_MODEL", model: { ...siteModel(), ...patch } });
            }}
            receptors={document.receptors}
            selectedReceptorId={selectedReceptorId}
            onSelectedReceptorIdChange={(id) => {
              setSelectedReceptorId(id);
              setPlacingReceptor(false);
            }}
            placing={placingReceptor}
            onTogglePlacing={() => {
              setPlacingReceptor((prev) => !prev);
              setDrawingDomain(false);
            }}
            onUpsertReceptor={(receptor) => {
              if (rejectLocked("designed")) return;
              dispatch({ type: "UPSERT_RECEPTOR", receptor });
              setVibResult(null);
            }}
            onDeleteReceptor={(id) => {
              if (rejectLocked("designed")) return;
              dispatch({ type: "DELETE_RECEPTOR", id });
              if (selectedReceptorId === id) setSelectedReceptorId(null);
              setVibResult(null);
            }}
            measurements={document.vibration_measurements}
            onUpsertMeasurement={(measurement) => {
              if (rejectLocked("measured")) return;
              dispatch({ type: "UPSERT_MEASUREMENT", measurement });
            }}
            onDeleteMeasurement={(id) => {
              if (rejectLocked("measured")) return;
              dispatch({ type: "DELETE_MEASUREMENT", id });
            }}
            micWindowMs={micWindowMs}
            onMicWindowChange={setMicWindowMs}
            onPredict={predictVibration}
            busy={vibBusy}
            result={vibResult}
          />
          <MovementPanel
            onPredict={predictMovement}
            busy={movementBusy}
            result={movementResult}
            selectedHoleId={selected.size === 1 ? Array.from(selected)[0] : null}
            showVectors={showMovementVectors}
            onToggleVectors={() => setShowMovementVectors((prev) => !prev)}
          />
          </>}
          {workflowStage === "execution" && <>
          <AsDrilledPanel
            holes={document.holes}
            asDrilled={document.as_drilled_holes}
            selectedHoleId={selected.size === 1 ? Array.from(selected)[0] : null}
            onSelectedHoleIdChange={(id) => setSelected(id ? new Set([id]) : new Set())}
            onRecord={recordAsDrilled}
            onDelete={(designHoleId) => {
              if (rejectLocked("execution")) return;
              dispatch({ type: "DELETE_AS_DRILLED", designHoleId });
              setAsDrilledResult(null);
            }}
            onCompare={compareAsDrilled}
            onImportMwd={importMwd}
            busy={asDrilledBusy}
            result={asDrilledResult}
            showOverlay={showAsDrilled}
            onToggleOverlay={() => setShowAsDrilled((prev) => !prev)}
            locked={executionLocked}
          />
          <AsChargedPanel
            holes={document.holes}
            loads={document.loads}
            asCharged={document.as_charged_holes}
            selectedHoleId={selected.size === 1 ? Array.from(selected)[0] : null}
            onSelectedHoleIdChange={(id) => setSelected(id ? new Set([id]) : new Set())}
            onRecord={recordAsCharged}
            onDelete={(designHoleId) => {
              if (rejectLocked("execution")) return;
              dispatch({ type: "DELETE_AS_CHARGED", designHoleId });
              setAsChargedResult(null);
            }}
            onCompare={compareAsCharged}
            busy={asChargedBusy}
            result={asChargedResult}
            explosiveKey={explosiveKey}
            locked={executionLocked}
          />
          <AsFiredPanel
            holes={document.holes}
            network={document.network}
            asFired={document.as_fired_holes}
            timesMs={analysis?.times_ms ?? null}
            selectedHoleId={selected.size === 1 ? Array.from(selected)[0] : null}
            onSelectedHoleIdChange={(id) => setSelected(id ? new Set([id]) : new Set())}
            onRecord={recordAsFired}
            onDelete={(designHoleId) => {
              if (rejectLocked("execution")) return;
              dispatch({ type: "DELETE_AS_FIRED", designHoleId });
              setAsFiredResult(null);
            }}
            onCompare={compareAsFired}
            busy={asFiredBusy}
            result={asFiredResult}
            locked={executionLocked}
          />
          <ExecutionComparePanel
            busy={executionBusy}
            result={executionResult}
            onCompare={compareExecution}
          />
          <PostBlastPanel
            designId={document.design_id}
            stored={document.blast_result}
            fragResult={fragResult}
            vibResult={vibResult}
            costResult={costResult}
            lumpSizeMm={lumpSizeMm}
            onRecord={recordBlastResult}
            onCompare={compareBlastResult}
            onClear={() => {
              if (rejectLocked("measured")) return;
              dispatch({ type: "SET_BLAST_RESULT", result: null });
              setBlastResultCompare(null);
            }}
            busy={blastResultBusy}
            result={blastResultCompare}
            locked={measuredLocked}
          />
          </>}
          {workflowStage === "intelligence" && <>
          <DatasetPanel
            siteId={datasetSiteId}
            onSiteIdChange={setDatasetSiteId}
            name={datasetName}
            onNameChange={setDatasetName}
            snapshots={datasetItems}
            selected={datasetSelected}
            preview={datasetPreview}
            busy={datasetBusy}
            onRefresh={() => {
              refreshDatasets();
              previewDataset();
            }}
            onBuild={buildDataset}
            onOpen={openDataset}
          />
          <CalibrationPanel
            siteId={datasetSiteId || datasetSelected?.site_id || ""}
            datasetId={datasetSelected?.dataset_id || ""}
            datasetLabel={datasetSelected ? (datasetSelected.name || `Снимок v${datasetSelected.dataset_version}`) : ""}
            modelType={calibrationType}
            onModelTypeChange={setCalibrationType}
            algorithm={calibrationAlgorithm}
            onAlgorithmChange={setCalibrationAlgorithm}
            algorithms={calibrationAlgorithms}
            models={calibrationItems}
            selected={calibrationSelected}
            overlay={calibrationOverlay}
            busy={calibrationBusy}
            onRefresh={refreshCalibrations}
            onTrain={trainCalibration}
            onOpen={openCalibration}
            onMarkProduction={markCalibrationProduction}
            onApplyOverlay={applyCalibrationOverlay}
          />
          <OutcomePanel
            siteId={datasetSiteId || datasetSelected?.site_id || ""}
            datasetId={datasetSelected?.dataset_id || ""}
            datasetLabel={datasetSelected ? (datasetSelected.name || `Снимок v${datasetSelected.dataset_version}`) : ""}
            modelType={outcomeType}
            onModelTypeChange={setOutcomeType}
            algorithm={outcomeAlgorithm}
            onAlgorithmChange={setOutcomeAlgorithm}
            algorithms={outcomeAlgorithms}
            models={outcomeItems}
            selected={outcomeSelected}
            overlay={outcomeOverlay}
            panel={outcomePanel}
            busy={outcomeBusy}
            onRefresh={refreshOutcomes}
            onTrain={trainOutcome}
            onOpen={openOutcome}
            onMarkProduction={markOutcomeProduction}
            onPredictType={predictOutcomeType}
            onPredictAll={predictAllOutcomes}
          />
          </>}
          {workflowStage === "scenarios" && <>
          <ScenarioPanel
            name={scenarioName}
            onNameChange={setScenarioName}
            diameterMm={scenarioDiameterMm}
            onDiameterChange={setScenarioDiameterMm}
            spacingM={scenarioSpacingM}
            onSpacingChange={setScenarioSpacingM}
            burdenM={scenarioBurdenM}
            onBurdenChange={setScenarioBurdenM}
            powderFactor={scenarioPowderFactor}
            onPowderFactorChange={setScenarioPowderFactor}
            useOverlays={scenarioUseOverlays}
            onUseOverlaysChange={setScenarioUseOverlays}
            items={scenarioItems}
            compare={scenarioCompare}
            busy={scenarioBusy}
            onCreate={createDesignScenario}
            onCompare={compareDesignScenarios}
          />
          <OptimizationPanel
            targetX50Mm={optTargetX50Mm}
            onTargetX50Change={setOptTargetX50Mm}
            maxCandidates={optMaxCandidates}
            onMaxCandidatesChange={setOptMaxCandidates}
            variables={optVariables}
            onVariableToggle={(name, enabled) =>
              setOptVariables((prev) => prev.map((item) => item.name === name ? { ...item, enabled } : item))
            }
            onVariableValuesChange={(name, valuesText) =>
              setOptVariables((prev) => prev.map((item) => item.name === name ? { ...item, valuesText } : item))
            }
            objectives={optObjectives}
            onObjectiveToggle={(key, enabled) =>
              setOptObjectives((prev) => enabled ? (prev.includes(key) ? prev : [...prev, key]) : prev.filter((item) => item !== key))
            }
            result={optResult}
            busy={optBusy}
            onRun={runOptimization}
            onPromote={promoteOptimizationCandidate}
          />
          <RecommendationPanel
            profile={recProfile}
            onProfileChange={setRecProfile}
            useOverlays={recUseOverlays}
            onUseOverlaysChange={setRecUseOverlays}
            result={recResult}
            busy={recBusy}
            onRun={runRecommendation}
            onPromote={promoteRecommendation}
          />
          </>}
          {workflowStage === "intelligence" && <>
          <LearningPanel
            siteId={datasetSiteId || datasetSelected?.site_id || ""}
            datasetLabel={datasetSelected ? (datasetSelected.name || `Снимок v${datasetSelected.dataset_version}`) : ""}
            snapshotCount={datasetItems.length || (datasetSelected ? 1 : 0)}
            modelType={learningType}
            onModelTypeChange={setLearningType}
            algorithm={learningAlgorithm}
            onAlgorithmChange={setLearningAlgorithm}
            algorithms={learningAlgorithms}
            models={learningItems}
            selected={learningSelected}
            overlay={learningOverlay}
            busy={learningBusy}
            onRefresh={refreshLearning}
            onTrainGlobal={trainLearningGlobal}
            onTrainSite={trainLearningSite}
            onOpen={openLearning}
            onMarkProduction={markLearningProduction}
            onPredict={predictLearning}
          />
          <RegistryPanel
            family={registryFamily}
            onFamilyChange={setRegistryFamily}
            models={registryItems}
            selected={registrySelected}
            busy={registryBusy}
            actor={user.email}
            onRefresh={refreshRegistry}
            onOpen={openRegistry}
            onPromote={promoteRegistry}
          />
          <SpatialPanel
            siteId={datasetSiteId || datasetSelected?.site_id || ""}
            datasetId={datasetSelected?.dataset_id || ""}
            datasetLabel={datasetSelected ? (datasetSelected.name || `Снимок v${datasetSelected.dataset_version}`) : ""}
            models={spatialItems}
            selected={spatialSelected}
            overlay={spatialOverlay}
            busy={spatialBusy}
            onRefresh={refreshSpatial}
            onTrain={trainSpatial}
            onOpen={openSpatial}
            onMarkProduction={markSpatialProduction}
            onPredict={predictSpatial}
          />
          <DriftPanel
            models={registryItems}
            selectedModelId={driftFamily && driftModelId ? `${driftFamily}:${driftModelId}` : ""}
            onModelChange={selectDriftModel}
            snapshots={datasetItems}
            currentDatasetId={driftDatasetId}
            onCurrentDatasetChange={setDriftDatasetId}
            report={driftReport}
            alerts={driftAlerts}
            busy={driftBusy}
            actor={user.email}
            onCheck={runDriftCheck}
            onAcknowledge={acknowledgeDrift}
          />
          </>}
          {workflowStage === "report" && <>
          <PassportPanel
            onAssemble={assemblePassport}
            onPrint={printPassport}
            busy={passportBusy}
            result={passportResult}
          />
          <MassBlastPanel designId={document.design_id} designName={document.name} />
          </>}
        </div>
            </StageInspector>
          )}
          {viewMode === "3d" ? (
            <Suspense fallback={<div className="scene3d-loading">Загружаем 3D-движок…</div>}>
              <Scene3D
                contour={document.contour}
                holes={document.holes}
                surfaces={document.surfaces}
                selected={selected}
                onSelectHole={onSelectHole3D}
                cameraMode={designView.cameraMode3d}
                colorMode={designView.colorMode}
                holeColors={holeColors3d}
              />
            </Suspense>
          ) : viewMode === "section" ? (
            <SectionView
              contour={document.contour}
              holes={document.holes}
              loads={document.loads}
              surfaces={document.surfaces}
              network={document.network}
              warnings={analysis?.validation_warnings}
              rowAzimuthDeg={patternParams.row_azimuth_deg}
              selectedRow={selectedRow}
              onSelectedRowChange={setSelectedRow}
              selectedHoleIds={selected}
              onHoleSelect={(id) => setSelected(new Set([id]))}
              onHoleInspect={setInspectHoleId}
              healthById={holeHealthMap}
            />
          ) : (
            <PlanCanvas
              contour={document.contour}
              holes={document.holes}
              mode={mode === "contour" ? "contour" : mode === "tie" ? "tie" : mode === "timing" ? "timing" : "holes"}
              selected={selected}
              onSelectedChange={(ids) => {
                setSelected(ids);
                if (mode === "tie" && ids.size === 1 && !pendingTieFromId) {
                  setPendingTieFromId(Array.from(ids)[0]);
                }
              }}
              onContourChange={onContourChange}
              onToggleFreeFace={onToggleFreeFace}
              onMoveHoles={onMoveHoles}
              onAddHole={onAddHole}
              onDeleteHoles={deleteHoles}
              onSetHolesEnabled={setHolesEnabled}
              camera={camera}
              onCameraChange={setCamera}
              pendingFit={pendingFit}
              onFitApplied={() => setPendingFit(false)}
              spacingHint={{ a: patternParams.spacing_a_m, b: patternParams.burden_b_m }}
              loadsById={loadsById}
              network={designView.layers.network ? document.network : undefined}
              isolines={designView.layers.isolines && showIsolines ? analysis?.isolines : undefined}
              timesMs={analysis?.times_ms ?? undefined}
              animationMs={mode === "timing" && analysis ? currentMs : undefined}
              pendingTieFromId={mode === "tie" ? pendingTieFromId : null}
              onTieHoles={addManualTie}
              onClearPendingTie={() => setPendingTieFromId(null)}
              domains={document.domains}
              drawingDomainId={drawingDomain && selectedDomainId && (mode === "contour" || mode === "holes") && !placingReceptor ? selectedDomainId : null}
              onDomainVertexAdd={addDomainVertex}
              mapValues={mapMetric ? mapOverlay.values : undefined}
              mapRange={mapMetric ? mapOverlay.range : null}
              receptors={document.receptors}
              selectedReceptorId={selectedReceptorId}
              placingReceptor={placingReceptor}
              onAddReceptor={addReceptorAt}
              onSelectReceptor={(id) => {
                setSelectedReceptorId(id);
                setPlacingReceptor(false);
              }}
              vibrationPredictions={vibResult?.predictions}
              asDrilled={document.as_drilled_holes}
              showAsDrilled={designView.layers.actual && showAsDrilled && document.as_drilled_holes.length > 0}
              asCharged={document.as_charged_holes}
              asFired={document.as_fired_holes}
              movementVectors={movementResult?.holes}
              showMovementVectors={showMovementVectors && Boolean(movementResult)}
              onHoleInspect={setInspectHoleId}
              layers={mapContourLayers}
              labelField={designView.labelField}
              colorMode={designView.colorMode}
              healthById={holeHealthMap}
              showHealthLayer={designView.layers.health}
              showNetworkLayer={designView.layers.network}
              showIsolineLayer={designView.layers.isolines}
              showLabelsLayer={designView.layers.labels}
              showThrowDirection={designView.layers.throw_direction}
              throwAzimuthDeg={throwAzimuthDeg}
              measureState={measureState}
              onMeasureChange={setMeasureState}
              onHoleContextMenu={(holeId, x, y) => setHoleMenu({ holeId, x, y })}
              onCursorWorldChange={setMapCursor}
              zoomRequest={zoomRequest}
              onZoomRequestHandled={() => setZoomRequest(null)}
              toolRequest={toolRequest}
              onToolRequestHandled={() => setToolRequest(null)}
              toePolylines={document.surfaces.floor?.polylines}
              insertKind={insertKind}
              onInsertKindChange={setInsertKind}
            />
          )}
          <VisibilityPanel
            viewState={designView}
            collapsed={visibilityCollapsed}
            onToggleCollapsed={() => setVisibilityCollapsed((v) => !v)}
            onPresetChange={setViewPreset}
            onLayerChange={(id: LayerId, visible) => setDesignView((prev) => ({ ...prev, layers: { ...prev.layers, [id]: visible } }))}
            onResetLayers={() => setDesignView((prev) => resetLayersToPreset(prev))}
          />
          <MapStatusBar
            cursorX={mapCursor?.x ?? null}
            cursorY={mapCursor?.y ?? null}
            scalePxPerM={camera.scale}
            selectedCount={selected.size}
            health={healthSummary}
            measure={measureState.result}
            onIssueClick={zoomToHole}
          />
          <HoleContextMenu
            menu={holeMenu}
            onClose={() => setHoleMenu(null)}
            onOpenInspector={setInspectHoleId}
            onToggleEnabled={(id, enabled) => setHolesEnabled([id], enabled)}
            onToggleStarter={toggleStarterForHole}
            onCopyParams={copyHoleParams}
            onZoomToHole={zoomToHole}
            isStarter={Boolean(
              holeMenu && (
                document.network.starter_items.some((item) => item.hole_id === holeMenu.holeId)
                || document.network.starters.includes(holeMenu.holeId)
              ),
            )}
            enabled={holeMenu ? (document.holes.find((h) => h.id === holeMenu.holeId)?.enabled ?? true) : true}
          />
          <CommandPalette open={commandOpen} commands={designCommands} onClose={() => setCommandOpen(false)} />
          {inspectHole && (
            <HoleInspector
              hole={inspectHole}
              load={loadsById[inspectHole.id]}
              locked={designedLocked}
              onClose={() => setInspectHoleId(null)}
              onUpdateHole={onUpdateHole}
              onSetEnabled={setHolesEnabled}
              onDelete={(id) => {
                if (rejectLocked("designed")) return;
                deleteHoles([id]);
                setInspectHoleId(null);
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
