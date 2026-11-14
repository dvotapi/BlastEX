// Съёмка бурения (TASK-014, PR 5а): файл маркшейдера → точки → сопоставление
// со скважинами и оценка по допускам паспорта на бурение → «Применить к
// проекту» одним действием `APPLY_SURVEY` (один шаг отмены).
//
// Сервер ничего не сохраняет: чтение, оценка и применение — чистые запросы,
// результат кладёт в документ страница. Решения инженера (ручная привязка
// точки, пропуск точки, введённая глубина) живут здесь и уходят одинаково в
// оценку и в применение — в том числе на копии утверждённого проекта.
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
const COPY_FAILED = "Копия по съёмке не открыта — съёмка не применена.";

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

export type SurveyLoadOptions = { format?: SurveyFormat | ""; swapXy?: boolean };

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
  /** Скважины проекта — для ручной привязки точки. */
  holeIds: string[];
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

type Loaded = { file: File; fileName: string; sha256: string; format: SurveyFormat; formatChoice: SurveyFormat | ""; swapXy: boolean; readWarnings: string[] };
type Evaluation = { response: SurveyEvaluateResponse; signature: string };
type Decisions = { points: SurveyedPoint[]; manual: Record<string, string>; skip: string[] };

const NO_DECISIONS: Decisions = { points: [], manual: {}, skip: [] };

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

  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [decisions, setDecisions] = useState<Decisions>(NO_DECISIONS);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [surveyDate, setSurveyDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [applyWarnings, setApplyWarnings] = useState<string[] | null>(null);
  // Копия по съёмке: id копии, которую ждём в документе, чтобы применить на ней.
  const [pendingCopy, setPendingCopy] = useState<string | null>(null);
  const copying = useRef(false);
  const sequence = useRef(0);
  const loadedRef = useRef(loaded);
  loadedRef.current = loaded;
  const decisionsRef = useRef(decisions);
  decisionsRef.current = decisions;

  function reset() {
    sequence.current += 1;
    setLoaded(null);
    setDecisions(NO_DECISIONS);
    setEvaluation(null);
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
        points: next.points,
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

  function decide(change: (current: Decisions) => Decisions) {
    const next = change(decisionsRef.current);
    decisionsRef.current = next;
    setDecisions(next);
    setNotice("");
    void runEvaluate(next);
  }

  async function load(file: File, opts: SurveyLoadOptions = {}): Promise<void> {
    const own = ++sequence.current;
    setBusy(true);
    setError("");
    setNotice("");
    setApplyWarnings(null);
    try {
      const params: { format?: SurveyFormat; swapXy?: boolean } = {};
      if (opts.format) params.format = opts.format;
      if (opts.swapXy) params.swapXy = true;
      const read = await api.survey.read(file, params);
      if (own !== sequence.current) return;
      setLoaded({
        file,
        fileName: read.file_name || file.name,
        sha256: read.sha256,
        format: read.format,
        formatChoice: opts.format ?? "",
        swapXy: Boolean(opts.swapXy),
        readWarnings: read.warnings,
      });
      const next: Decisions = { points: read.points, manual: {}, skip: [] };
      decisionsRef.current = next;
      setDecisions(next);
      setEvaluation(null);
      await runEvaluate(next);
    } catch (reason) {
      if (own !== sequence.current) return;
      setError(message(reason, "Не удалось прочитать файл съёмки."));
      setBusy(false);
    }
  }

  async function setFormat(format: SurveyFormat | ""): Promise<void> {
    const current = loadedRef.current;
    if (current) await load(current.file, { format, swapXy: current.swapXy });
  }

  async function swap(): Promise<void> {
    const current = loadedRef.current;
    if (current) await load(current.file, { format: current.formatChoice, swapXy: !current.swapXy });
  }

  async function evaluate(): Promise<void> {
    if (!loadedRef.current) return;
    setNotice("");
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

  function setDepth(holeId: string, m: number | null) {
    const verdict = evaluation?.response.verdicts.find((item) => item.hole_id === holeId);
    if (!verdict) return;
    const line = verdict.point.line;
    decide((current) => ({
      ...current,
      points: current.points.map((point) => (point.line === line ? { ...point, depth_m: m } : point)),
    }));
  }

  /** Применить к документу `base` (черновику): ответ — только если документ тот же. */
  async function runApply(base: BlastDesign): Promise<void> {
    const current = loadedRef.current;
    if (!current) return;
    const signature = surveySignature(base);
    const { points, manual, skip: skipped } = decisionsRef.current;
    const charge = chargeRef.current();
    setBusy(true);
    setError("");
    try {
      const response = await api.survey.apply({
        design: base,
        design_id: base.design_id || undefined,
        points,
        manual,
        skip: skipped,
        file_name: current.fileName,
        file_sha256: current.sha256,
        survey_date: surveyDate,
        // Скважины сервер берёт из проекта: в параметрах зарядов они лишние.
        charge: charge ? { ...charge, holes: [] } : null,
      });
      const now = latest.current;
      if (now.design_id !== base.design_id || surveySignature(now) !== signature) {
        setError(SURVEY_CHANGED);
        return;
      }
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

  /** Документ тот же, по которому оценено; иначе — ошибка. */
  function evaluatedHere(): boolean {
    if (!evaluation) return false;
    if (surveySignature(latest.current) !== evaluation.signature) {
      setError(SURVEY_CHANGED);
      return false;
    }
    return true;
  }

  const { action, hint } = surveyAction(status);

  async function apply(): Promise<void> {
    if (action !== "apply" || busy || !evaluatedHere()) return;
    await runApply(latest.current);
  }

  async function copyBySurvey(): Promise<void> {
    if (action !== "copy" || busy || !evaluatedHere()) return;
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
    if (!copy) {
      copying.current = false;
      setBusy(false);
      setError(failure);
      return;
    }
    // Копия открывается страницей: применяем, когда она стала документом.
    setPendingCopy(copy.design_id);
  }

  useEffect(() => {
    if (pendingCopy === null || present.design_id !== pendingCopy) return;
    setPendingCopy(null);
    void runApply(present).finally(() => {
      copying.current = false;
    });
    // runApply читает остальное из ссылок.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [present, pendingCopy]);

  const rows = useMemo(() => (evaluation ? surveyRows(evaluation.response) : []), [evaluation]);
  const response = evaluation?.response ?? null;
  const warnings = applyWarnings ?? [...(loaded?.readWarnings ?? []), ...(response?.warnings ?? [])];
  const holeIds = useMemo(() => present.holes.map((hole) => hole.id), [present.holes]);

  return {
    fileName: loaded?.fileName ?? "",
    format: loaded?.format ?? null,
    formatChoice: loaded?.formatChoice ?? "",
    points: decisions.points,
    rows,
    tolerances: response?.tolerances ?? null,
    swapSuggested: Boolean(response?.swap_suggested),
    warnings,
    skipped: decisions.skip,
    holeIds,
    surveyDate,
    setSurveyDate,
    action,
    actionHint: hint,
    ready: Boolean(response && response.verdicts.length > 0),
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
