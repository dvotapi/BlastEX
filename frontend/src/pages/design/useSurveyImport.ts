// Съёмка бурения (TASK-014, PR 5а): файл маркшейдера → точки → сопоставление
// со скважинами и оценка по допускам паспорта на бурение → «Применить к
// проекту» одним действием `APPLY_SURVEY` (один шаг отмены).
//
// Сервер ничего не сохраняет: чтение, оценка и применение — чистые запросы,
// результат кладёт в документ страница. Решения инженера (ручная привязка
// точки, «без скважины», пропуск точки, введённая глубина — по строке файла
// точки, а не по имени; колонки таблицы) живут здесь и
// уходят одинаково в оценку и в применение — в том числе на копии
// утверждённого проекта. После применения оценка повторяется по новому
// документу: таблица показывает то, что теперь в проекте.
//
// Применяется только к тому документу, по которому оценено: сменился проект
// между оценкой и «Применить» или пока шёл запрос — ошибка без dispatch
// (как `CHANGED_DURING_GEOLOGY` у подбора раскладки). Сверка — по значениям:
// «Сохранить» даёт новые объекты с теми же значениями.
import { useEffect, useMemo, useRef, useState, type Dispatch } from "react";
import { api } from "../../api/endpoints";
import { normalizeLifecycleStatus } from "../../lib/lifecycle";
import type {
  BlastDesign,
  ChargeGenerateRequest,
  SurveyColumns,
  SurveyEvaluateResponse,
  SurveyFormat,
  SurveyHoleVerdict,
  SurveyMatchBy,
  SurveyMatchIssue,
  SurveyTolerances,
  SurfaceModel,
  SurveyedPoint,
} from "../../types/design";
import type { DesignAction, DesignState } from "./designReducer";
import { headersOf } from "./SurveyColumnsPicker";
import { tinFingerprint } from "./useHoleRecompute";
import { stableJson } from "./useLayoutSearch";

export const SURVEY_CHANGED = "Проект изменился, повторите оценку";
export const DECISIONS_CHANGED = "Решения изменились — повторите оценку";
export const IN_REVIEW_HINT = "Верните проект в черновик";
export const CLOSED_HINT = "Проект закрыт: съёмку к нему не применить";
export const DATE_MISSING = "Укажите дату съёмки";
export const COPY_FAILED = "Копия по съёмке не открыта — съёмка не применена.";

/** Копия создана на сервере, но пока она создавалась, открыли другой проект. */
export function copyNotOpened(name: string): string {
  return `Копия «${name}» создана, но не открыта — откройте её в списке проектов и примените съёмку там.`;
}

/** Итог «Создать копию»: копия на сервере и открыла ли её страница. */
export type ForkResult = { copy: BlastDesign; opened: boolean };

/** Строка таблицы сопоставления: скважина, её точка и оценка. */
export type SurveyRow = {
  key: string;
  holeId: string | null;
  point: SurveyedPoint | null;
  by: SurveyMatchBy;
  issue: SurveyMatchIssue;
  /** Оценка по допускам — только у сопоставленной без спора скважины. */
  verdict: SurveyHoleVerdict | null;
};

/** Что делает главная кнопка при этом статусе проекта. */
export type SurveyAction = "apply" | "copy" | "blocked";

export type SurveyLoadOptions = { format?: SurveyFormat | ""; swapXy?: boolean; columns?: SurveyColumns };

