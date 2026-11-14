// @vitest-environment jsdom
// Съёмка бурения (TASK-014, PR 5а): чтение, оценка и «Применить» на уровне
// страницы — настоящий редьюсер, сервер замокан.
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { useReducer, type Dispatch } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  emptyAsDrilled,
  emptyDesign,
  emptyHoleGeology,
  type BlastDesign,
  type ChargeGenerateRequest,
  type Hole,
  type SurveyApplyResponse,
  type SurveyEvaluateResponse,
  type SurveyReadResponse,
  type SurveyedPoint,
} from "../../types/design";
import { designReducer, initDesignState, type DesignAction } from "./designReducer";

const api = vi.hoisted(() => ({
  survey: { read: vi.fn(), evaluate: vi.fn(), apply: vi.fn() },
}));
vi.mock("../../api/endpoints", () => ({ api }));

import { HttpError } from "../../api/client";
import { COPY_FAILED, DATE_MISSING, DECISIONS_CHANGED, SURVEY_CHANGED, copyNotOpened, surveySignature, todayIso, useSurveyImport, type ForkResult } from "./useSurveyImport";

function hole(id: string, x: number): Hole {
  return {
    id,
    row: 0,
    col: 0,
    collar: { x, y: 5, z: 420 },
    toe: { x, y: 5, z: 408 },
    diameter_mm: 152,
    subdrill_m: 1,
    kind: "production",
    source: "generated",
    enabled: true,
    ...emptyHoleGeology(),
  };
}

function design(status: BlastDesign["lifecycle_status"] = "draft", id = "d1"): BlastDesign {
  return { ...emptyDesign(), design_id: id, name: "66", lifecycle_status: status, holes: [hole("1-01", 10), hole("1-02", 14)] };
}

const P1: SurveyedPoint = { name: "66-1-01", x: 10, y: 5, z: 420, depth_m: 12.1, line: 1 };
const P2: SurveyedPoint = { name: "7", x: 14.2, y: 5, z: 420, depth_m: null, line: 2 };
const R1: SurveyedPoint = { name: "R1", x: 40, y: 40, z: 421, line: 3 };

const READ: SurveyReadResponse = {
  points: [P1, P2, R1],
  format: "PNEZD_CSV",
  columns: {},
  warnings: ["Строка 9: нет координат — пропущена."],
  sha256: "abc",
  file_name: "66.csv",
};

const TOLERANCES = {
  depth_m: 0.3, collar_m: 0.3, angle_deg: 1, burden_pct: 5, spacing_pct: 5,
  source: "passport" as const, passport_no: "12", revision_no: 2, passport_design_id: "d1",
};

function evaluation(): SurveyEvaluateResponse {
  return {
    matches: [
      { hole_id: "1-01", point: P1, by: "name", issue: "" },
      { hole_id: "1-02", point: P2, by: "nearest", issue: "" },
      { hole_id: null, point: R1, by: "", issue: "unmatched_point" },
    ],
    verdicts: [
      { hole_id: "1-01", point: P1, codes: ["ok"], offset_m: 0, depth_delta_m: 0, required_length_m: 12.1, angle_delta_deg: null, burden_delta_pct: null, spacing_delta_pct: null, unchanged: true },
      { hole_id: "1-02", point: P2, codes: ["offset", "no_depth"], offset_m: 0.2, depth_delta_m: null, required_length_m: 12.1, angle_delta_deg: null, burden_delta_pct: null, spacing_delta_pct: null, unchanged: false },
    ],
    tolerances: TOLERANCES,
    swap_suggested: false,
    block: "66",
    warnings: [],
  };
}

function applied(): SurveyApplyResponse {
  return {
    holes: [hole("1-01", 10), hole("1-02", 14.2)],
    loads: null,
    as_drilled_holes: [emptyAsDrilled(hole("1-02", 14.2))],
    survey_application: { applied_at: "", survey_date: "", file_name: "66.csv", file_sha256: "abc", actor: "", counts: { ok: 1 } },
    changed_ids: ["1-02"],
    warnings: ["Заряды пересчитаны у 1 скважины."],
  };
}

