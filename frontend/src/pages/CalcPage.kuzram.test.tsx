// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceContext } from "../app/useWorkspace";
import { CalcPage } from "./CalcPage";
import { KUZRAM_DEFAULTS, type KuzRamBlock } from "./calc/kuzram/kuzramSettings";
import { gabbroVariant, OPTIMIZE_GABBRO } from "./calc/kuzram/testing/fixtures";

/**
 * Модель Kuz-Ram на листе «Расчёт»: кнопка окна и подпись настроек, пересчёт
 * по правке настроек (без фактов в запросе), автосохранение блока `kuzram`,
 * значок «!» в таблице вариантов.
 */

const api = vi.hoisted(() => ({
  rocks: vi.fn(),
  explosives: vi.fn(),
  blastOptions: vi.fn(),
  productionUnits: vi.fn(),
  calcInputs: vi.fn(),
  saveCalcInputs: vi.fn(),
  optimize: vi.fn(),
  calibrateKuzram: vi.fn(),
  geometry: vi.fn(),
  economics: { referenceSnapshot: vi.fn(), technicalPassports: vi.fn() },
}));
vi.mock("../api/endpoints", () => ({ api }));

const OBJECT = { name: "Карьер Анна", mobilization_km: 1, diesel_price_ton_rub: null, production_unit_code: "UNIT_PERM" };
const OBJECT_2 = { ...OBJECT, name: "Карьер Берёзовый" };
const PANEL = {
  explosive_key: "ПВВ Гранулит-РП",
  undercharge_m: 2,
  intermediate_detonators_per_hole: 1,
  nsi_per_hole: 1,
  nsi_length_1_m: 12,
  nsi_length_2_m: 6,
  detonator_delay_ms: 500,
};

function savedInputs(kuzram?: KuzRamBlock) {
  return {
    version: 1,
    rock_name: "Гранит",
    explosive_key: "ПВВ Гранулит-РП",
    lump_size_mm: 400,
    bench_height_m: 10,
    overdrill_m: 1,
    oversize_coeff: 1.05,
    spacing_coeff: 1.25,
    oversize_threshold_pct: 5,
    selected_crowns_mm: [110, 152, 250],
    selected_crown_mm: 152,
    block_volume_m3: 30000,
    additional_holes_pct: 3,
    production_unit_code: "UNIT_PERM",
    panels: { left: PANEL, right: PANEL },
    ...(kuzram ? { kuzram } : {}),
  };
}

function Workspace({ children, objectName = OBJECT.name }: { children: ReactNode; objectName?: string }) {
  const value = {
    loading: false,
    error: "",
    state: {
      settings: { team_id: "t", team_name: "Команда", active_scenario_id: "drill_blast", active_work_object_name: objectName },
      references: { work_object_records: [OBJECT, OBJECT_2] },
      warnings: [],
    } as never,
    scenarios: [],
    activeScenario: null,
    dirty: false,
    saving: false,
    blastContext: null,
    setBlastContext: () => {},
    updateSnapshot: () => {},
    setActiveWorkObjectName: async () => {},
    save: async () => {},
    reload: async () => {},
    canEdit: true,
  };
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

const renderSheet = () =>
  render(
    <Workspace>
      <CalcPage />
    </Workspace>,
  );

// Под нагрузкой полного прогона лист грузится дольше секунды по умолчанию.
const SLOW = { timeout: 3000 };
/** Дождаться, пока отложенная запись автосохранения (800 мс) точно успела бы уйти. */
const autosaveWindow = () => act(() => new Promise((resolve) => setTimeout(resolve, 1100)));

async function loaded() {
  await waitFor(() => expect(screen.getByRole("button", { name: "Рассчитать варианты" })).toBeEnabled(), SLOW);
  await waitFor(() => expect(api.optimize).toHaveBeenCalledTimes(1), SLOW);
}

const lastSaved = () => api.saveCalcInputs.mock.calls.at(-1)?.[1] as { kuzram: KuzRamBlock } | undefined;
const lastSavedCrown = () => api.saveCalcInputs.mock.calls.at(-1)?.[1] as { selected_crown_mm: number } | undefined;
const dialog = () => screen.getByRole("dialog", { name: "Модель Kuz-Ram" });
/** Пауза дольше задержки пересчёта по правке настроек (300 мс): таймер точно успел бы сработать. */
const recalcWindow = () => act(() => new Promise((resolve) => setTimeout(resolve, 500)));
/** Правка C(A) в окне и закрытие окна — дальше правят лист. */
function editCorrectionAndClose(value: string) {
  fireEvent.click(screen.getByRole("button", { name: "Модель Kuz-Ram" }));
  fireEvent.change(within(dialog()).getByLabelText("Поправка C(A)"), { target: { value } });
  fireEvent.click(within(dialog()).getByRole("button", { name: "Закрыть" }));
}

beforeAll(() => {
  // jsdom не реализует модальный `dialog`.
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false;
  });
});

