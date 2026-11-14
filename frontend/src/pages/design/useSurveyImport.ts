// Съёмка бурения (TASK-014, PR 5а): файл маркшейдера → точки → сопоставление
// со скважинами и оценка по допускам паспорта на бурение → «Применить к
// проекту» одним действием `APPLY_SURVEY` (один шаг отмены).
//
// Сервер ничего не сохраняет: чтение, оценка и применение — чистые запросы,
// результат кладёт в документ страница. Решения инженера (ручная привязка
// точки, пропуск точки, введённая глубина, колонки таблицы) живут здесь и
// уходят одинаково в оценку и в применение — в том числе на копии
// утверждённого проекта. После применения оценка повторяется по новому
// документу: таблица показывает то, что теперь в проекте.
//
// Применяется только к тому документу, по которому оценено: сменился проект
// между оценкой и «Применить» или пока шёл запрос — ошибка без dispatch
// (как `CHANGED_DURING_GEOLOGY` у подбора раскладки). Сверка — по значениям:
// «Сохранить» даёт новые объекты с теми же значениями.
import { useEffect, useMemo, useRef, useState, type Dispatch } from "react";
import { HttpError } from "../../api/client";
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
  SurveyedPoint,
} from "../../types/design";
import type { DesignAction, DesignState } from "./designReducer";
import { stableJson } from "./useLayoutSearch";

export const SURVEY_CHANGED = "Проект изменился, повторите оценку";
export const IN_REVIEW_HINT = "Верните проект в черновик";
export const CLOSED_HINT = "Проект закрыт: съёмку к нему не применить";
export const DATE_MISSING = "Укажите дату съёмки";
export const COPY_FAILED = "Копия по съёмке не открыта — съёмка не применена.";

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
  skipped: string[];
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
  /** Есть что применять. */
  ready: boolean;
  busy: boolean;
  error: string;
  /** Итог применения. */
  notice: string;
  load: (file: File, opts?: SurveyLoadOptions) => Promise<void>;
  setFormat: (format: SurveyFormat | "") => Promise<void>;
  swap: () => Promise<void>;
  evaluate: () => Promise<void>;
  setManual: (point: string, holeId: string) => void;
  skip: (point: string) => void;
  unskip: (point: string) => void;
  setDepth: (holeId: string, m: number | null) => void;
  apply: () => Promise<void>;
  copyBySurvey: () => Promise<void>;
}