type ForkFn = (dispatch: Dispatch<DesignAction>) => Promise<ForkResult | null>;

/** Живые (несохранённые) параметры сетки страницы — как `designWithParams`. */
let liveParams: Record<string, unknown> | null = null;
/** Параметры заряжания страницы на момент вызова `chargeRequest`. */
let liveCharge: ChargeGenerateRequest | null = null;

function withLive(design: BlastDesign): BlastDesign {
  return liveParams ? { ...design, pattern_params: { ...design.pattern_params, ...liveParams } } : design;
}

function setup(initial: BlastDesign, fork: ForkFn = async () => null, swallow: DesignAction["type"][] = []) {
  const actions: DesignAction[] = [];
  const onFork = vi.fn();
  const view = renderHook(() => {
    const [state, rawDispatch] = useReducer(designReducer, initial, initDesignState);
    const dispatch = (action: DesignAction) => {
      actions.push(action);
      if (!swallow.includes(action.type)) rawDispatch(action);
    };
    onFork.mockImplementation(() => fork(rawDispatch));
    const survey = useSurveyImport({
      state,
      dispatch,
      designId: state.present.design_id,
      status: state.present.lifecycle_status,
      chargeRequest: () => liveCharge,
      onFork,
      withParams: withLive,
    });
    return { state, dispatch: rawDispatch, survey };
  });
  return { view, actions, onFork };
}

const FILE = new File(["66-1-01,5,10,420"], "66.csv");

beforeEach(() => {
  liveParams = null;
  liveCharge = null;
  api.survey.read.mockReset().mockResolvedValue(READ);
  api.survey.evaluate.mockReset().mockResolvedValue(evaluation());
  api.survey.apply.mockReset().mockResolvedValue(applied());
});
afterEach(cleanup);

async function loaded(initial: BlastDesign, fork?: ForkFn, swallow: DesignAction["type"][] = []) {
  const ctx = setup(initial, fork, swallow);
  await act(() => ctx.view.result.current.survey.load(FILE));
  return ctx;
}

