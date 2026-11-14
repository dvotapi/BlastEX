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
import { COPY_FAILED, DATE_MISSING, SURVEY_CHANGED, todayIso, useSurveyImport } from "./useSurveyImport";

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

type ForkFn = (dispatch: Dispatch<DesignAction>) => Promise<BlastDesign | null>;

function setup(initial: BlastDesign, fork: ForkFn = async () => null) {
  const actions: DesignAction[] = [];
  const onFork = vi.fn();
  const view = renderHook(() => {
    const [state, rawDispatch] = useReducer(designReducer, initial, initDesignState);
    const dispatch = (action: DesignAction) => {
      actions.push(action);
      rawDispatch(action);
    };
    onFork.mockImplementation(() => fork(rawDispatch));
    const survey = useSurveyImport({
      state,
      dispatch,
      designId: state.present.design_id,
      status: state.present.lifecycle_status,
      chargeRequest: () => null,
      onFork,
    });
    return { state, dispatch: rawDispatch, survey };
  });
  return { view, actions, onFork };
}

const FILE = new File(["66-1-01,5,10,420"], "66.csv");

beforeEach(() => {
  api.survey.read.mockReset().mockResolvedValue(READ);
  api.survey.evaluate.mockReset().mockResolvedValue(evaluation());
  api.survey.apply.mockReset().mockResolvedValue(applied());
});
afterEach(cleanup);

async function loaded(initial: BlastDesign, fork?: ForkFn) {
  const ctx = setup(initial, fork);
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

  it("выбор скважины для точки уходит в manual, пропуск — в skip", async () => {
    const { view } = await loaded(design());
    await act(async () => view.result.current.survey.setManual("R1", "1-02"));
    expect(api.survey.evaluate).toHaveBeenLastCalledWith(expect.objectContaining({ manual: { R1: "1-02" }, skip: [] }));
    await act(async () => view.result.current.survey.skip("R1"));
    expect(api.survey.evaluate).toHaveBeenLastCalledWith(expect.objectContaining({ manual: {}, skip: ["R1"] }));
    expect(view.result.current.survey.skipped).toEqual(["R1"]);
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
    await act(async () => view.result.current.survey.setManual("R1", "1-02"));
    await act(() => view.result.current.survey.apply());
    expect(api.survey.apply).toHaveBeenCalledTimes(1);
    const body = api.survey.apply.mock.calls[0][0];
    expect(body).toMatchObject({ design_id: "d1", manual: { R1: "1-02" }, skip: [], file_name: "66.csv", file_sha256: "abc", charge: null });
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
      return copy;
    };
    const { view, actions, onFork } = await loaded(design("approved"), fork);
    await act(async () => view.result.current.survey.setManual("R1", "1-02"));
    await act(async () => view.result.current.survey.skip("7"));
    await act(() => view.result.current.survey.copyBySurvey());
    await waitFor(() => expect(api.survey.apply).toHaveBeenCalledTimes(1));
    expect(onFork).toHaveBeenCalledTimes(1);
    const body = api.survey.apply.mock.calls[0][0];
    expect(body.design_id).toBe("d2");
    expect(body.design.lifecycle_status).toBe("draft");
    expect(body.manual).toEqual({ R1: "1-02" });
    expect(body.skip).toEqual(["7"]);
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
    await act(async () => view.result.current.survey.setManual("7", "1-01"));
    expect(api.survey.evaluate).toHaveBeenLastCalledWith(expect.objectContaining({ manual: { "7": "1-01" } }));
    await act(async () => view.result.current.survey.setManual("7", ""));
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
    expect(api.survey.read).toHaveBeenLastCalledWith(FILE, { columns: { name: "Пикет", east: "Вост", north: "Сев" } });
    expect(view.result.current.survey.error).toBe("");
    expect(view.result.current.survey.rows).toHaveLength(3);
  });

  it("копия не стала документом — ошибка, «Применить» не вызывается", async () => {
    const { view } = await loaded(design("approved"), async () => ({ ...design("draft", "d2") }));
    await act(() => view.result.current.survey.copyBySurvey());
    await waitFor(() => expect(view.result.current.survey.error).toBe(COPY_FAILED));
    expect(api.survey.apply).not.toHaveBeenCalled();
    expect(view.result.current.survey.busy).toBe(false);
  });
});