beforeEach(() => {
  vi.clearAllMocks();
  api.rocks.mockResolvedValue({ items: [{ name: "Гранит", density_t_m3: 2.65, ucs_mpa: 150, fissuring_ff: 2 }], default_name: "Гранит" });
  api.explosives.mockResolvedValue({
    items: [{ key: "ПВВ Гранулит-РП", name: "Гранулит-РП", density_t_m3: 0.9, power_mj_kg: 3.8, chart_label: "ГРАНУЛИТ-РП" }],
    default_key: "ПВВ Гранулит-РП",
  });
  api.blastOptions.mockResolvedValue({ crown_diameters_mm: [110, 152, 250], nsi_length_options_m: [6, 12], detonator_delay_ms_options: [500] });
  api.productionUnits.mockResolvedValue({ items: [{ code: "UNIT_PERM", name: "Юнит Пермь" }] });
  api.calcInputs.mockResolvedValue({ work_object_name: OBJECT.name, inputs: savedInputs(), updated_at: "then" });
  api.optimize.mockResolvedValue(OPTIMIZE_GABBRO);
  // Схемы заряда здесь не проверяются: запрос висит, карточки — в загрузке.
  api.geometry.mockReturnValue(new Promise(() => {}));
  api.economics.referenceSnapshot.mockResolvedValue({ revision_id: "REV", sections: { sites: [] } });
  api.economics.technicalPassports.mockResolvedValue([]);
  api.saveCalcInputs.mockImplementation(async (name: string, inputs: object) => ({ work_object_name: name, inputs, updated_at: "now" }));
});
afterEach(cleanup);