describe("useSurveyImport", () => {
  it("файл → чтение → оценка: строки, допуски, предупреждения чтения", async () => {
    const { view } = await loaded(design());
    expect(api.survey.read).toHaveBeenCalledWith(FILE, {});
    expect(api.survey.evaluate).toHaveBeenCalledTimes(1);
    const body = api.survey.evaluate.mock.calls[0][0];
    expect(body.points).toEqual([P1, P2, R1]);
    expect(body.design_id).toBe("d1");
    const survey = view.result.current.survey;
    expect(survey.rows.map((row) => [row.holeId, row.point?.name, row.issue])).toEqual([
      ["1-01", "66-1-01", ""],
      ["1-02", "7", ""],
      [null, "R1", "unmatched_point"],
    ]);
    expect(survey.rows[1].verdict?.codes).toEqual(["offset", "no_depth"]);
    expect(survey.tolerances?.passport_no).toBe("12");
    expect(survey.warnings).toContain("Строка 9: нет координат — пропущена.");
  });

  it("выбор скважины для точки уходит в manual, пропуск — в skip: по строке файла, а не по имени", async () => {
    const { view } = await loaded(design());
    await act(async () => view.result.current.survey.setManual(3, "1-02"));
    expect(api.survey.evaluate).toHaveBeenLastCalledWith(expect.objectContaining({ manual: { 3: "1-02" }, skip: [] }));
    await act(async () => view.result.current.survey.skip(3));
    expect(api.survey.evaluate).toHaveBeenLastCalledWith(expect.objectContaining({ manual: {}, skip: [3] }));
    expect(view.result.current.survey.skipped).toEqual([R1]);
    await act(async () => view.result.current.survey.unskip(3));
    expect(api.survey.evaluate).toHaveBeenLastCalledWith(expect.objectContaining({ skip: [] }));
  });

  it("две точки с одним именем: пропуск одной не трогает другую", async () => {
    const twin: SurveyedPoint = { ...P1, x: 10.1, line: 4 };
    api.survey.read.mockResolvedValue({ ...READ, points: [P1, P2, R1, twin] });
    const { view } = await loaded(design());
    await act(async () => view.result.current.survey.skip(4));
    const body = api.survey.evaluate.mock.calls.at(-1)![0];
    expect(body.skip).toEqual([4]);
    expect(view.result.current.survey.skipped).toEqual([twin]);
  });

  it("привязку по имени можно снять: «без скважины» — пустой id в manual", async () => {
    const { view } = await loaded(design());
    await act(async () => view.result.current.survey.detach(1));
    expect(api.survey.evaluate).toHaveBeenLastCalledWith(expect.objectContaining({ manual: { 1: "" } }));
    await act(async () => view.result.current.survey.setManual(1, ""));
    expect(api.survey.evaluate).toHaveBeenLastCalledWith(expect.objectContaining({ manual: {} }));
  });

  it("введённая глубина уходит в точку скважины, оценка пересчитывается", async () => {
    const { view } = await loaded(design());
    await act(async () => view.result.current.survey.setDepth("1-02", 11.8));
    const body = api.survey.evaluate.mock.calls.at(-1)![0];
    expect(body.points.find((p: SurveyedPoint) => p.line === 2).depth_m).toBe(11.8);
    expect(body.points.find((p: SurveyedPoint) => p.line === 1).depth_m).toBe(12.1);
  });

  it("«Применить» — одно APPLY_SURVEY с ответом сервера и одна запись отмены", async () => {
    const { view, actions } = await loaded(design());
    await act(async () => view.result.current.survey.setManual(3, "1-02"));
    await act(() => view.result.current.survey.apply());
    expect(api.survey.apply).toHaveBeenCalledTimes(1);
    const body = api.survey.apply.mock.calls[0][0];
    expect(body.block).toBe("66");
    expect(body).toMatchObject({ design_id: "d1", manual: { 3: "1-02" }, skip: [], file_name: "66.csv", file_sha256: "abc", charge: null });
    const surveyActions = actions.filter((action) => action.type === "APPLY_SURVEY");
    expect(surveyActions).toHaveLength(1);
    expect(surveyActions[0]).toMatchObject({ changed_ids: ["1-02"], loads: null });
    const state = view.result.current.state;
    expect(state.present.holes[1].collar.x).toBe(14.2);
    expect(state.present.survey_applications).toHaveLength(1);
    expect(state.past).toHaveLength(1);
    expect(view.result.current.survey.warnings).toContain("Заряды пересчитаны у 1 скважины.");
    expect(view.result.current.survey.error).toBe("");
  });

  it("проект изменился после оценки — ошибка, без запроса и без dispatch", async () => {
    const { view, actions } = await loaded(design());
    act(() => view.result.current.dispatch({ type: "SET_NAME", name: "66 правка" }));
    act(() => view.result.current.dispatch({ type: "SET_HOLES", holes: [hole("1-02", 14)] }));
    await act(() => view.result.current.survey.apply());
    expect(view.result.current.survey.error).toBe(SURVEY_CHANGED);
    expect(api.survey.apply).not.toHaveBeenCalled();
    expect(actions.some((action) => action.type === "APPLY_SURVEY")).toBe(false);
  });

  it("проект изменился, пока шёл запрос «Применить», — ответ не применяется", async () => {
    let release: (value: SurveyApplyResponse) => void = () => undefined;
    api.survey.apply.mockImplementation(() => new Promise((resolve) => (release = resolve)));
    const { view, actions } = await loaded(design());
    let pending: Promise<void> = Promise.resolve();
    act(() => {
      pending = view.result.current.survey.apply();
    });
    act(() => view.result.current.dispatch({ type: "SET_HOLES", holes: [hole("1-02", 14)] }));
    await act(async () => {
      release(applied());
      await pending;
    });
    expect(view.result.current.survey.error).toBe(SURVEY_CHANGED);
    expect(actions.some((action) => action.type === "APPLY_SURVEY")).toBe(false);
  });

  it("утверждённый: «Копия по съёмке» — onFork, затем apply на копии с теми же решениями", async () => {
    const fork: ForkFn = async (dispatch) => {
      const copy = { ...design("draft", "d2"), parent_design_id: "d1" } as BlastDesign;
      dispatch({ type: "LOAD", design: copy });
      return { copy, opened: true };
    };
    const { view, actions, onFork } = await loaded(design("approved"), fork);
    await act(async () => view.result.current.survey.setManual(3, "1-02"));
    await act(async () => view.result.current.survey.skip(2));
    await act(() => view.result.current.survey.copyBySurvey());
    await waitFor(() => expect(api.survey.apply).toHaveBeenCalledTimes(1));
    expect(onFork).toHaveBeenCalledTimes(1);
    const body = api.survey.apply.mock.calls[0][0];
    expect(body.design_id).toBe("d2");
    // Копия называется «… · по съёмке»: блок — тот, по которому сопоставлялись имена при оценке.
    expect(body.block).toBe("66");
    expect(body.design.lifecycle_status).toBe("draft");
    expect(body.manual).toEqual({ 3: "1-02" });
    expect(body.skip).toEqual([2]);
    expect(body.points).toEqual([P1, P2, R1]);
    await waitFor(() => expect(actions.filter((action) => action.type === "APPLY_SURVEY")).toHaveLength(1));
    expect(view.result.current.state.present.design_id).toBe("d2");
    expect(view.result.current.state.present.survey_applications).toHaveLength(1);
  });

  it("копия не создана — ошибка, «Применить» не вызывается", async () => {
    const { view, onFork } = await loaded(design("approved"), async () => {
      throw new Error("Сначала сохраните паспорт.");
    });
    await act(() => view.result.current.survey.copyBySurvey());
    expect(onFork).toHaveBeenCalledTimes(1);
    expect(view.result.current.survey.error).toBe("Сначала сохраните паспорт.");
    expect(api.survey.apply).not.toHaveBeenCalled();
  });

  it("на проверке и в утверждённом «Применить к проекту» запрос не шлёт", async () => {
    for (const status of ["in_review", "approved"] as const) {
      api.survey.apply.mockClear();
      const { view } = await loaded(design(status));
      await act(() => view.result.current.survey.apply());
      expect(api.survey.apply).not.toHaveBeenCalled();
      cleanup();
    }
  });

  it("при swap_suggested «Поменять» перечитывает файл с перестановкой X и Y", async () => {
    api.survey.evaluate.mockResolvedValueOnce({ ...evaluation(), swap_suggested: true });
    const { view } = await loaded(design());
    expect(view.result.current.survey.swapSuggested).toBe(true);
    await act(() => view.result.current.survey.swap());
    expect(api.survey.read).toHaveBeenLastCalledWith(FILE, { swapXy: true });
  });

  it("после «Применить» оценка повторяется по новому документу", async () => {
    const { view } = await loaded(design());
    const before = api.survey.evaluate.mock.calls.length;
    await act(() => view.result.current.survey.apply());
    await waitFor(() => expect(api.survey.evaluate.mock.calls.length).toBe(before + 1));
    const body = api.survey.evaluate.mock.calls.at(-1)![0];
    expect(body.design.holes[1].collar.x).toBe(14.2);
    expect(body.design.survey_applications).toHaveLength(1);
    await waitFor(() => expect(view.result.current.survey.busy).toBe(false));
    // Оценено по новому документу — «Применить» снова сверяется с ним, а не ловушка.
    api.survey.apply.mockClear();
    await act(() => view.result.current.survey.apply());
    expect(api.survey.apply).toHaveBeenCalledTimes(1);
  });

  it("дата съёмки — сегодня; пустая дата не даёт применить", async () => {
    const { view } = await loaded(design());
    expect(view.result.current.survey.surveyDate).toBe(todayIso());
    act(() => view.result.current.survey.setSurveyDate(""));
    await act(() => view.result.current.survey.apply());
    expect(view.result.current.survey.error).toBe(DATE_MISSING);
    expect(api.survey.apply).not.toHaveBeenCalled();
  });

  it("ручную привязку можно снять", async () => {
    const { view } = await loaded(design());
    await act(async () => view.result.current.survey.setManual(2, "1-01"));
    expect(api.survey.evaluate).toHaveBeenLastCalledWith(expect.objectContaining({ manual: { 2: "1-01" } }));
    await act(async () => view.result.current.survey.setManual(2, ""));
    expect(api.survey.evaluate).toHaveBeenLastCalledWith(expect.objectContaining({ manual: {} }));
  });

  it("введённую глубину можно сменить и снять — в точке снова глубина файла", async () => {
    const { view } = await loaded(design());
    await act(async () => view.result.current.survey.setDepth("1-02", 11.8));
    expect(view.result.current.survey.enteredDepths).toEqual({ 2: 11.8 });
    await act(async () => view.result.current.survey.setDepth("1-02", null));
    expect(view.result.current.survey.enteredDepths).toEqual({});
    const body = api.survey.evaluate.mock.calls.at(-1)![0];
    expect(body.points.find((p: SurveyedPoint) => p.line === 2).depth_m).toBeNull();
  });

  it("колонка таблицы не найдена — заголовки файла, выбор вручную и чтение заново", async () => {
    const detail = { message: "В таблице не найдена колонка «север». Укажите её вручную.", headers: ["Пикет", "Вост", "Сев"] };
    api.survey.read.mockRejectedValueOnce(new HttpError(detail.message, 422, detail));
    const { view } = setup(design());
    await act(() => view.result.current.survey.load(FILE));
    const survey = view.result.current.survey;
    expect(survey.error).toBe(detail.message);
    expect(survey.headers).toEqual(["Пикет", "Вост", "Сев"]);
    expect(survey.fileName).toBe("66.csv");
    act(() => view.result.current.survey.setColumn("name", "Пикет"));
    act(() => view.result.current.survey.setColumn("east", "Вост"));
    act(() => view.result.current.survey.setColumn("north", "Сев"));
    act(() => view.result.current.survey.setColumn("z", ""));
    await act(() => view.result.current.survey.rereadColumns());
    // «— нет —» — роль выключена: уходит пустой строкой, сервер её не ищет сам.
    expect(api.survey.read).toHaveBeenLastCalledWith(FILE, { columns: { name: "Пикет", east: "Вост", north: "Сев", z: "" } });
    expect(view.result.current.survey.error).toBe("");
    expect(view.result.current.survey.rows).toHaveLength(3);
  });

  it("копия не стала документом — ошибка, «Применить» не вызывается", async () => {
    const { view } = await loaded(design("approved"), async () => ({ copy: { ...design("draft", "d2") }, opened: true }));
    await act(() => view.result.current.survey.copyBySurvey());
    await waitFor(() => expect(view.result.current.survey.error).toBe(COPY_FAILED));
    expect(api.survey.apply).not.toHaveBeenCalled();
    expect(view.result.current.survey.busy).toBe(false);
  });

  it("копия создана, но страница сменилась — ошибка называет копию, «Применить» не вызывается", async () => {
    const copy = { ...design("draft", "d2"), name: "Блок 66 · по съёмке" } as BlastDesign;
    const { view } = await loaded(design("approved"), async () => ({ copy, opened: false }));
    await act(() => view.result.current.survey.copyBySurvey());
    expect(view.result.current.survey.error).toBe(copyNotOpened("Блок 66 · по съёмке"));
    expect(view.result.current.survey.error).toBe(
      "Копия «Блок 66 · по съёмке» создана, но не открыта — откройте её в списке проектов и примените съёмку там.",
    );
    expect(api.survey.apply).not.toHaveBeenCalled();
    expect(view.result.current.survey.busy).toBe(false);
  });

  it("«Поменять» → «Прочитать заново»: колонки уже с перестановкой, X/Y второй раз не меняются", async () => {
    api.survey.read
      .mockResolvedValueOnce({ ...READ, format: "TABLE", headers: ["№", "E", "N"], columns: { name: "№", east: "E", north: "N" } })
      .mockResolvedValueOnce({ ...READ, format: "TABLE", headers: ["№", "E", "N"], columns: { name: "№", east: "N", north: "E" } })
      .mockResolvedValue({ ...READ, format: "TABLE", headers: ["№", "E", "N"], columns: { name: "№", east: "N", north: "E" } });
    const { view } = setup(design());
    await act(() => view.result.current.survey.load(FILE));
    await act(() => view.result.current.survey.swap());
    expect(api.survey.read).toHaveBeenLastCalledWith(FILE, { swapXy: true });
    await act(() => view.result.current.survey.rereadColumns());
    expect(api.survey.read).toHaveBeenLastCalledWith(FILE, { columns: { name: "№", east: "N", north: "E" } });
    // Следующее «Поменять» — снова одна перестановка, от прочитанных колонок.
    await act(() => view.result.current.survey.swap());
    expect(api.survey.read).toHaveBeenLastCalledWith(FILE, { swapXy: true, columns: { name: "№", east: "N", north: "E" } });
  });

  it("«Применить» не сменило документ — повторной оценки нет и потом", async () => {
    const { view } = await loaded(design(), undefined, ["APPLY_SURVEY"]);
    await act(() => view.result.current.survey.apply());
    await waitFor(() => expect(view.result.current.survey.busy).toBe(false));
    const calls = api.survey.evaluate.mock.calls.length;
    act(() => view.result.current.dispatch({ type: "SET_NAME", name: "66 правка" }));
    await act(async () => undefined);
    expect(api.survey.evaluate.mock.calls.length).toBe(calls);
  });

  it("«— нет —» у найденной сервером колонки выключает её и при следующих чтениях", async () => {
    const found = { name: "№", east: "E", north: "N", z: "Z" };
    api.survey.read
      .mockResolvedValueOnce({ ...READ, format: "TABLE", headers: ["№", "E", "N", "Z"], columns: found })
      .mockResolvedValue({ ...READ, format: "TABLE", headers: ["№", "E", "N", "Z"], columns: { ...found, z: "" } });
    const { view } = setup(design());
    await act(() => view.result.current.survey.load(FILE));
    act(() => view.result.current.survey.setColumn("z", ""));
    await act(() => view.result.current.survey.rereadColumns());
    expect(api.survey.read).toHaveBeenLastCalledWith(FILE, { columns: { ...found, z: "" } });
    expect(view.result.current.survey.columns.z).toBe("");
    // «Поменять» после этого — Z по-прежнему выключена; нетронутые роли не уходят.
    await act(() => view.result.current.survey.swap());
    expect(api.survey.read).toHaveBeenLastCalledWith(FILE, { swapXy: true, columns: { ...found, z: "" } });
  });

  it("решения сменились, а оценка не удалась — «Применить» не шлёт новые решения под старую таблицу", async () => {
    const { view } = await loaded(design());
    expect(view.result.current.survey.ready).toBe(true);
    api.survey.evaluate.mockRejectedValueOnce(new Error("Сервер недоступен"));
    await act(async () => view.result.current.survey.setManual(3, "1-02"));
    expect(view.result.current.survey.error).toBe("Сервер недоступен");
    expect(view.result.current.survey.ready).toBe(false);
    expect(view.result.current.survey.stale).toBe(true);
    await act(() => view.result.current.survey.apply());
    expect(api.survey.apply).not.toHaveBeenCalled();
    expect(view.result.current.survey.error).toBe(DECISIONS_CHANGED);
    // Оценка заново — по новым решениям — снова даёт применить.
    await act(() => view.result.current.survey.evaluate());
    expect(view.result.current.survey.stale).toBe(false);
    await act(() => view.result.current.survey.apply());
    expect(api.survey.apply).toHaveBeenCalledTimes(1);
    expect(api.survey.apply.mock.calls[0][0].manual).toEqual({ 3: "1-02" });
  });

  it("подпись проекта учитывает поверхности и параметры сетки — сервер считает по ним", () => {
    const base = design();
    const roof = { ...base, surfaces: { ...base.surfaces, top: { kind: "top" } } } as unknown as BlastDesign;
    const params = { ...base, pattern_params: { ...base.pattern_params, depth_m: 11 } };
    expect(surveySignature(roof)).not.toBe(surveySignature(base));
    expect(surveySignature(params)).not.toBe(surveySignature(base));
  });

  it("параметры сетки сменились после оценки — «Применить» просит повторить оценку", async () => {
    const { view } = await loaded(design());
    act(() => view.result.current.dispatch({ type: "SET_PATTERN_PARAMS", params: { subdrill_m: 1.5 } }));
    await act(() => view.result.current.survey.apply());
    expect(view.result.current.survey.error).toBe(SURVEY_CHANGED);
    expect(api.survey.apply).not.toHaveBeenCalled();
  });

  it("оценка и «Применить» — по документу с живыми параметрами сетки страницы", async () => {
    liveParams = { depth_m: 11 };
    const { view } = await loaded(design());
    expect(api.survey.evaluate.mock.calls[0][0].design.pattern_params.depth_m).toBe(11);
    await act(() => view.result.current.survey.apply());
    expect(api.survey.apply.mock.calls[0][0].design.pattern_params.depth_m).toBe(11);
    // Параметры на странице сменились после оценки — подпись другая, применять нельзя.
    liveParams = { depth_m: 12 };
    view.rerender();
    api.survey.apply.mockClear();
    await act(() => view.result.current.survey.apply());
    expect(api.survey.apply).not.toHaveBeenCalled();
  });

  it("решения сменились, пока шёл «Применить», — ответ не применяется", async () => {
    let release: (value: SurveyApplyResponse) => void = () => undefined;
    api.survey.apply.mockImplementation(() => new Promise((resolve) => (release = resolve)));
    const { view, actions } = await loaded(design());
    let pending: Promise<void> = Promise.resolve();
    act(() => {
      pending = view.result.current.survey.apply();
    });
    await act(async () => view.result.current.survey.setDepth("1-02", 11.8));
    await act(async () => {
      release(applied());
      await pending;
    });
    expect(actions.some((action) => action.type === "APPLY_SURVEY")).toBe(false);
    expect(view.result.current.survey.error).toBe(DECISIONS_CHANGED);
  });

  it("параметры заряжания сменились, пока шёл «Применить», — ответ (заряды по старым) не применяется", async () => {
    const explosive = { key: "e100", name: "Э-100", density_t_m3: 1.2, power_mj_kg: 3.8 } as unknown as ChargeGenerateRequest["explosive"];
    liveCharge = { holes: [], rules: { stemming_m: 3 }, explosive };
    let release: (value: SurveyApplyResponse) => void = () => undefined;
    api.survey.apply.mockImplementation(() => new Promise((resolve) => (release = resolve)));
    const { view, actions } = await loaded(design());
    let pending: Promise<void> = Promise.resolve();
    act(() => {
      pending = view.result.current.survey.apply();
    });
    liveCharge = { holes: [], rules: { stemming_m: 4 }, explosive };
    await act(async () => {
      release(applied());
      await pending;
    });
    expect(actions.some((action) => action.type === "APPLY_SURVEY")).toBe(false);
    expect(view.result.current.survey.error).toBe(SURVEY_CHANGED);
  });
});