export interface SurveyImportView {
  fileName: string;
  /** Формат, которым прочитан файл. */
  format: SurveyFormat | null;
  /** Формат, выбранный вручную; пусто — определяется сам. */
  formatChoice: SurveyFormat | "";
  points: SurveyedPoint[];
  rows: SurveyRow[];
  tolerances: SurveyTolerances | null;
  swapSuggested: boolean;
  warnings: string[];
  /** Пропущенные точки (решение — по строке файла). */
  skipped: SurveyedPoint[];
  /** Глубины, введённые вручную: номер строки файла → м. */
  enteredDepths: Record<number, number>;
  /** Скважины проекта — для ручной привязки точки. */
  holeIds: string[];
  /** Заголовки колонок таблицы; пусто — не таблица. */
  headers: string[];
  /** Колонки таблицы: роль → заголовок файла (найденные сервером и выбранные вручную). */
  columns: SurveyColumns;
  setColumn: (role: string, header: string) => void;
  /** Прочитать файл заново с выбранными колонками. */
  rereadColumns: () => Promise<void>;
  surveyDate: string;
  setSurveyDate: (value: string) => void;
  action: SurveyAction;
  /** Почему кнопка недоступна; иначе пусто. */
  actionHint: string;
  /** Есть что применять: оценка — по текущему проекту и решениям. */
  ready: boolean;
  /** Таблица оценки — не по текущим решениям инженера. */
  stale: boolean;
  busy: boolean;
  error: string;
  /** Итог применения. */
  notice: string;
  load: (file: File, opts?: SurveyLoadOptions) => Promise<void>;
  setFormat: (format: SurveyFormat | "") => Promise<void>;
  swap: () => Promise<void>;
  evaluate: () => Promise<void>;
  /** Привязать точку строки `line` к скважине; пустой id — снять ручное решение. */
  setManual: (line: number, holeId: string) => void;
  /** Точка строки `line` — «без скважины»: не сопоставляется ни по имени, ни по близости. */
  detach: (line: number) => void;
  skip: (line: number) => void;
  unskip: (line: number) => void;
  setDepth: (holeId: string, m: number | null) => void;
  apply: () => Promise<void>;
  copyBySurvey: () => Promise<void>;
}

/** Поверхность в подписи: сеть — отпечатком по содержимому, точки и линии — числом (TIN строится из них). */
function surfaceKey(surface: SurfaceModel | null | undefined): unknown {
  if (!surface) return null;
  const { tin, points, polylines, ...rest } = surface;
  return { ...rest, tin: tin ? tinFingerprint(tin) : null, points: points?.length ?? 0, polylines: polylines?.length ?? 0 };
}

/**
 * Всё, от чего зависят оценка и применение: по нему сверяется документ. Сервер
 * ставит скважины по кровле и подошве и по параметрам сетки (своя глубина вида) —
 * поверхности и `pattern_params` входят в подпись.
 */
export function surveySignature(design: BlastDesign): string {
  const surfaces = design.surfaces ?? {};
  return stableJson({
    design_id: design.design_id,
    lifecycle_status: design.lifecycle_status,
    contour: design.contour,
    surfaces: Object.fromEntries(
      Object.entries(surfaces).map(([kind, surface]) => [kind, surfaceKey(surface as SurfaceModel | null)]),
    ),
    pattern_params: design.pattern_params ?? {},
    holes: design.holes,
    loads: design.loads,
    as_drilled_holes: design.as_drilled_holes,
    survey_applications: design.survey_applications ?? [],
  });
}

