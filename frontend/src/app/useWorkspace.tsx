import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
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
  User,
  WorkObject,
  WorkspaceSnapshot,
  WorkspaceState,
} from "../types";
import {
  normalizeReferenceRows,
  normalizeSnapshotPatch,
  normalizeSnapshotRows,
} from "./referenceRows";
import {
  isLatestObjectRequest,
  mergeWorkspaceAfterObjectSwitch,
  shouldRollbackOnError,
} from "./workspaceObjectSwitch";

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
  setActiveWorkObjectName: (name: string) => Promise<void>;
  save: () => Promise<void>;
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
  // Номер последнего запроса на смену объекта работ: ответ применяется,
  // только если запрос всё ещё последний (см. workspaceObjectSwitch.ts).
  const activeObjectRequestRef = useRef(0);
  // Хвост очереди PUT-запросов смены объекта: следующий встаёт после уже
  // отправленных, чтобы сервер получал их в порядке кликов (см. docstring
  // `setActiveWorkObjectName`), а не в порядке ответа сети.
  const activeObjectQueueRef = useRef<Promise<void>>(Promise.resolve());

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
      setSavedKey(JSON.stringify(normalized.snapshot));
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
    return JSON.stringify(state.snapshot) !== savedKey;
  }, [state, savedKey]);

  const updateSnapshot = useCallback((patch: Partial<WorkspaceSnapshot>) => {
    setState((prev) => (prev ? { ...prev, snapshot: { ...prev.snapshot, ...normalizeSnapshotPatch(patch) } } : prev));
  }, []);

  /** Смена объекта работ сохраняется сразу: снимок сценария не участвует,
   * поэтому «несохранённых изменений» после переключения не возникает.
   * Из ответа берём только настройки, справочники, предупреждения и цену
   * бурения — снимок остаётся локальным, иначе несохранённые правки
   * «Бурения» и «ФОТ» пропали бы при переключении (и `savedKey` не трогаем,
   * иначе они же стали бы выглядеть сохранёнными).
   * Если пользователь быстро переключает объекты, ответы могут прийти не
   * в том порядке, в котором ушли запросы — применяем только ответ на
   * последний из них; ответ на устаревший запрос молча игнорируем. При
   * ошибке последнего запроса возвращаем предыдущее имя объекта.
   *
   * Сами PUT-запросы идут через промис-очередь `activeObjectQueueRef`
   * (`queueRef.current = queueRef.current.then(run, run)`, как в
   * `useCalcInputsAutosave`): следующий отправляется на сервер только после
   * ответа на предыдущий. Без очереди быстрое A→B могло уйти на сервер
   * двумя параллельными PUT, и сервер иногда обрабатывал их не в порядке
   * кликов — тогда запись A, отправленная первой, но обработанная сервером
   * последней, обгоняла B, и рабочее пространство оставалось на объекте A,
   * хотя клиент (и пользователь) уже видел B. Игнорирование устаревших
   * ответов и откат при ошибке остаются как есть — очередь только
   * упорядочивает сами запросы. */
  const setActiveWorkObjectName = useCallback((name: string) => {
    const requestId = ++activeObjectRequestRef.current;
    let previousName: string | undefined;
    setState((prev) => {
      if (!prev) return prev;
      previousName = prev.settings.active_work_object_name;
      return { ...prev, settings: { ...prev.settings, active_work_object_name: name } };
    });
    setError("");
    const run = async () => {
      try {
        const next = await api.setActiveWorkObject(name);
        if (!isLatestObjectRequest(requestId, activeObjectRequestRef.current)) return;
        const normalized = { ...next, references: normalizeReferenceRows(next.references) };
        setState((prev) => {
          // Состояния ещё нет — применять ответ некуда: его снимок мы всё равно
          // не берём, а полное состояние поднимет `load()`.
          if (!prev) return prev;
          return mergeWorkspaceAfterObjectSwitch(prev, normalized);
        });
      } catch (reason) {
        if (shouldRollbackOnError(requestId, activeObjectRequestRef.current, previousName)) {
          const restoredName: string = previousName;
          setState((prev) =>
            prev ? { ...prev, settings: { ...prev.settings, active_work_object_name: restoredName } } : prev
          );
        }
        if (isLatestObjectRequest(requestId, activeObjectRequestRef.current)) {
          setError(reason instanceof Error ? reason.message : "Не удалось сменить объект работ.");
        }
      }
    };
    const task = activeObjectQueueRef.current.then(run, run);
    activeObjectQueueRef.current = task;
    return task;
  }, []);

  const save = useCallback(async () => {
    if (!state) return;
    setSaving(true);
    setError("");
    try {
      const next = await api.saveWorkspace({
        snapshot: state.snapshot,
        active_work_object_name: state.settings.active_work_object_name,
      });
      const normalized = {
        ...next,
        snapshot: normalizeSnapshotRows(next.snapshot),
        references: normalizeReferenceRows(next.references),
      };
      setState(normalized);
      setSavedKey(JSON.stringify(normalized.snapshot));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сохранить рабочее пространство.");
      throw reason;
    } finally {
      setSaving(false);
    }
  }, [state]);

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
    setActiveWorkObjectName,
    save,
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
