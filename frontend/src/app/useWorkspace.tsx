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

export const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

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
  // Последнее имя объекта, которое сервер подтвердил ответом (успешным
  // `PUT /workspace/active-object` или `PUT /workspace/snapshot`) — а не то,
  // что сейчас оптимистично показано на экране. Именно на него откатываемся
  // при ошибке: локально показанное имя могло быть ещё не подтверждённым
  // предположением от предыдущего, тоже неудавшегося переключения (тогда
  // откат к нему оставил бы клиента с именем, которого сервер никогда не
  // видел). Обновляется на `load()` и на каждый успешный ответ обоих
  // мутирующих запросов ниже — независимо от того, «последний» ли это
  // запрос: пока очередь общая (`workspaceQueueRef`), сервер обрабатывает их
  // строго по порядку, и любой успешный ответ отражает состояние сервера на
  // момент до следующего запроса в очереди.
  const confirmedObjectNameRef = useRef<string | null>(null);
  // Общая очередь мутирующих запросов рабочего пространства — смены объекта
  // (`setActiveWorkObjectName`) и сохранения снимка (`save`): следующий
  // уходит на сервер только после ответа на предыдущий, независимо от того,
  // какой из двух это был. Без общей очереди сохранение и переключение
  // объекта могли уйти параллельно двумя PUT, и сервер иногда обрабатывал их
  // не в порядке кликов — тогда более ранний запрос обгонял более поздний, и
  // рабочее пространство оставалось не с тем объектом, что показывал клиент.
  const workspaceQueueRef = useRef<Promise<void>>(Promise.resolve());

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
      confirmedObjectNameRef.current = normalized.settings.active_work_object_name;
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
   * ошибке последнего запроса возвращаем последнее подтверждённое сервером
   * имя (`confirmedObjectNameRef`), а не то, что было оптимистично показано
   * перед этим запросом: если и оно тоже было лишь неудавшимся
   * предположением (пользователь успел кликнуть дважды подряд, и оба запроса
   * упали), откат к нему оставил бы клиента с именем, которого сервер
   * никогда не подтверждал.
   *
   * Сами PUT-запросы идут через общую промис-очередь `workspaceQueueRef`
   * (`queueRef.current = queueRef.current.then(run, run)`, как в
   * `useCalcInputsAutosave`) вместе с `save()`: следующий мутирующий запрос
   * отправляется на сервер только после ответа на предыдущий, кем бы из
   * двух он ни был. Без общей очереди быстрое переключение объекта могло
   * уйти на сервер параллельно с сохранением снимка, и сервер иногда
   * обрабатывал их не в порядке кликов — тогда более ранний запрос обгонял
   * более поздний, и рабочее пространство оставалось не с тем объектом,
   * что показывал клиент. Игнорирование устаревших ответов и откат при
   * ошибке остаются как есть — очередь только упорядочивает сами запросы. */
  const setActiveWorkObjectName = useCallback((name: string) => {
    const requestId = ++activeObjectRequestRef.current;
    setState((prev) =>
      prev ? { ...prev, settings: { ...prev.settings, active_work_object_name: name } } : prev
    );
    setError("");
    const run = async () => {
      try {
        const next = await api.setActiveWorkObject(name);
        confirmedObjectNameRef.current = next.settings.active_work_object_name;
        if (!isLatestObjectRequest(requestId, activeObjectRequestRef.current)) return;
        const normalized = { ...next, references: normalizeReferenceRows(next.references) };
        setState((prev) => {
          // Состояния ещё нет — применять ответ некуда: его снимок мы всё равно
          // не берём, а полное состояние поднимет `load()`.
          if (!prev) return prev;
          return mergeWorkspaceAfterObjectSwitch(prev, normalized);
        });
      } catch (reason) {
        const confirmedName = confirmedObjectNameRef.current ?? undefined;
        if (shouldRollbackOnError(requestId, activeObjectRequestRef.current, confirmedName)) {
          const restoredName: string = confirmedName;
          setState((prev) =>
            prev ? { ...prev, settings: { ...prev.settings, active_work_object_name: restoredName } } : prev
          );
        }
        if (isLatestObjectRequest(requestId, activeObjectRequestRef.current)) {
          setError(reason instanceof Error ? reason.message : "Не удалось сменить объект работ.");
        }
      }
    };
    const task = workspaceQueueRef.current.then(run, run);
    workspaceQueueRef.current = task;
    return task;
  }, []);

  /** Сохранение снимка идёт через ту же общую очередь `workspaceQueueRef`,
   * что и смена активного объекта (см. docstring `setActiveWorkObjectName`):
   * запрос сохраняет `active_work_object_name`, который сервер считает
   * активным, поэтому сохранение и переключение объекта, случившиеся почти
   * одновременно, должны обрабатываться сервером в порядке кликов, а не
   * параллельно — иначе более ранний из двух запросов мог обработаться
   * позже и вернуть активный объект на сервере к прежнему значению. */
  const save = useCallback(() => {
    if (!state) return Promise.resolve();
    setSaving(true);
    setError("");
    const { snapshot, settings } = state;
    const run = async () => {
      try {
        const next = await api.saveWorkspace({
          snapshot,
          active_work_object_name: settings.active_work_object_name,
        });
        confirmedObjectNameRef.current = next.settings.active_work_object_name;
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
    };
    const task = workspaceQueueRef.current.then(run, run);
    workspaceQueueRef.current = task;
    return task;
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