describe("CalcPage: модель Kuz-Ram", () => {
  it("настройки без блока kuzram — подбор с умолчаниями модели, подписи нет, при открытии ничего не пишется", async () => {
    renderSheet();
    await loaded();
    expect(api.optimize.mock.calls[0][0].kuzram).toEqual(KUZRAM_DEFAULTS);
    expect(document.querySelector(".kuzram-caption")).toBeNull();
    await autosaveWindow();
    expect(api.saveCalcInputs).not.toHaveBeenCalled();
  });

  it("«!» у q, «≤ 0.10» и «> 5%» в таблице вариантов", async () => {
    api.optimize.mockResolvedValue({
      ...OPTIMIZE_GABBRO,
      variants: [gabbroVariant(110, { specific_q_kg_m3: 0.1 }), gabbroVariant(152), gabbroVariant(250, { oversize_pct: 5 })],
    });
    renderSheet();
    await loaded();
    const rowOf = async (crown: number) => (await screen.findByText(`Ø ${crown}`, undefined, SLOW)).closest("tr")!;
    const row250 = await rowOf(250);
    expect(within(row250).getByRole("img", { name: "Порог негабарита не достигнут" })).toHaveAttribute(
      "title",
      expect.stringContaining("верхней границе перебора"),
    );
    expect(row250).toHaveTextContent("1.50");
    expect(row250).toHaveTextContent("> 5%");
    expect(await rowOf(110)).toHaveTextContent("≤ 0.10");
    expect(within(await rowOf(152)).queryByRole("img", { name: "Порог негабарита не достигнут" })).not.toBeInTheDocument();
  });

  it("правка C(A) в окне пересчитывает варианты без фактов, показывает подпись и сохраняет блок", async () => {
    const facts = [{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 }];
    api.calcInputs.mockResolvedValue({ work_object_name: OBJECT.name, inputs: savedInputs({ ...KUZRAM_DEFAULTS, facts }), updated_at: "then" });
    renderSheet();
    await loaded();
    fireEvent.click(screen.getByRole("button", { name: "Модель Kuz-Ram" }));
    fireEvent.change(within(dialog()).getByLabelText("Поправка C(A)"), { target: { value: "1,2" } });
    await waitFor(() => expect(api.optimize).toHaveBeenCalledTimes(2), SLOW);
    expect(api.optimize.mock.calls[1][0].kuzram).toEqual({ ...KUZRAM_DEFAULTS, rock_factor_correction: 1.2 });
    expect(document.querySelector(".kuzram-caption")).toHaveTextContent("C(A) 1,2");
    await waitFor(() => expect(lastSaved()?.kuzram).toEqual({ ...KUZRAM_DEFAULTS, rock_factor_correction: 1.2, facts }), SLOW);
  });

  it("пересчёт по правке настроек модели не сбрасывает выбранную коронку", async () => {
    renderSheet();
    await loaded();
    const rowOf = async (crown: number) => (await screen.findByText(`Ø ${crown}`, undefined, SLOW)).closest("tr")!;
    fireEvent.click(await rowOf(250));
    expect(await rowOf(250)).toHaveClass("selected");
    fireEvent.click(screen.getByRole("button", { name: "Модель Kuz-Ram" }));
    fireEvent.change(within(dialog()).getByLabelText("Поправка C(A)"), { target: { value: "1,2" } });
    await waitFor(() => expect(api.optimize).toHaveBeenCalledTimes(2), SLOW);
    expect(await rowOf(250)).toHaveClass("selected");
    await waitFor(() => expect(lastSavedCrown()?.selected_crown_mm).toBe(250), SLOW);
  });

  it("клик по другой строке во время пересчёта по правке настроек не откатывается к прежней коронке", async () => {
    renderSheet();
    await loaded();
    const rowOf = async (crown: number) => (await screen.findByText(`Ø ${crown}`, undefined, SLOW)).closest("tr")!;
    fireEvent.click(await rowOf(250));
    expect(await rowOf(250)).toHaveClass("selected");
    let release: (value: unknown) => void = () => {};
    api.optimize.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    fireEvent.click(screen.getByRole("button", { name: "Модель Kuz-Ram" }));
    fireEvent.change(within(dialog()).getByLabelText("Поправка C(A)"), { target: { value: "1,2" } });
    await waitFor(() => expect(api.optimize).toHaveBeenCalledTimes(2), SLOW);
    // Второй запрос (по правке настроек) ещё не ответил — кликаем другую строку.
    fireEvent.click(await rowOf(110));
    expect(await rowOf(110)).toHaveClass("selected");
    await act(async () => release(OPTIMIZE_GABBRO));
    expect(await rowOf(110)).toHaveClass("selected");
    await waitFor(() => expect(lastSavedCrown()?.selected_crown_mm).toBe(110), SLOW);
  });

  it("смена объекта в паузе перед пересчётом по настройкам не шлёт запрос по прежнему листу", async () => {
    api.calcInputs.mockImplementation(async (name: string) => ({ work_object_name: name, inputs: savedInputs(), updated_at: "then" }));
    const { rerender } = renderSheet();
    await loaded();
    let release: (value: unknown) => void = () => {};
    api.optimize.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    editCorrectionAndClose("1,2");
    rerender(
      <Workspace objectName={OBJECT_2.name}>
        <CalcPage />
      </Workspace>,
    );
    await waitFor(() => expect(api.optimize).toHaveBeenCalledTimes(2), SLOW);
    await recalcWindow();
    // Только загрузка нового объекта: запрос по листу прежнего стал бы последним
    // и не дал бы ответу нового объекта снять «идёт расчёт».
    expect(api.optimize).toHaveBeenCalledTimes(2);
    await act(async () => release(OPTIMIZE_GABBRO));
    await waitFor(() => expect(screen.getByRole("button", { name: "Рассчитать варианты" })).toBeEnabled(), SLOW);
  });

  it("правка листа в паузе перед пересчётом по настройкам — запрос уходит по свежему листу", async () => {
    renderSheet();
    await loaded();
    editCorrectionAndClose("1,2");
    fireEvent.change(screen.getByLabelText("Кусок, мм"), { target: { value: "600" } });
    await waitFor(() => expect(api.optimize).toHaveBeenCalledTimes(2), SLOW);
    expect(api.optimize.mock.calls[1][0]).toMatchObject({ lumpSize: 600, kuzram: { rock_factor_correction: 1.2 } });
    await recalcWindow();
    expect(api.optimize).toHaveBeenCalledTimes(2);
  });

  it("правка листа, пока летит пересчёт по настройкам, — пересчёт повторяется по свежему листу", async () => {
    renderSheet();
    await loaded();
    let release: (value: unknown) => void = () => {};
    api.optimize.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    editCorrectionAndClose("1,2");
    await waitFor(() => expect(api.optimize).toHaveBeenCalledTimes(2), SLOW);
    fireEvent.change(screen.getByLabelText("Кусок, мм"), { target: { value: "600" } });
    // Ответ по прежнему листу отбрасывается — варианты не должны остаться
    // посчитанными по прежней C(A) с погасшим «Пересчёт…».
    await act(async () => release(OPTIMIZE_GABBRO));
    await waitFor(() => expect(api.optimize).toHaveBeenCalledTimes(3), SLOW);
    expect(api.optimize.mock.calls[2][0]).toMatchObject({ lumpSize: 600, kuzram: { rock_factor_correction: 1.2 } });
  });

  it("новая правка настроек, пока летит пересчёт по прежней, — прежний пересчёт не повторяется", async () => {
    renderSheet();
    await loaded();
    let release: (value: unknown) => void = () => {};
    api.optimize.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    fireEvent.click(screen.getByRole("button", { name: "Модель Kuz-Ram" }));
    fireEvent.change(within(dialog()).getByLabelText("Поправка C(A)"), { target: { value: "1,2" } });
    await waitFor(() => expect(api.optimize).toHaveBeenCalledTimes(2), SLOW);
    fireEvent.change(within(dialog()).getByLabelText("Поправка C(A)"), { target: { value: "1,3" } });
    await waitFor(() => expect(api.optimize).toHaveBeenCalledTimes(3), SLOW);
    expect(api.optimize.mock.calls[2][0].kuzram.rock_factor_correction).toBe(1.3);
    // Ответ по C(A) 1,2 устарел; повторять его незачем — C(A) 1,3 считает свой таймер.
    await act(async () => release(OPTIMIZE_GABBRO));
    await recalcWindow();
    expect(api.optimize).toHaveBeenCalledTimes(3);
  });

  it("повторы пересчёта по настройкам ограничены тремя попытками", async () => {
    renderSheet();
    await loaded();
    const releases: ((value: unknown) => void)[] = [];
    api.optimize.mockImplementation(() => new Promise((resolve) => { releases.push(resolve); }));
    editCorrectionAndClose("1,2");
    // Каждую попытку лист правят, пока она летит, — каждая отбрасывается.
    for (let attempt = 1; attempt <= 3; attempt += 1) {
      await waitFor(() => expect(api.optimize).toHaveBeenCalledTimes(1 + attempt), SLOW);
      fireEvent.change(screen.getByLabelText("Кусок, мм"), { target: { value: String(400 + attempt * 50) } });
      await act(async () => releases.at(-1)!(OPTIMIZE_GABBRO));
    }
    await recalcWindow();
    expect(api.optimize).toHaveBeenCalledTimes(4);
  });

  it("пока идёт пересчёт, окно показывает «Пересчёт…»", async () => {
    renderSheet();
    await loaded();
    let release: (value: unknown) => void = () => {};
    api.optimize.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    fireEvent.click(screen.getByRole("button", { name: "Модель Kuz-Ram" }));
    fireEvent.change(within(dialog()).getByLabelText("Поправка C(A)"), { target: { value: "1,3" } });
    expect(within(dialog()).getByRole("status")).toHaveTextContent("Пересчёт…");
    await waitFor(() => expect(api.optimize).toHaveBeenCalledTimes(2), SLOW);
    await act(async () => release(OPTIMIZE_GABBRO));
    await waitFor(() => expect(within(dialog()).getByRole("status")).toBeEmptyDOMElement(), SLOW);
  });
});

