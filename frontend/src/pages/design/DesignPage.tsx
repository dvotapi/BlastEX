import { useEffect, useMemo, useReducer, useState } from "react";
import { api } from "../../api";
import { holeFromCollar, type Camera, type Vec2 } from "../../lib/geometry2d";
import type { BlastVariant, Explosive, User } from "../../types";
import {
  DEFAULT_CHARGE_RULES,
  DEFAULT_PATTERN_PARAMS,
  emptyDesign,
  type ChargeRules,
  type DesignSummary,
  type Hole,
  type HoleLoad,
  type PatternParams,
  type Point3,
} from "../../types/design";
import { ChargePanel } from "./ChargePanel";
import { designReducer, initDesignState } from "./designReducer";
import { HoleTable } from "./HoleTable";
import { PatternPanel } from "./PatternPanel";
import { PlanCanvas } from "./PlanCanvas";
import { PlansPanel } from "./PlansPanel";
import { SectionView } from "./SectionView";
import { SummaryPanel } from "./SummaryPanel";

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

  const [mode, setMode] = useState<"contour" | "holes" | "charge">("contour");
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

  function onContourVerticesChange(vertices: Point3[]) {
    dispatch({ type: "SET_CONTOUR_VERTICES", vertices });
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

  function deleteSelected() {
    if (!selected.size) return;
    dispatch({ type: "DELETE_HOLES", ids: Array.from(selected) });
    setSelected(new Set());
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
    setBlockVolumeM3(null);
    setSelected(new Set());
    setSelectedRow(null);
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
            busy={saveBusy}
          />
        </div>
        <div className="design-main">
          <PlanCanvas
            contour={document.contour}
            holes={document.holes}
            mode={mode === "charge" ? "holes" : mode}
            selected={selected}
            onSelectedChange={setSelected}
            onContourVerticesChange={onContourVerticesChange}
            onToggleFreeFace={onToggleFreeFace}
            onMoveHoles={onMoveHoles}
            onAddHole={onAddHole}
            camera={camera}
            onCameraChange={setCamera}
            spacingHint={{ a: patternParams.spacing_a_m, b: patternParams.burden_b_m }}
            loadsById={mode === "charge" ? loadsById : undefined}
          />
          {mode === "charge" ? (
            <SectionView
              contour={document.contour}
              holes={document.holes}
              loads={document.loads}
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
        </div>
      </div>
    </div>
  );
}