/** Сегодняшняя дата по местному времени, ГГГГ-ММ-ДД. */
export function todayIso(now = new Date()): string {
  const two = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${two(now.getMonth() + 1)}-${two(now.getDate())}`;
}

function surveyAction(status: string): { action: SurveyAction; hint: string } {
  const normalized = normalizeLifecycleStatus(status);
  if (normalized === "draft") return { action: "apply", hint: "" };
  if (normalized === "approved" || normalized === "executed") return { action: "copy", hint: "" };
  return { action: "blocked", hint: normalized === "in_review" ? IN_REVIEW_HINT : CLOSED_HINT };
}

/** Строки таблицы: у скважины с двумя точками — только строки точек («две точки»). */
export function surveyRows(response: SurveyEvaluateResponse): SurveyRow[] {
  const verdicts = new Map(response.verdicts.map((verdict) => [verdict.hole_id, verdict]));
  const disputed = new Set(response.matches.filter((match) => match.issue === "duplicate_point").map((match) => match.hole_id));
  return response.matches
    .filter((match) => !(match.issue === "missing_point" && disputed.has(match.hole_id)))
    .map((match, index) => ({
      key: `${match.hole_id ?? ""}|${match.point?.line ?? ""}|${index}`,
      holeId: match.hole_id,
      point: match.point,
      by: match.by,
      issue: match.issue,
      verdict: !match.issue && match.hole_id ? verdicts.get(match.hole_id) ?? null : null,
    }));
}

function message(reason: unknown, fallback: string): string {
  return reason instanceof Error && reason.message ? reason.message : fallback;
}

type Source = { file: File; formatChoice: SurveyFormat | ""; swapXy: boolean; columns: SurveyColumns };
type Loaded = { fileName: string; sha256: string; format: SurveyFormat; readWarnings: string[] };
/** Оценка и то, по чему она сделана: проект (`signature`) и решения инженера (`decisions`). */
type Evaluation = { response: SurveyEvaluateResponse; signature: string; decisions: string };
type Decisions = {
  /** Точки как в файле. */
  filePoints: SurveyedPoint[];
  /** Введённые глубины: номер строки → м. */
  entered: Record<number, number>;
  /** Строка точки → id скважины; пусто — «без скважины». */
  manual: Record<number, string>;
  /** Строки пропущенных точек. */
  skip: number[];
};

const NO_DECISIONS: Decisions = { filePoints: [], entered: {}, manual: {}, skip: [] };

/** Точки, которые уходят на сервер: из файла с введёнными глубинами. */
function effectivePoints(decisions: Decisions): SurveyedPoint[] {
  return decisions.filePoints.map((point) =>
    decisions.entered[point.line] !== undefined ? { ...point, depth_m: decisions.entered[point.line] } : point,
  );
}

/** Отпечаток решений инженера: точки с введёнными глубинами, привязки, пропуски. */
function decisionsSignature(decisions: Decisions): string {
  return stableJson({ points: effectivePoints(decisions), manual: decisions.manual, skip: decisions.skip });
}

export function useSurveyImport({
  state,
  dispatch,
  designId,
  status,
  chargeRequest,
  onFork,
  onApplied,
  withParams,
}: {
  state: DesignState;
  dispatch: Dispatch<DesignAction>;
  designId: string;
  status: string;
  /** Параметры расчёта зарядов страницы (как у «Рассчитать заряды»); нет ВВ — null. */
  chargeRequest: () => ChargeGenerateRequest | null;
  /** Копия сохранённого проекта, открытая черновиком; не вышло — null (причину показывает страница). */
  onFork: () => Promise<ForkResult | null>;
  /** Съёмка легла в документ: страница сбрасывает свои результаты. */
  onApplied?: () => void;
  /**
   * Документ для сервера: с живыми (ещё не сохранёнными) параметрами страницы,
   * как у пересчёта по кровле (`designWithParams`). По нему же — подпись проекта.
   */
  withParams?: (design: BlastDesign) => BlastDesign;
}): SurveyImportView {
  const present = state.present;
  const latest = useRef(present);
  latest.current = present;
  const chargeRef = useRef(chargeRequest);
  chargeRef.current = chargeRequest;
  const onForkRef = useRef(onFork);
  onForkRef.current = onFork;
  const onAppliedRef = useRef(onApplied);
  onAppliedRef.current = onApplied;
  const withParamsRef = useRef(withParams);
  withParamsRef.current = withParams;
  /** Документ так, как его увидит сервер. */
  const forServer = (design: BlastDesign): BlastDesign => (withParamsRef.current ? withParamsRef.current(design) : design);

  const [source, setSource] = useState<Source | null>(null);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [columns, setColumns] = useState<SurveyColumns>({});
  const [decisions, setDecisions] = useState<Decisions>(NO_DECISIONS);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [surveyDate, setSurveyDate] = useState(() => todayIso());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [applyWarnings, setApplyWarnings] = useState<string[] | null>(null);
  // Копия по съёмке: id копии, на которой применить, когда она стала документом.
  const [pendingCopy, setPendingCopy] = useState<string | null>(null);
  const copying = useRef(false);
  const copyRun = useRef(0);
  // Блок оценки, по которой нажата «Копия по съёмке»: применение на копии — с ним.
  const copyBlock = useRef("");
  // После «Применить» — повторная оценка по новому документу (не по `base`).
  const reevaluateAfter = useRef<BlastDesign | null>(null);
  // Отметка «применено»: эффект повторной оценки сверяет документ после dispatch.
  const [appliedTick, setAppliedTick] = useState(0);
  const sequence = useRef(0);
  const sourceRef = useRef(source);
  sourceRef.current = source;
  const loadedRef = useRef(loaded);
  loadedRef.current = loaded;
  const decisionsRef = useRef(decisions);
  decisionsRef.current = decisions;
  const columnsRef = useRef(columns);
  columnsRef.current = columns;
  const surveyDateRef = useRef(surveyDate);
  surveyDateRef.current = surveyDate;

  function reset() {
    sequence.current += 1;
    copyRun.current += 1;
    copying.current = false;
    reevaluateAfter.current = null;
    setPendingCopy(null);
    setSource(null);
    setLoaded(null);
    setHeaders([]);
    setColumns({});
    setDecisions(NO_DECISIONS);
    setEvaluation(null);
    setBusy(false);
    setError("");
    setNotice("");
    setApplyWarnings(null);
  }

  // Открыли другой проект — съёмка прежнего к нему не относится. Первое
  // сохранение нового проекта (id появился) и копия по съёмке её не сбрасывают.
  const shownFor = useRef(designId);
  useEffect(() => {
    const previous = shownFor.current;
    shownFor.current = designId;
    if (previous && previous !== designId && !copying.current) reset();
  }, [designId]);

  async function runEvaluate(next: Decisions): Promise<void> {
    const own = ++sequence.current;
    const base = forServer(latest.current);
    setBusy(true);
    setError("");
    try {
      const response = await api.survey.evaluate({
        design: base,
        design_id: base.design_id || undefined,
        points: effectivePoints(next),
        manual: next.manual,
        skip: next.skip,
      });
      if (own !== sequence.current) return;
      setEvaluation({ response, signature: surveySignature(base), decisions: decisionsSignature(next) });
    } catch (reason) {
      if (own === sequence.current) setError(message(reason, "Не удалось оценить съёмку."));
    } finally {
      if (own === sequence.current) setBusy(false);
    }
  }

  // «Применить» положило съёмку в документ — оценка заново, уже по нему.
  useEffect(() => {
    const base = reevaluateAfter.current;
    if (!base) return;
    reevaluateAfter.current = null;
    // Документ не сменился — оценка прежняя, повторять нечего.
    if (present !== base) void runEvaluate(decisionsRef.current);
    // runEvaluate читает остальное из ссылок.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [present, appliedTick]);

  function decide(change: (current: Decisions) => Decisions) {
    const next = change(decisionsRef.current);
    decisionsRef.current = next;
    setDecisions(next);
    setNotice("");
    setApplyWarnings(null);
    void runEvaluate(next);
  }

  async function load(file: File, opts: SurveyLoadOptions = {}): Promise<void> {
    const own = ++sequence.current;
    const next: Source = {
      file,
      formatChoice: opts.format ?? "",
      swapXy: Boolean(opts.swapXy),
      // Пустая строка — роль выключена человеком («— нет —»): сервер её не ищет.
      columns: { ...(opts.columns ?? {}) },
    };
    setSource(next);
    setBusy(true);
    setError("");
    setNotice("");
    setApplyWarnings(null);
    try {
      const params: { format?: SurveyFormat; swapXy?: boolean; columns?: SurveyColumns } = {};
      if (next.formatChoice) params.format = next.formatChoice;
      if (next.swapXy) params.swapXy = true;
      if (Object.keys(next.columns).length) params.columns = next.columns;
      const read = await api.survey.read(file, params);
      if (own !== sequence.current) return;
      setLoaded({ fileName: read.file_name || file.name, sha256: read.sha256, format: read.format, readWarnings: read.warnings });
      setHeaders(read.headers ?? []);
      setColumns(read.columns ?? {});
      const decided: Decisions = { filePoints: read.points, entered: {}, manual: {}, skip: [] };
      decisionsRef.current = decided;
      setDecisions(decided);
      setEvaluation(null);
      await runEvaluate(decided);
    } catch (reason) {
      if (own !== sequence.current) return;
      // Колонка таблицы не найдена — заголовки файла для выбора вручную.
      setLoaded(null);
      setEvaluation(null);
      setDecisions(NO_DECISIONS);
      decisionsRef.current = NO_DECISIONS;
      const fileHeaders = headersOf(reason);
      setHeaders(fileHeaders);
      if (fileHeaders.length) setColumns(next.columns);
      setError(message(reason, "Не удалось прочитать файл съёмки."));
      setBusy(false);
    }
  }

  async function setFormat(format: SurveyFormat | ""): Promise<void> {
    const current = sourceRef.current;
    // Колонки — свои у каждого формата: при смене формата их находит сервер.
    if (current) await load(current.file, { format, swapXy: current.swapXy });
  }

  async function swap(): Promise<void> {
    const current = sourceRef.current;
    if (current) await load(current.file, { format: current.formatChoice, swapXy: !current.swapXy, columns: current.columns });
  }

  /** «— нет —» (`header` = "") — роль выключена, а не «найди сам». */
  function setColumn(role: string, header: string) {
    setColumns((current) => ({ ...current, [role]: header }));
  }

  async function rereadColumns(): Promise<void> {
    const current = sourceRef.current;
    // Колонки уже несут перестановку X/Y («Поменять»): вторая перестановка сервером
    // отразила бы точки обратно.
    if (current) await load(current.file, { format: current.formatChoice, swapXy: false, columns: columnsRef.current });
  }

  async function evaluate(): Promise<void> {
    if (!loadedRef.current) return;
    setNotice("");
    setApplyWarnings(null);
    await runEvaluate(decisionsRef.current);
  }

  /** Решение по точке строки `line`: id скважины, "" — «без скважины», null — снять решение. */
  function bind(line: number, holeId: string | null) {
    decide((current) => {
      const manual = { ...current.manual };
      if (holeId === null) delete manual[line];
      else manual[line] = holeId;
      return { ...current, manual, skip: current.skip.filter((item) => item !== line) };
    });
  }

  function setManual(line: number, holeId: string) {
    bind(line, holeId || null);
  }

  function detach(line: number) {
    bind(line, "");
  }

  function skip(line: number) {
    decide((current) => {
      const manual = { ...current.manual };
      delete manual[line];
      return { ...current, manual, skip: current.skip.includes(line) ? current.skip : [...current.skip, line] };
    });
  }

  function unskip(line: number) {
    decide((current) => ({ ...current, skip: current.skip.filter((item) => item !== line) }));
  }

  /** Глубина скважины вручную; null — снять введённую (глубина — как в файле). */
  function setDepth(holeId: string, m: number | null) {
    const verdict = evaluation?.response.verdicts.find((item) => item.hole_id === holeId);
    if (!verdict) return;
    const line = verdict.point.line;
    decide((current) => {
      const entered = { ...current.entered };
      if (m === null) delete entered[line];
      else entered[line] = m;
      return { ...current, entered };
    });
  }

  /** Применить к документу `base` (черновику): ответ — только если документ тот же. */
  /**
   * `block` — блок, по которому сопоставлялись имена при оценке, которую видел
   * инженер: копия по съёмке называется иначе («… · по съёмке»), и сервер вывел
   * бы из имени другой префикс.
   */
  async function runApply(document: BlastDesign, block: string): Promise<void> {
    const current = loadedRef.current;
    if (!current) return;
    const base = forServer(document);
    const signature = surveySignature(base);
    // Решения, под которые ушёл запрос: сменились, пока он шёл, — ответ не тот.
    const decided = decisionsSignature(decisionsRef.current);
    const { manual, skip: skipped } = decisionsRef.current;
    const charge = chargeRef.current();
    setBusy(true);
    setError("");
    try {
      const response = await api.survey.apply({
        design: base,
        design_id: base.design_id || undefined,
        points: effectivePoints(decisionsRef.current),
        manual,
        skip: skipped,
        ...(block ? { block } : {}),
        file_name: current.fileName,
        file_sha256: current.sha256,
        survey_date: surveyDateRef.current,
        // Скважины сервер берёт из проекта: в параметрах зарядов они лишние.
        charge: charge ? { ...charge, holes: [] } : null,
      });
      const now = latest.current;
      if (now.design_id !== base.design_id || surveySignature(forServer(now)) !== signature) {
        setError(SURVEY_CHANGED);
        return;
      }
      if (decisionsSignature(decisionsRef.current) !== decided) {
        setError(DECISIONS_CHANGED);
        return;
      }
      reevaluateAfter.current = now;
      dispatch({
        type: "APPLY_SURVEY",
        holes: response.holes,
        loads: response.loads,
        as_drilled_holes: response.as_drilled_holes,
        survey_application: response.survey_application,
        changed_ids: response.changed_ids,
      });
      setAppliedTick((tick) => tick + 1);
      setApplyWarnings(response.warnings);
      setNotice(`Съёмка применена: изменено скважин — ${response.changed_ids.length}.`);
      onAppliedRef.current?.();
    } catch (reason) {
      setError(message(reason, "Не удалось применить съёмку."));
    } finally {
      setBusy(false);
    }
  }

  /** Можно применять: оценено по этому документу и дата съёмки задана. */
  function applicable(): boolean {
    if (!evaluation) return false;
    if (!surveyDateRef.current) {
      setError(DATE_MISSING);
      return false;
    }
    if (surveySignature(forServer(latest.current)) !== evaluation.signature) {
      setError(SURVEY_CHANGED);
      return false;
    }
    // Оценка после смены решений не удалась — таблица прежняя, а решения новые.
    if (decisionsSignature(decisionsRef.current) !== evaluation.decisions) {
      setError(DECISIONS_CHANGED);
      return false;
    }
    return true;
  }

  const { action, hint } = surveyAction(status);

  async function apply(): Promise<void> {
    if (action !== "apply" || busy || !applicable()) return;
    await runApply(latest.current, evaluation?.response.block ?? "");
  }

  async function copyBySurvey(): Promise<void> {
    if (action !== "copy" || busy || !applicable()) return;
    const run = ++copyRun.current;
    copying.current = true;
    copyBlock.current = evaluation?.response.block ?? "";
    setBusy(true);
    setError("");
    setNotice("");
    let fork: ForkResult | null = null;
    let failure = COPY_FAILED;
    try {
      fork = await onForkRef.current();
    } catch (reason) {
      failure = message(reason, COPY_FAILED);
    }
    // Пока создавалась копия, съёмку сбросили (открыли другой проект) — не применяем.
    if (run !== copyRun.current) return;
    if (!fork || !fork.opened) {
      copying.current = false;
      setBusy(false);
      // Копия на сервере есть, но страница уже на другом проекте — сказать, где она.
      setError(fork ? copyNotOpened(fork.copy.name) : failure);
      return;
    }
    // Страница открывает копию до ответа: на ближайшей отрисовке она — документ.
    setPendingCopy(fork.copy.design_id);
  }

  useEffect(() => {
    if (pendingCopy === null) return;
    setPendingCopy(null);
    const run = copyRun.current;
    if (present.design_id !== pendingCopy) {
      // Документ — не копия: применять не к чему.
      copying.current = false;
      setBusy(false);
      setError(COPY_FAILED);
      return;
    }
    void runApply(present, copyBlock.current).finally(() => {
      if (run === copyRun.current) copying.current = false;
    });
    // runApply читает остальное из ссылок.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [present, pendingCopy]);

  const rows = useMemo(() => (evaluation ? surveyRows(evaluation.response) : []), [evaluation]);
  const points = useMemo(() => effectivePoints(decisions), [decisions]);
  const response = evaluation?.response ?? null;
  // Показанная таблица — не по текущим решениям (оценка ещё идёт или не удалась).
  const stale = Boolean(evaluation && decisionsSignature(decisions) !== evaluation.decisions);
  const warnings = applyWarnings ?? [...(loaded?.readWarnings ?? []), ...(response?.warnings ?? [])];
  const holeIds = useMemo(() => present.holes.map((hole) => hole.id), [present.holes]);
  const skipped = useMemo(
    () =>
      decisions.skip
        .map((line) => points.find((point) => point.line === line))
        .filter((point): point is SurveyedPoint => point !== undefined),
    [decisions.skip, points],
  );

  return {
    fileName: loaded?.fileName ?? source?.file.name ?? "",
    format: loaded?.format ?? null,
    formatChoice: source?.formatChoice ?? "",
    points,
    rows,
    tolerances: response?.tolerances ?? null,
    swapSuggested: Boolean(response?.swap_suggested),
    warnings,
    skipped,
    enteredDepths: decisions.entered,
    holeIds,
    headers,
    columns,
    setColumn,
    rereadColumns,
    surveyDate,
    setSurveyDate,
    action,
    actionHint: hint,
    ready: Boolean(loaded && response && response.verdicts.length > 0 && !stale),
    stale,
    busy: busy || pendingCopy !== null,
    error,
    notice,
    load,
    setFormat,
    swap,
    evaluate,
    setManual,
    detach,
    skip,
    unskip,
    setDepth,
    apply,
    copyBySurvey,
  };
}