describe("CalcPage: фактические взрывы", () => {
  it("правка фактов сохраняется за объектом и подбор не запускает", async () => {
    renderSheet();
    await loaded();
    fireEvent.click(screen.getByRole("button", { name: "Модель Kuz-Ram" }));
    fireEvent.click(within(dialog()).getByRole("button", { name: "Добавить взрыв" }));
    fireEvent.change(within(dialog()).getByLabelText("Фактический q, строка 1"), { target: { value: "1,3" } });
    await waitFor(() => expect(lastSaved()?.kuzram.facts).toEqual([{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: null }]), SLOW);
    await autosaveWindow();
    expect(api.optimize).toHaveBeenCalledTimes(1);
  });

  it("«Подобрать C(A) по факту» шлёт только полные строки и пересчитывает варианты с новой поправкой", async () => {
    const facts = [
      { crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 },
      { crown_mm: 165, q_kg_m3: null, oversize_pct: null },
    ];
    api.calcInputs.mockResolvedValue({ work_object_name: OBJECT.name, inputs: savedInputs({ ...KUZRAM_DEFAULTS, facts }), updated_at: "then" });
    api.calibrateKuzram.mockResolvedValue({
      rows: [{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8, legacy_oversize_pct: 5.3, model_oversize_pct: 4.29, rock_factor_correction: 1.132, note: null }],
      rock_factor_correction: 1.132,
      used: 1,
      skipped: 0,
      model_version: "kuzram-cunningham-1.0",
    });
    renderSheet();
    await loaded();
    fireEvent.click(screen.getByRole("button", { name: "Модель Kuz-Ram" }));
    fireEvent.click(within(dialog()).getByRole("button", { name: "Подобрать C(A) по факту" }));
    await waitFor(() => expect(api.calibrateKuzram).toHaveBeenCalledTimes(1));
    const request = api.calibrateKuzram.mock.calls[0][0];
    expect(request.kuzram).toEqual(KUZRAM_DEFAULTS);
    expect(request.facts).toEqual([{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 }]);
    await waitFor(() => expect(api.optimize).toHaveBeenCalledTimes(2), SLOW);
    expect(api.optimize.mock.calls[1][0].kuzram).toEqual({ ...KUZRAM_DEFAULTS, rock_factor_correction: 1.132 });
    expect(within(dialog()).getByText(/C\(A\) = 1,132 записана в настройки/)).toBeInTheDocument();
    expect(document.querySelector(".kuzram-caption")).toHaveTextContent("C(A) 1,132");
  });

  it("подбор C(A), устаревший из-за правки настроек за время запроса, не записывается", async () => {
    const facts = [{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 }];
    api.calcInputs.mockResolvedValue({ work_object_name: OBJECT.name, inputs: savedInputs({ ...KUZRAM_DEFAULTS, facts }), updated_at: "then" });
    let release: (value: unknown) => void = () => {};
    api.calibrateKuzram.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    renderSheet();
    await loaded();
    fireEvent.click(screen.getByRole("button", { name: "Модель Kuz-Ram" }));
    fireEvent.click(within(dialog()).getByRole("button", { name: "Подобрать C(A) по факту" }));
    await waitFor(() => expect(api.calibrateKuzram).toHaveBeenCalledTimes(1));
    // Пока подбор летит, в окне поправляют настройку — она пересчитывает
    // варианты сама, независимо от подбора.
    fireEvent.change(within(dialog()).getByLabelText("Поправка C(A)"), { target: { value: "1,3" } });
    await waitFor(() => expect(api.optimize).toHaveBeenCalledTimes(2), SLOW);
    await act(async () =>
      release({
        rows: [{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8, legacy_oversize_pct: 5.3, model_oversize_pct: 4.29, rock_factor_correction: 1.132, note: null }],
        rock_factor_correction: 1.132,
        used: 1,
        skipped: 0,
        model_version: "kuzram-cunningham-1.0",
      }),
    );
    await waitFor(() => expect(within(dialog()).getByRole("alert")).toHaveTextContent("C(A) не записана"));
    expect(document.querySelector(".kuzram-caption")).toHaveTextContent("C(A) 1,3");
    expect(api.optimize.mock.calls.some((call) => call[0].kuzram.rock_factor_correction === 1.132)).toBe(false);
  });
});
