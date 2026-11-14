// @vitest-environment jsdom
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { SurveyHoleVerdict, SurveyTolerances, SurveyedPoint } from "../../types/design";
import type { SurveyImportView, SurveyRow } from "./useSurveyImport";

const api = vi.hoisted(() => ({
  economics: { referenceSnapshot: vi.fn() },
  survey: { sites: { list: vi.fn(), create: vi.fn(), remove: vi.fn() } },
}));
vi.mock("../../api/endpoints", () => ({ api }));

import { SurveyPanel } from "./SurveyPanel";

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false;
  });
});
beforeEach(() => {
  api.economics.referenceSnapshot.mockReset().mockResolvedValue({
    revision_id: "r", published_at: null, published_by: "", section_catalog: [], group_catalog: [],
    sections: {
      sites: [
        { code: "GUS", name: "Гусевогорское", payload: {}, is_active: true, valid_from: null, valid_to: null, source: "", comment: "", revision: 1 },
        { code: "OLD", name: "Закрытый", payload: {}, is_active: false, valid_from: null, valid_to: null, source: "", comment: "", revision: 1 },
      ],
    },
  });
  api.survey.sites.list.mockReset().mockResolvedValue([
    { id: "s1", site_code: "GUS", block_label: "64", horizon_m: 180, survey_date: "2026-10-01", file_name: "64.csv", file_sha256: "x", points_count: 41, created_at: "2026-10-02T10:00:00+00:00" },
  ]);
  api.survey.sites.create.mockReset();
  api.survey.sites.remove.mockReset().mockResolvedValue(undefined);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const P1: SurveyedPoint = { name: "66-1-01", x: 10, y: 5, line: 1 };
const P2: SurveyedPoint = { name: "7", x: 14.2, y: 5, line: 2 };
const R1: SurveyedPoint = { name: "R1", x: 40, y: 40, line: 3 };

function verdict(hole_id: string, point: SurveyedPoint, codes: SurveyHoleVerdict["codes"], extra: Partial<SurveyHoleVerdict> = {}): SurveyHoleVerdict {
  return {
    hole_id, point, codes, offset_m: 0, depth_delta_m: 0, required_length_m: 12, angle_delta_deg: null,
    burden_delta_pct: null, spacing_delta_pct: null, unchanged: false, ...extra,
  };
}

const ROWS: SurveyRow[] = [
  { key: "a", holeId: "1-01", point: P1, by: "name", issue: "", verdict: verdict("1-01", P1, ["ok"]) },
  { key: "b", holeId: "1-02", point: P2, by: "nearest", issue: "", verdict: verdict("1-02", P2, ["offset", "underdrill", "no_depth"], { offset_m: 0.42, depth_delta_m: -0.5 }) },
  { key: "c", holeId: null, point: R1, by: "", issue: "unmatched_point", verdict: null },
  { key: "d", holeId: "1-03", point: null, by: "", issue: "missing_point", verdict: null },
];

const TOLERANCES: SurveyTolerances = {
  depth_m: 0.3, collar_m: 0.3, angle_deg: 1, burden_pct: 5, spacing_pct: 5,
  source: "passport", passport_no: "12", revision_no: 2, passport_design_id: "d1",
};

function view(extra: Partial<SurveyImportView> = {}): SurveyImportView {
  return {
    fileName: "66.csv",
    format: "PNEZD_CSV",
    formatChoice: "",
    points: [P1, P2, R1],
    rows: ROWS,
    tolerances: TOLERANCES,
    swapSuggested: false,
    warnings: [],
    skipped: [],
    enteredDepths: {},
    holeIds: ["1-01", "1-02", "1-03"],
    headers: [],
    columns: {},
    setColumn: vi.fn(),
    rereadColumns: vi.fn(async () => undefined),
    surveyDate: "2026-11-14",
    setSurveyDate: vi.fn(),
    action: "apply",
    actionHint: "",
    ready: true,
    busy: false,
    error: "",
    notice: "",
    load: vi.fn(async () => undefined),
    setFormat: vi.fn(async () => undefined),
    swap: vi.fn(async () => undefined),
    evaluate: vi.fn(async () => undefined),
    setManual: vi.fn(),
    detach: vi.fn(),
    skip: vi.fn(),
    unskip: vi.fn(),
    setDepth: vi.fn(),
    apply: vi.fn(async () => undefined),
    copyBySurvey: vi.fn(async () => undefined),
    ...extra,
  };
}

describe("SurveyPanel", () => {
  it("таблица: сопоставление и статусы подписями, допуски с источником", () => {
    render(<SurveyPanel survey={view()} />);
    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row");
    // Скважина строки — показанный выбор: и точку по имени можно перепривязать.
    const hole = within(rows[1]).getByLabelText("Скважина для точки 66-1-01") as HTMLSelectElement;
    expect(hole.selectedOptions[0].textContent).toBe("1-01");
    expect(within(rows[1]).getByText("по имени")).toBeTruthy();
    expect(within(rows[1]).getByText("ОК")).toBeTruthy();
    expect(within(rows[2]).getByText("по близости")).toBeTruthy();
    expect(within(rows[2]).getByText("СМЕЩЕНИЕ")).toBeTruthy();
    expect(within(rows[2]).getByText("ДОБУРИТЬ")).toBeTruthy();
    expect(within(rows[2]).getByText("глубина не замерена")).toBeTruthy();
    expect(within(rows[2]).getByText("0,42")).toBeTruthy();
    expect(within(rows[2]).getByText("−0,50")).toBeTruthy();
    expect(within(rows[3]).getByText("точка без скважины")).toBeTruthy();
    expect(within(rows[4]).getByText("нет съёмки")).toBeTruthy();
    expect(screen.getByText(/из паспорта на бурение № 12, ревизия 2/)).toBeTruthy();
    expect(screen.queryByText(/[{}]/)).toBeNull();
  });

  it("умолчания допусков подписаны словом", () => {
    render(<SurveyPanel survey={view({ tolerances: { ...TOLERANCES, source: "default", passport_no: "", revision_no: null } })} />);
    expect(screen.getByText(/умолчания/)).toBeTruthy();
  });

  it("точка без скважины: выбор скважины — setManual, «Пропустить» — skip", async () => {
    const user = userEvent.setup();
    const survey = view();
    render(<SurveyPanel survey={survey} />);
    await user.selectOptions(screen.getByLabelText("Скважина для точки R1"), "1-03");
    expect(survey.setManual).toHaveBeenCalledWith(3, "1-03");
    await user.click(screen.getByRole("button", { name: "Пропустить точку R1" }));
    expect(survey.skip).toHaveBeenCalledWith(3);
  });

  it("глубина не замерена: введённая глубина уходит в setDepth", async () => {
    const user = userEvent.setup();
    const survey = view();
    render(<SurveyPanel survey={survey} />);
    await user.type(screen.getByLabelText("Глубина скважины 1-02, м"), "11,8{Enter}");
    expect(survey.setDepth).toHaveBeenCalledWith("1-02", 11.8);
  });

  it("кнопка по статусу: черновик — «Применить к проекту»", async () => {
    const user = userEvent.setup();
    const survey = view();
    render(<SurveyPanel survey={survey} />);
    await user.click(screen.getByRole("button", { name: "Применить к проекту" }));
    expect(survey.apply).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Копия по съёмке" })).toBeNull();
  });

  it("кнопка по статусу: утверждён — «Копия по съёмке»", async () => {
    const user = userEvent.setup();
    const survey = view({ action: "copy" });
    render(<SurveyPanel survey={survey} />);
    await user.click(screen.getByRole("button", { name: "Копия по съёмке" }));
    expect(survey.copyBySurvey).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Применить к проекту" })).toBeNull();
  });

  it("кнопка по статусу: на проверке — недоступна с подсказкой", () => {
    render(<SurveyPanel survey={view({ action: "blocked", actionHint: "Верните проект в черновик" })} />);
    const button = screen.getByRole("button", { name: "Применить к проекту" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(screen.getByText("Верните проект в черновик")).toBeTruthy();
  });

  it("X и Y перепутаны — плашка и «Поменять»", async () => {
    const user = userEvent.setup();
    const survey = view({ swapSuggested: true });
    render(<SurveyPanel survey={survey} />);
    expect(screen.getByText("Похоже, X и Y перепутаны")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Поменять" }));
    expect(survey.swap).toHaveBeenCalledTimes(1);
  });

  it("файл уходит в load, формат можно сменить", async () => {
    const user = userEvent.setup();
    const survey = view();
    render(<SurveyPanel survey={survey} />);
    const file = new File(["x"], "66.csv");
    await user.upload(screen.getByLabelText("Файл съёмки"), file);
    expect(survey.load).toHaveBeenCalledWith(file);
    await user.selectOptions(screen.getByLabelText("Формат файла"), "TABLE");
    expect(survey.setFormat).toHaveBeenCalledWith("TABLE");
  });

  it("«Съёмка старого блока»: объект из справочника, список, загрузка и удаление", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    api.survey.sites.create.mockResolvedValue({
      id: "s2", site_code: "GUS", block_label: "65", horizon_m: 175.5, survey_date: "2026-11-01", file_name: "65.csv",
      file_sha256: "y", points_count: 30, created_at: "2026-11-02T10:00:00+00:00", points: [],
    });
    render(<SurveyPanel survey={view()} />);
    await user.click(screen.getByRole("button", { name: "Съёмка старого блока" }));
    const dialog = await screen.findByRole("dialog");
    const site = within(dialog).getByLabelText("Объект") as HTMLSelectElement;
    await waitFor(() => expect(site.value).toBe("GUS"));
    expect(within(site).queryByText("Закрытый")).toBeNull();
    await waitFor(() => expect(api.survey.sites.list).toHaveBeenCalledWith("GUS"));
    expect(await within(dialog).findByText(/Блок 64/)).toBeTruthy();

    await user.type(within(dialog).getByLabelText("Блок"), "65");
    await user.type(within(dialog).getByLabelText("Горизонт, м"), "175,5");
    await user.type(within(dialog).getByLabelText("Дата съёмки"), "2026-11-01");
    const file = new File(["x"], "65.csv");
    await user.upload(within(dialog).getByLabelText("Файл съёмки старого блока"), file);
    await user.click(within(dialog).getByRole("button", { name: "Загрузить" }));
    await waitFor(() =>
      expect(api.survey.sites.create).toHaveBeenCalledWith("GUS", file, { blockLabel: "65", surveyDate: "2026-11-01", horizonM: 175.5 }),
    );
    expect(await within(dialog).findByText(/Блок 65/)).toBeTruthy();

    await user.click(within(dialog).getByRole("button", { name: "Удалить съёмку блока 64" }));
    await waitFor(() => expect(api.survey.sites.remove).toHaveBeenCalledWith("GUS", "s1"));
    await waitFor(() => expect(within(dialog).queryByText(/Блок 64/)).toBeNull());
  });

  it("точку по близости и вручную можно перепривязать, пропустить и снять ручную привязку", async () => {
    const user = userEvent.setup();
    const manualRow: SurveyRow = { key: "e", holeId: "1-03", point: { name: "9", x: 1, y: 1, line: 4 }, by: "manual", issue: "", verdict: verdict("1-03", { name: "9", x: 1, y: 1, line: 4 }, ["ok"]) };
    const survey = view({ rows: [...ROWS, manualRow] });
    render(<SurveyPanel survey={survey} />);
    await user.selectOptions(screen.getByLabelText("Скважина для точки 7"), "1-03");
    expect(survey.setManual).toHaveBeenLastCalledWith(2, "1-03");
    await user.click(screen.getByRole("button", { name: "Пропустить точку 7" }));
    expect(survey.skip).toHaveBeenCalledWith(2);
    expect(within(screen.getByLabelText("Скважина для точки 7")).queryByText("снять ручную привязку")).toBeNull();
    await user.selectOptions(screen.getByLabelText("Скважина для точки 9"), "снять ручную привязку");
    expect(survey.setManual).toHaveBeenLastCalledWith(4, "");
    expect(within(screen.getByLabelText("Скважина для точки 9")).queryByText("без скважины")).toBeNull();
    expect(screen.getByRole("button", { name: "Пропустить точку 9" })).toBeTruthy();
  });

  it("точку по имени можно перепривязать, отвязать («без скважины») и пропустить", async () => {
    const user = userEvent.setup();
    const survey = view();
    render(<SurveyPanel survey={survey} />);
    await user.selectOptions(screen.getByLabelText("Скважина для точки 66-1-01"), "1-02");
    expect(survey.setManual).toHaveBeenLastCalledWith(1, "1-02");
    await user.selectOptions(screen.getByLabelText("Скважина для точки 66-1-01"), "без скважины");
    expect(survey.detach).toHaveBeenLastCalledWith(1);
    await user.click(screen.getByRole("button", { name: "Пропустить точку 66-1-01" }));
    expect(survey.skip).toHaveBeenLastCalledWith(1);
  });

  it("пропущенные точки: одноимённые различаются строкой файла, возврат — по строке", async () => {
    const user = userEvent.setup();
    const twin: SurveyedPoint = { ...P1, line: 9 };
    const survey = view({ points: [P1, P2, R1, twin], skipped: [twin] });
    render(<SurveyPanel survey={survey} />);
    await user.click(screen.getByRole("button", { name: /66-1-01 · стр\. 9/ }));
    expect(survey.unskip).toHaveBeenCalledWith(9);
  });

  it("введённая глубина видна и правится; стёртая — снимается; 0 — подсказка", async () => {
    const user = userEvent.setup();
    const entered: SurveyRow = { ...ROWS[1], verdict: verdict("1-02", P2, ["offset"], { offset_m: 0.42, depth_delta_m: -0.5 }) };
    const survey = view({ rows: [ROWS[0], entered], enteredDepths: { 2: 11.8 } });
    render(<SurveyPanel survey={survey} />);
    const input = screen.getByLabelText("Глубина скважины 1-02, м") as HTMLInputElement;
    expect(input.value).toBe("11,80");
    await user.clear(input);
    await user.type(input, "0{Enter}");
    expect(screen.getByText("Глубина — число больше нуля.")).toBeTruthy();
    expect(survey.setDepth).not.toHaveBeenCalled();
    await user.clear(input);
    await user.type(input, "{Enter}");
    expect(survey.setDepth).toHaveBeenCalledWith("1-02", null);
  });

  it("таблица с заголовками: колонки выбираются, «Прочитать заново»", async () => {
    const user = userEvent.setup();
    const survey = view({ format: "TABLE", headers: ["Пикет", "Вост", "Сев"], columns: { name: "Пикет" } });
    render(<SurveyPanel survey={survey} />);
    const group = screen.getByRole("group", { name: "Колонки" });
    expect((within(group).getByLabelText("номер") as HTMLSelectElement).value).toBe("Пикет");
    expect(within(group).getByLabelText("уровень воды")).toBeTruthy();
    await user.selectOptions(within(group).getByLabelText("север"), "Сев");
    expect(survey.setColumn).toHaveBeenCalledWith("north", "Сев");
    await user.click(within(group).getByRole("button", { name: "Прочитать заново" }));
    expect(survey.rereadColumns).toHaveBeenCalledTimes(1);
  });

  it("без даты съёмки «Применить» недоступно с подсказкой", () => {
    render(<SurveyPanel survey={view({ surveyDate: "" })} />);
    expect((screen.getByRole("button", { name: "Применить к проекту" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Укажите дату съёмки")).toBeTruthy();
  });

  it("«Съёмка старого блока» — обычная кнопка панели", () => {
    render(<SurveyPanel survey={view()} />);
    expect(screen.getByRole("button", { name: "Съёмка старого блока" }).className).toBe("secondary-button");
  });

  it("«Оценить заново» доступна, когда файл прочитан, даже если оценки нет", async () => {
    const user = userEvent.setup();
    const survey = view({ rows: [], tolerances: null, ready: false, error: "База не отвечает." });
    render(<SurveyPanel survey={survey} />);
    const button = screen.getByRole("button", { name: "Оценить заново" }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
    await user.click(button);
    expect(survey.evaluate).toHaveBeenCalledTimes(1);
  });

  it("одинаковые заголовки таблицы — без повторных ключей", () => {
    const errors = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(<SurveyPanel survey={view({ format: "TABLE", headers: ["A", "A", "B"], columns: {} })} />);
    expect(within(screen.getByRole("group", { name: "Колонки" })).getByLabelText("номер").querySelectorAll("option")).toHaveLength(4);
    expect(errors.mock.calls.some((call) => String(call[0]).includes("same key"))).toBe(false);
  });
});
