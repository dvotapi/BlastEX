import { Suspense, lazy, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { api } from "../../api/endpoints";
import { holeFromCollar, type Camera, type Vec2 } from "../../lib/geometry2d";
import type { BlastVariant, Explosive, User } from "../../types";
import {
  DEFAULT_CHARGE_RULES,
  DEFAULT_PATTERN_PARAMS,
  DEFAULT_PPV_REQUEST,
  DEFAULT_TIE_PARAMS,
  emptyDesign,
  type AnalyzeResponse,
  type ChargeRules,
  type CostScenarioId,
  type DesignCostResult,
  type DesignSummary,
  type Hole,
  type HoleLoad,
  type PatternParams,
  type Point3,
  type PpvRequest,
  type SchemeType,
  type TieParams,
} from "../../types/design";
import { ChargePanel } from "./ChargePanel";
import { CostPanel } from "./CostPanel";
import { designReducer, initDesignState } from "./designReducer";
import { HoleTable } from "./HoleTable";
import { PatternPanel } from "./PatternPanel";
import { PlanCanvas } from "./PlanCanvas";
import { PlansPanel } from "./PlansPanel";
import { SectionView } from "./SectionView";
import { SummaryPanel } from "./SummaryPanel";
import { TiePanel } from "./TiePanel";
import { TimingPanel } from "./TimingPanel";

// three.js — крупная зависимость, нужная только вкладке «3D»: грузим лениво,
// чтобы не раздувать основной бандл для остальных режимов редактора.
const Scene3D = lazy(() => import("./Scene3D").then((m) => ({ default: m.Scene3D })));

let manualHoleCounter = 0;

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

  const [mode, setMode] = useState<"contour" | "holes" | "charge" | "tie" | "timing" | "3d">("contour");
  const [camera, setCamera] = useState<Camera>({ x: 0, y: 0, scale: 6 });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [patternParams, setPatternParams] = useState<PatternParams>(DEFAULT_PATTERN_PARAMS);
  const [blockVolumeM3, setBlockVolumeM3] = useState<number | null>(null);
  const [plans, setPlans] = useState<DesignSummary[]>([]);
  const [patternBusy, setPatternBusy] = useState(false);
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
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [analyzeBusy, setAnalyzeBusy] = useState(false);
  const [isolineStepMs, setIsolineStepMs] = useState(25);
  const [showIsolines, setShowIsolines] = useState(true);
  const [ppv, setPpv] = useState<PpvRequest>(DEFAULT_PPV_REQUEST);
  const [playing, setPlaying] = useState(false);
  const [currentMs, setCurrentMs] = useState(0);
  const animationFrameRef = useRef<number | null>(null);

  const [scenarioId, setScenarioId] = useState<CostScenarioId>("drill_blast");
  const [costResult, setCostResult] = useState<DesignCostResult | null>(null);
  const [costBusy, setCostBusy] = useState(false);

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

  useEffect(() => { refreshPlans(); }, []);

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
      if ((e.key === "Delete" || e.key === "Backspace") && !typing && selected.size > 0) {
        e.preventDefault();
        deleteSelected();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  async function refreshPlans() {
    try {
      const result = await api.design.listPlans();
      setPlans(result.items);
    } catch {
      // Список паспортов не критичен для работы редактора — молча пропускаем.
    }
  }

  async function generatePattern() {
    if (document.contour.vertices.length < 3) {
      setError("Нарисуйте контур блока (не менее трёх точек) перед раскладкой сетки.");
      return;
    }
    setPatternBusy(true);
    setError("");
    try {
      const result = await api.design.pattern(document.contour, patternParams, document.holes);
      dispatch({ type: "SET_HOLES", holes: result.holes });
      setBlockVolumeM3(result.block_volume_m3);
      setSelected(new Set());
      setChargeRules((prev) => ({ ...prev, grid_a_m: patternParams.spacing_a_m, grid_b_m: patternParams.burden_b_m }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось построить сетку.");
    } finally {
      setPatternBusy(false);
    }
  }

  function onContourChange(vertices: Point3[], freeFaces?: number[][], coalesce?: boolean) {
    dispatch({ type: "SET_CONTOUR_VERTICES", vertices, free_faces: freeFaces, coalesce });
  }

  function onToggleFreeFace(edgeIndex: number) {
    dispatch({ type: "TOGGLE_FREE_FACE", edgeIndex });
  }

  function onMoveHoles(ids: string[], dx: number, dy: number) {
    dispatch({ type: "MOVE_HOLES", ids, dx, dy });
  }

  function onUpdateHole(id: string, patch: Partial<Hole>) {
    dispatch({ type: "UPDATE_HOLE", id, patch });
  }

  function onAddHole(world: Vec2) {
    manualHoleCounter += 1;
    const collar: Point3 = { x: Math.round(world.x * 100) / 100, y: Math.round(world.y * 100) / 100, z: document.contour.bench.crest_z_m };
    const depth = document.contour.bench.crest_z_m - document.contour.bench.toe_z_m + patternParams.subdrill_m;
    const toe = holeFromCollar(collar, depth, patternParams.angle_deg, patternParams.azimuth_deg);
    const hole: Hole = {
      id: `M-${manualHoleCounter}`,
      row: -1000,
      col: manualHoleCounter,
      collar,
      toe,
      diameter_mm: patternParams.diameter_mm,
      subdrill_m: patternParams.subdrill_m,
      kind: "production",
      source: "manual",
      enabled: true,
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

  function deleteSelected() {
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
      const result = await api.design.charge(document.holes, chargeRules, explosive);
      dispatch({ type: "SET_LOADS", loads: result.loads });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось рассчитать заряжание.");
    } finally {
      setChargeBusy(false);
    }
  }

  async function generateTie() {
    if (!document.holes.length) {
      setError("Сначала постройте сетку скважин.");
      return;
    }
    setTieBusy(true);
    setError("");
    try {
      const result = await api.design.tie(document.holes, tieScheme, tieParams);
      dispatch({ type: "SET_NETWORK", network: result.network });
      setAnalysis(null);
      setCurrentMs(0);
      setPlaying(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось построить схему коммутации.");
    } finally {
      setTieBusy(false);
    }
  }

  async function runAnalyze() {
    if (!document.network.starters.length) {
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
      const result = await api.design.analyze(designForAnalysis, isolineStepMs, 8.0, ppv);
      setAnalysis(result);
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

  function printPassport() {
    if (!document.design_id) return;
    window.open(api.design.passportUrl(document.design_id), "_blank");
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

  async function savePlan() {
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
      setSelected(new Set());
      setSelectedRow(null);
      setAnalysis(null);
      setCurrentMs(0);
      setPlaying(false);
      setCostResult(null);
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
      }
      await refreshPlans();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось удалить паспорт.");
    }
  }

  function newPlan() {
    dispatch({ type: "LOAD", design: emptyDesign() });
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
  }

  async function exportCsv() {
    if (!document.design_id) return;
    try {
      await api.design.exportCsv(document.design_id, `${document.name || "passport"}.csv`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось выгрузить CSV.");
    }
  }

  return (
    <div className="page-content">
      <div className="page-heading">
        <div><h1>Проектирование БВР</h1><p>Контур блока → сетка скважин → ручная правка</p></div>
        <span className="save-status">● {user.organization_name}</span>
      </div>
      {error && <div className="page-error" role="alert">{error}</div>}

      <div className="design-toolbar">
        <div className="mode-switch">
          <button className={mode === "contour" ? "active" : ""} onClick={() => setMode("contour")}>Контур</button>
          <button className={mode === "holes" ? "active" : ""} onClick={() => setMode("holes")}>Скважины</button>
          <button className={mode === "charge" ? "active" : ""} onClick={() => setMode("charge")}>Заряжание</button>
          <button className={mode === "tie" ? "active" : ""} onClick={() => setMode("tie")}>Коммутация</button>
          <button className={mode === "timing" ? "active" : ""} onClick={() => setMode("timing")}>Тайминг</button>
          <button className={mode === "3d" ? "active" : ""} onClick={() => setMode("3d")}>3D</button>
        </div>
        <div className="history-controls">
          <button onClick={() => dispatch({ type: "UNDO" })} disabled={!state.past.length} title="Отменить (Ctrl+Z)">↶ Отменить</button>
          <button onClick={() => dispatch({ type: "REDO" })} disabled={!state.future.length} title="Повторить (Ctrl+Shift+Z)">↷ Повторить</button>
        </div>
      </div>

      <SummaryPanel holes={document.holes} blockVolumeM3={blockVolumeM3} loads={document.loads.length ? document.loads : undefined} />

      <div className="design-grid">
        <div className="design-sidebar">
          {mode === "charge" ? (
            <ChargePanel
              rules={chargeRules}
              explosives={explosives}
              explosiveKey={explosiveKey}
              onExplosiveKeyChange={setExplosiveKey}
              onChange={(patch) => setChargeRules((prev) => ({ ...prev, ...patch }))}
              onCalculate={calculateCharge}
              busy={chargeBusy}
            />
          ) : mode === "tie" ? (
            <TiePanel
              scheme={tieScheme}
              params={tieParams}
              onSchemeChange={setTieScheme}
              onParamsChange={(patch) => setTieParams((prev) => ({ ...prev, ...patch }))}
              onGenerate={generateTie}
              busy={tieBusy}
            />
          ) : mode === "timing" ? (
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
          ) : mode === "3d" ? (
            <section className="panel">
              <header><b>3D-вид</b><span>06</span></header>
              <div className="panel-body">
                <small>
                  Просмотр контура блока и наклонных скважин в пространстве. Правка геометрии
                  выполняется на 2D-плане — здесь только вращение, зум и выбор скважины кликом.
                </small>
              </div>
            </section>
          ) : (
            <PatternPanel params={patternParams} onChange={(patch) => setPatternParams((prev) => ({ ...prev, ...patch }))} onGenerate={generatePattern} busy={patternBusy} />
          )}
          <PlansPanel
            plans={plans}
            currentDesignId={document.design_id}
            currentName={document.name}
            onNameChange={(name) => dispatch({ type: "SET_NAME", name })}
            onSave={savePlan}
            onOpen={openPlan}
            onDelete={deletePlan}
            onNew={newPlan}
            onExportCsv={exportCsv}
            onPrintPassport={printPassport}
            busy={saveBusy}
          />
          <CostPanel
            scenarioId={scenarioId}
            onScenarioChange={setScenarioId}
            onCalculate={calculateCost}
            busy={costBusy}
            result={costResult}
          />
        </div>
        <div className="design-main">
          {mode === "3d" ? (
            <Suspense fallback={<div className="scene3d-loading">Загружаем 3D-движок…</div>}>
              <Scene3D
                contour={document.contour}
                holes={document.holes}
                selected={selected}
                onSelectHole={onSelectHole3D}
              />
            </Suspense>
          ) : (
            <>
              <PlanCanvas
                contour={document.contour}
                holes={document.holes}
                mode={mode === "contour" ? "contour" : "holes"}
                selected={selected}
                onSelectedChange={setSelected}
                onContourChange={onContourChange}
                onToggleFreeFace={onToggleFreeFace}
                onMoveHoles={onMoveHoles}
                onAddHole={onAddHole}
                onDeleteHoles={deleteHoles}
                camera={camera}
                onCameraChange={setCamera}
                spacingHint={{ a: patternParams.spacing_a_m, b: patternParams.burden_b_m }}
                loadsById={mode === "charge" ? loadsById : undefined}
                network={mode === "tie" || mode === "timing" ? document.network : undefined}
                isolines={mode === "timing" && showIsolines ? analysis?.isolines : undefined}
                timesMs={mode === "timing" ? analysis?.times_ms : undefined}
                animationMs={mode === "timing" && analysis ? currentMs : undefined}
              />
              {mode === "charge" ? (
                <SectionView
                  contour={document.contour}
                  holes={document.holes}
                  loads={document.loads}
                  network={document.network}
                  warnings={analysis?.validation_warnings}
                  rowAzimuthDeg={patternParams.row_azimuth_deg}
                  selectedRow={selectedRow}
                  onSelectedRowChange={setSelectedRow}
                />
              ) : (
                <HoleTable
                  holes={document.holes}
                  selected={selected}
                  onSelectedChange={setSelected}
                  onUpdateHole={onUpdateHole}
                  onDeleteSelected={deleteSelected}
                />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
