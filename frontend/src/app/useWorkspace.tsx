import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../api/endpoints";
import type {
  CatalogItem,
  DrillRig,
  FixedAssetDepreciation,
  FixedCostItem,
  JobPosition,
  LaborAssignment,
  Rock,
  ScenarioListItem,
  TeamReferences,
  User,
  WorkObject,
  WorkspaceSnapshot,
  WorkspaceState,
} from "../types";
import {
  normalizeReferencePatch,
  normalizeReferenceRows,
  normalizeSnapshotPatch,
  normalizeSnapshotRows,
} from "./referenceRows";

/** Контекст последнего расчёта на вкладке «Расчёт» — для кнопок
 * «Подставить объём/объёмы из расчёта БВР» на вкладках «Бурение» и «ФОТ». */
export type BlastCalcContext = {
  blockVolumeM3: number;
  additionalHolesPct: number;
  drillingFootageM: number;
  totalHoles: number;
  crownMm: number;
};

type WorkspaceContextValue = {
  loading: boolean;
  error: string;
  state: WorkspaceState | null;
  scenarios: ScenarioListItem[];
  activeScenario: ScenarioListItem | null;
  dirty: boolean;
  saving: boolean;
  blastContext: BlastCalcContext | null;
  setBlastContext: (ctx: BlastCalcContext | null) => void;
  updateSnapshot: (patch: Partial<WorkspaceSnapshot>) => void;
  updateReferences: (patch: Partial<TeamReferences>) => void;
  setActiveWorkObjectName: (name: string) => void;
  save: () => Promise<void>;
  switchScenario: (scenarioId: string) => Promise<void>;
  reload: () => Promise<void>;
  canEdit: boolean;
};

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({ user, children }: { user: User; children: ReactNode }) {
  const [state, setState] = useState<WorkspaceState | null>(null);
  const [savedKey, setSavedKey] = useState<string>("");
  const [scenarios, setScenarios] = useState<ScenarioListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [blastContext, setBlastContext] = useState<BlastCalcContext | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [ws, sc] = await Promise.all([api.workspace(), api.scenarios()]);
      const normalized = {
        ...ws,
        snapshot: normalizeSnapshotRows(ws.snapshot),
        references: normalizeReferenceRows(ws.references),
      };
      setState(normalized);
      setSavedKey(JSON.stringify([normalized.snapshot, normalized.references, normalized.settings.active_work_object_name]));
      setScenarios(sc);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить рабочее пространство.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load, user.organization_id]);

  const dirty = useMemo(() => {
    if (!state) return false;
    return JSON.stringify([state.snapshot, state.references, state.settings.active_work_object_name]) !== savedKey;
  }, [state, savedKey]);

  const updateSnapshot = useCallback((patch: Partial<WorkspaceSnapshot>) => {
    setState((prev) => (prev ? { ...prev, snapshot: { ...prev.snapshot, ...normalizeSnapshotPatch(patch) } } : prev));
  }, []);

  const updateReferences = useCallback((patch: Partial<TeamReferences>) => {
    setState((prev) => (prev ? { ...prev, references: { ...prev.references, ...normalizeReferencePatch(patch) } } : prev));
  }, []);

  const setActiveWorkObjectName = useCallback((name: string) => {
    setState((prev) => (prev ? { ...prev, settings: { ...prev.settings, active_work_object_name: name } } : prev));
  }, []);

  const save = useCallback(async () => {
    if (!state) return;
    setSaving(true);
    setError("");
    try {
      const next = await api.saveWorkspace({
        snapshot: state.snapshot,
        references: state.references,
        active_work_object_name: state.settings.active_work_object_name,
      });
      const normalized = {
        ...next,
        snapshot: normalizeSnapshotRows(next.snapshot),
        references: normalizeReferenceRows(next.references),
      };
      setState(normalized);
      setSavedKey(JSON.stringify([normalized.snapshot, normalized.references, normalized.settings.active_work_object_name]));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сохранить рабочее пространство.");
      throw reason;
    } finally {
      setSaving(false);
    }
  }, [state]);

  const switchScenario = useCallback(async (scenarioId: string) => {
    setError("");
    try {
      const next = await api.switchScenario(scenarioId);
      const normalized = {
        ...next,
        snapshot: normalizeSnapshotRows(next.snapshot),
        references: normalizeReferenceRows(next.references),
      };
      setState(normalized);
      setSavedKey(JSON.stringify([normalized.snapshot, normalized.references, normalized.settings.active_work_object_name]));
      setBlastContext(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось переключить сценарий.");
    }
  }, []);

  const activeScenario = useMemo(
    () => scenarios.find((s) => s.id === state?.settings.active_scenario_id) ?? null,
    [scenarios, state]
  );

  const canEdit = user.role === "admin" || user.role === "reference_editor";

  const value: WorkspaceContextValue = {
    loading,
    canEdit,
    error,
    state,
    scenarios,
    activeScenario,
    dirty,
    saving,
    blastContext,
    setBlastContext,
    updateSnapshot,
    updateReferences,
    setActiveWorkObjectName,
    save,
    switchScenario,
    reload: load,
  };

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used within WorkspaceProvider");
  return ctx;
}

export type { CatalogItem, DrillRig, FixedAssetDepreciation, FixedCostItem, JobPosition, LaborAssignment, Rock, WorkObject };