/** Всё, от чего зависят оценка и применение: по нему сверяется документ. */
export function surveySignature(design: BlastDesign): string {
  return stableJson({
    design_id: design.design_id,
    lifecycle_status: design.lifecycle_status,
    contour: design.contour,
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

/** Заголовки таблицы из ответа 422 чтения (колонка не найдена). */
function headersOf(reason: unknown): string[] {
  if (!(reason instanceof HttpError) || !reason.detail || typeof reason.detail !== "object") return [];
  const headers = (reason.detail as { headers?: unknown }).headers;
  return Array.isArray(headers) ? headers.filter((item): item is string => typeof item === "string") : [];
}

/** Только заданные роли — их сервер читает как выбор человека. */
function chosenColumns(columns: SurveyColumns): SurveyColumns {
  return Object.fromEntries(Object.entries(columns).filter(([, header]) => header));
}

type Source = { file: File; formatChoice: SurveyFormat | ""; swapXy: boolean; columns: SurveyColumns };
type Loaded = { fileName: string; sha256: string; format: SurveyFormat; readWarnings: string[] };
type Evaluation = { response: SurveyEvaluateResponse; signature: string };
type Decisions = {
  /** Точки как в файле. */
  filePoints: SurveyedPoint[];
  /** Введённые глубины: номер строки → м. */
  entered: Record<number, number>;
  manual: Record<string, string>;
  skip: string[];
};

const NO_DECISIONS: Decisions = { filePoints: [], entered: {}, manual: {}, skip: [] };

/** Точки, которые уходят на сервер: из файла с введёнными глубинами. */
function effectivePoints(decisions: Decisions): SurveyedPoint[] {
  return decisions.filePoints.map((point) =>
    decisions.entered[point.line] !== undefined ? { ...point, depth_m: decisions.entered[point.line] } : point,
  );
}

export function useSurveyImport({
  state,
  dispatch,
  designId,
  status,
  chargeRequest,
  onFork,
  onApplied,
}: {
  state: DesignState;
  dispatch: Dispatch<DesignAction>;
  designId: string;
  status: string;
  /** Параметры расчёта зарядов страницы (как у «Рассчитать заряды»); нет ВВ — null. */
  chargeRequest: () => ChargeGenerateRequest | null;
  /** Копия сохранённого проекта, открытая черновиком; не вышло — null (причину показывает страница). */
  onFork: () => Promise<BlastDesign | null>;
  /** Съёмка легла в документ: страница сбрасывает свои результаты. */
  onApplied?: () => void;
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
  // После «Применить» — повторная оценка по новому документу (не по `base`).
  const reevaluateAfter = useRef<BlastDesign | null>(null);
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
    const base = latest.current;
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
      setEvaluation({ response, signature: surveySignature(base) });
    } catch (reason) {
      if (own === sequence.current) setError(message(reason, "Не удалось оценить съёмку."));
    } finally {
      if (own === sequence.current) setBusy(false);
    }
  }

  // «Применить» положило съёмку в документ — оценка заново, уже по нему.
  useEffect(() => {
    const base = reevaluateAfter.current;
    if (!base || present === base) return;
    reevaluateAfter.current = null;
    void runEvaluate(decisionsRef.current);
    // runEvaluate читает остальное из ссылок.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [present]);

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
      columns: chosenColumns(opts.columns ?? {}),
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

  function setColumn(role: string, header: string) {
    setColumns((current) => {
      const next = { ...current };
      if (header) next[role] = header;
      else delete next[role];
      return next;
    });
  }

  async function rereadColumns(): Promise<void> {
    const current = sourceRef.current;
    if (current) await load(current.file, { format: current.formatChoice, swapXy: current.swapXy, columns: columnsRef.current });
  }

  async function evaluate(): Promise<void> {
    if (!loadedRef.current) return;
    setNotice("");
    setApplyWarnings(null);
    await runEvaluate(decisionsRef.current);
  }

  function setManual(point: string, holeId: string) {
    decide((current) => {
      const manual = { ...current.manual };
      if (holeId) manual[point] = holeId;
      else delete manual[point];
      return { ...current, manual, skip: current.skip.filter((name) => name !== point) };
    });
  }

  function skip(point: string) {
    decide((current) => {
      const manual = { ...current.manual };
      delete manual[point];
      return { ...current, manual, skip: current.skip.includes(point) ? current.skip : [...current.skip, point] };
    });
  }

  function unskip(point: string) {
    decide((current) => ({ ...current, skip: current.skip.filter((name) => name !== point) }));
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
  async function runApply(base: BlastDesign): Promise<void> {
    const current = loadedRef.current;
    if (!current) return;
    const signature = surveySignature(base);
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
        file_name: current.fileName,
        file_sha256: current.sha256,
        survey_date: surveyDateRef.current,
        // Скважины сервер берёт из проекта: в параметрах зарядов они лишние.
        charge: charge ? { ...charge, holes: [] } : null,
      });
      const now = latest.current;
      if (now.design_id !== base.design_id || surveySignature(now) !== signature) {
        setError(SURVEY_CHANGED);
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
    if (surveySignature(latest.current) !== evaluation.signature) {
      setError(SURVEY_CHANGED);
      return false;
    }
    return true;
  }

  const { action, hint } = surveyAction(status);

  async function apply(): Promise<void> {
    if (action !== "apply" || busy || !applicable()) return;
    await runApply(latest.current);
  }

  async function copyBySurvey(): Promise<void> {
    if (action !== "copy" || busy || !applicable()) return;
    const run = ++copyRun.current;
    copying.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    let copy: BlastDesign | null = null;
    let failure = COPY_FAILED;
    try {
      copy = await onForkRef.current();
    } catch (reason) {
      failure = message(reason, COPY_FAILED);
    }
    // Пока создавалась копия, съёмку сбросили (открыли другой проект) — не применяем.
    if (run !== copyRun.current) return;
    if (!copy) {
      copying.current = false;
      setBusy(false);
      setError(failure);
      return;
    }
    // Страница открывает копию до ответа: на ближайшей отрисовке она — документ.
    setPendingCopy(copy.design_id);
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
    void runApply(present).finally(() => {
      if (run === copyRun.current) copying.current = false;
    });
    // runApply читает остальное из ссылок.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [present, pendingCopy]);

  const rows = useMemo(() => (evaluation ? surveyRows(evaluation.response) : []), [evaluation]);
  const points = useMemo(() => effectivePoints(decisions), [decisions]);
  const response = evaluation?.response ?? null;
  const warnings = applyWarnings ?? [...(loaded?.readWarnings ?? []), ...(response?.warnings ?? [])];
  const holeIds = useMemo(() => present.holes.map((hole) => hole.id), [present.holes]);

  return {
    fileName: loaded?.fileName ?? source?.file.name ?? "",
    format: loaded?.format ?? null,
    formatChoice: source?.formatChoice ?? "",
    points,
    rows,
    tolerances: response?.tolerances ?? null,
    swapSuggested: Boolean(response?.swap_suggested),
    warnings,
    skipped: decisions.skip,
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
    ready: Boolean(loaded && response && response.verdicts.length > 0),
    busy: busy || pendingCopy !== null,
    error,
    notice,
    load,
    setFormat,
    swap,
    evaluate,
    setManual,
    skip,
    unskip,
    setDepth,
    apply,
    copyBySurvey,
  };
}
