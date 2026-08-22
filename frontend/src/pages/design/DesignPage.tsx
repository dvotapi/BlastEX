import { useEffect, useReducer, useState } from "react";
import { api } from "../../api";
import { holeFromCollar, type Camera, type Vec2 } from "../../lib/geometry2d";
import type { BlastVariant, User } from "../../types";
import { DEFAULT_PATTERN_PARAMS, emptyDesign, type DesignSummary, type Hole, type PatternParams, type Point3 } from "../../types/design";
import { designReducer, initDesignState } from "./designReducer";
import { HoleTable } from "./HoleTable";
import { PatternPanel } from "./PatternPanel";
import { PlanCanvas } from "./PlanCanvas";
import { PlansPanel } from "./PlansPanel";
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

  const [mode, setMode] = useState<"contour" | "holes">("contour");
  const [camera, setCamera] = useState<Camera>({ x: 0, y: 0, scale: 6 });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [patternParams, setPatternParams] = useState<PatternParams>(DEFAULT_PATTERN_PARAMS);
  const [blockVolumeM3, setBlockVolumeM3] = useState<number | null>(null);
  const [plans, setPlans] = useState<DesignSummary[]>([]);
  const [patternBusy, setPatternBusy] = useState(false);
  const [saveBusy, setSaveBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { refreshPlans(); }, []);

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

  async function savePlan() {
    setSaveBusy(true);
    setError("");
    try {
      const toSave = { ...document, pattern_params: patternParams as unknown as Record<string, unknown> };
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
      setBlockVolumeM3(null);
      setSelected(new Set());
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
    setBlockVolumeM3(null);
    setSelected(new Set());
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
        </div>
        <div className="history-controls">
          <button onClick={() => dispatch({ type: "UNDO" })} disabled={!state.past.length} title="Отменить (Ctrl+Z)">↶ Отменить</button>
          <button onClick={() => dispatch({ type: "REDO" })} disabled={!state.future.length} title="Повторить (Ctrl+Shift+Z)">↷ Повторить</button>
        </div>
      </div>

      <SummaryPanel holes={document.holes} blockVolumeM3={blockVolumeM3} />

      <div className="design-grid">
        <div className="design-sidebar">
          <PatternPanel params={patternParams} onChange={(patch) => setPatternParams((prev) => ({ ...prev, ...patch }))} onGenerate={generatePattern} busy={patternBusy} />
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
            mode={mode}
            selected={selected}
            onSelectedChange={setSelected}
            onContourVerticesChange={onContourVerticesChange}
            onToggleFreeFace={onToggleFreeFace}
            onMoveHoles={onMoveHoles}
            onAddHole={onAddHole}
            camera={camera}
            onCameraChange={setCamera}
            spacingHint={{ a: patternParams.spacing_a_m, b: patternParams.burden_b_m }}
          />
          <HoleTable
            holes={document.holes}
            selected={selected}
            onSelectedChange={setSelected}
            onUpdateHole={onUpdateHole}
            onDeleteSelected={deleteSelected}
          />
        </div>
      </div>
    </div>
  );
}
