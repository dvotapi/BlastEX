// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceContext } from "../app/useWorkspace";
import { CalcPage } from "./CalcPage";

/**
 * Юнит в шапке листа «Расчёт» вместе с автосохранением: какой юнит получает
 * загруженный лист и когда он пишется в настройки объекта. Логика живёт в
 * эффектах `CalcPage` и зависит от порядка хуков, поэтому проверяется
 * рендером листа, а не только чистыми функциями `unitSelection.ts`.
 */

const api = vi.hoisted(() => ({
  rocks: vi.fn(),
  explosives: vi.fn(),
  blastOptions: vi.fn(),
  productionUnits: vi.fn(),
  calcInputs: vi.fn(),
  saveCalcInputs: vi.fn(),
  optimize: vi.fn(),
  geometry: vi.fn(),
  // Панель паспортов стоит в верхнем ряду листа всегда.
  economics: { referenceSnapshot: vi.fn(), technicalPassports: vi.fn() },
}));
vi.mock("../api/endpoints", () => ({ api }));

const UNITS = [
  { code: "UNIT_PERM", name: "Юнит Пермь" },
  { code: "UNIT_URAL", name: "Юнит Урал" },
];
const OBJECTS = [
  { name: "Карьер Анна", mobilization_km: 1, diesel_price_ton_rub: null, production_unit_code: "UNIT_PERM" },
  { name: "Карьер Жуков", mobilization_km: 1, diesel_price_ton_rub: null, production_unit_code: null },
  { name: "Карьер Лом", mobilization_km: 1, diesel_price_ton_rub: null, production_unit_code: "UNIT_URAL" },
];

function savedInputs(unit: string) {
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
    selected_crowns_mm: [152],
    selected_crown_mm: 152,
    block_volume_m3: 30000,
    additional_holes_pct: 3,
    production_unit_code: unit,
    panels: {
      left: { explosive_key: "ПВВ Гранулит-РП", undercharge_m: 3.1, intermediate_detonators_per_hole: 1, nsi_per_hole: 1, nsi_length_1_m: 12, nsi_length_2_m: 6, detonator_delay_ms: 500 },
      right: { explosive_key: "ПВВ Гранулит-РП", undercharge_m: 2, intermediate_detonators_per_hole: 1, nsi_per_hole: 1, nsi_length_1_m: 12, nsi_length_2_m: 6, detonator_delay_ms: 500 },
    },
  };
}

function Workspace({ initialObject, children }: { initialObject: string; children: ReactNode }) {
  const [objectName, setObjectName] = useState(initialObject);
  const value = {
    loading: false,
    error: "",
    state: {
      settings: { team_id: "t", team_name: "Команда", active_scenario_id: "drill_blast", active_work_object_name: objectName },
      references: { work_object_records: OBJECTS },
      warnings: [],
    } as never,
    scenarios: [],
    activeScenario: null,
    dirty: false,
    saving: false,
    blastContext: null,
    setBlastContext: () => {},
    updateSnapshot: () => {},
    setActiveWorkObjectName: async (name: string) => setObjectName(name),
    save: async () => {},
    reload: async () => {},
    canEdit: true,
  };
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

function renderSheet(initialObject: string) {
  return render(
    <Workspace initialObject={initialObject}>
      <CalcPage />
    </Workspace>,
  );
}

const savedUnits = () =>
  api.saveCalcInputs.mock.calls.map(([name, inputs]) => [name, (inputs as { production_unit_code: string }).production_unit_code]);

beforeEach(() => {
  vi.clearAllMocks();
  api.rocks.mockResolvedValue({ items: [{ name: "Гранит", density_t_m3: 2.7, ucs_mpa: 120, fissuring_ff: 1 }], default_name: "Гранит" });
  api.explosives.mockResolvedValue({
    items: [
      { key: "ПВВ Гранулит-РП", name: "Гранулит-РП", density_t_m3: 0.9, power_mj_kg: 3.8, chart_label: "ГРАНУЛИТ-РП" },
      { key: "ПЭВВ ЭВЕРСИН Э-100", name: "ЭВЕРСИН Э-100", density_t_m3: 1.2, power_mj_kg: 3.2, chart_label: "ЭВЕРСИН" },
    ],
    default_key: "ПВВ Гранулит-РП",
  });
  api.blastOptions.mockResolvedValue({ crown_diameters_mm: [152], nsi_length_options_m: [6, 12], detonator_delay_ms_options: [500] });
  api.productionUnits.mockResolvedValue({ items: UNITS });
  api.optimize.mockResolvedValue({ variants: [] });
  api.economics.referenceSnapshot.mockResolvedValue({ revision_id: "REV", sections: { sites: [] } });
  api.economics.technicalPassports.mockResolvedValue([]);
  api.saveCalcInputs.mockImplementation(async (name: string, inputs: object) => ({ work_object_name: name, inputs, updated_at: "now" }));
});
afterEach(cleanup);

// Под нагрузкой полного прогона лист грузится дольше секунды по умолчанию.
const SLOW = { timeout: 3000 };

async function loaded(objectPart: string) {
  await waitFor(() => expect(screen.getByRole("button", { name: "Рассчитать варианты" })).toBeEnabled(), SLOW);
  expect(screen.getByLabelText("Объект")).toHaveValue(OBJECTS.find((o) => o.name.includes(objectPart))!.name);
}

/** Дождаться, пока отложенная запись автосохранения (800 мс) точно успела бы уйти. */
const autosaveWindow = () => act(() => new Promise((resolve) => setTimeout(resolve, 1100)));

describe("CalcPage: юнит в шапке и автосохранение", () => {
  it("открытие объекта с юнитом показывает его юнит и ничего не записывает", async () => {
    api.calcInputs.mockResolvedValue({ work_object_name: "Карьер Анна", inputs: null, updated_at: null });
    renderSheet("Карьер Анна");
    await loaded("Анна");
    await waitFor(() => expect(screen.getByLabelText("Юнит")).toHaveValue("UNIT_PERM"), SLOW);
    await autosaveWindow();
    expect(api.saveCalcInputs).not.toHaveBeenCalled();
  });

  it("сохранённые до юнитов настройки объекта с юнитом не переписываются при открытии", async () => {
    api.calcInputs.mockResolvedValue({ work_object_name: "Карьер Лом", inputs: savedInputs(""), updated_at: "then" });
    renderSheet("Карьер Лом");
    await loaded("Лом");
    await waitFor(() => expect(screen.getByLabelText("Юнит")).toHaveValue("UNIT_URAL"), SLOW);
    await autosaveWindow();
    expect(api.saveCalcInputs).not.toHaveBeenCalled();
  });

  it("фильтр, перенесённый на объект без юнита с сохранёнными настройками, записывается", async () => {
    api.calcInputs.mockImplementation(async (name: string) => ({
      work_object_name: name,
      inputs: name === "Карьер Жуков" ? savedInputs("UNIT_URAL") : null,
      updated_at: null,
    }));
    renderSheet("Карьер Анна");
    await loaded("Анна");
    await waitFor(() => expect(screen.getByLabelText("Юнит")).toHaveValue("UNIT_PERM"), SLOW);
    fireEvent.change(screen.getByLabelText("Объект"), { target: { value: "Карьер Жуков" } });
    await loaded("Жуков");
    await waitFor(() => expect(screen.getByLabelText("Юнит")).toHaveValue("UNIT_PERM"), SLOW);
    await waitFor(() => expect(savedUnits()).toContainEqual(["Карьер Жуков", "UNIT_PERM"]), { timeout: 2000 });
  });

  it("пока юниты не загружены, переход на объект без юнита не затирает его сохранённый юнит", async () => {
    api.productionUnits.mockRejectedValue(new Error("нет связи"));
    api.calcInputs.mockImplementation(async (name: string) => ({
      work_object_name: name,
      inputs: name === "Карьер Жуков" ? savedInputs("UNIT_URAL") : null,
      updated_at: null,
    }));
    renderSheet("Карьер Анна");
    await loaded("Анна");
    fireEvent.change(screen.getByLabelText("Объект"), { target: { value: "Карьер Жуков" } });
    await loaded("Жуков");
    await autosaveWindow();
    expect(savedUnits().filter(([name]) => name === "Карьер Жуков")).toEqual([]);
  });

  it("юнит нельзя выбрать, пока загружаются настройки объекта", async () => {
    let release: (value: unknown) => void = () => {};
    api.calcInputs.mockImplementation(() => new Promise((resolve) => { release = resolve; }));
    renderSheet("Карьер Анна");
    await waitFor(() => expect(screen.getByLabelText("Юнит")).toBeInTheDocument(), { timeout: 3000 });
    expect(screen.getByLabelText("Юнит")).toBeDisabled();
    await act(async () => release({ work_object_name: "Карьер Анна", inputs: null, updated_at: null }));
    await waitFor(() => expect(screen.getByLabelText("Юнит")).toBeEnabled(), { timeout: 3000 });
  });
});

/** Ответ схемы заряда: масса заряда зависит от ВВ варианта — так видно, чья схема где. */
function geometryFor(payload: { explosive_key: string; block_volume_m3: number }) {
  const charge = payload.explosive_key === "ПВВ Гранулит-РП" ? "136" : "179";
  return {
    label: payload.explosive_key === "ПВВ Гранулит-РП" ? "ГРАНУЛИТ-РП" : "ЭВЕРСИН",
    hole: {
      grid_a_m: 4.84, grid_b_m: 4.84, depth_m: 11, overdrill_m: 1, undercharge_m: 2.7, charge_length_m: 8.3,
      charge_diameter_m: 0.157, capacity_kg_per_m: 16.36, charge_mass_kg: Number(charge), yield_m3: 234,
      specific_q_kg_m3: 0.58, explosive_name: payload.explosive_key, explosive_label: "",
    },
    block: {
      block_volume_m3: payload.block_volume_m3, total_holes: 97, drilling_footage_m: 1067,
      total_charge_mass_kg: Number(charge) * 97, specific_q_kg_m3: 0.6,
    },
    initiation: { intermediate_detonators_per_hole: 1, nsi_per_hole: 1, nsi_length_1_m: 12, nsi_length_2_m: 6, detonator_delay_ms: 500 },
    hole_rows: [["Сетка a×b, м", "4.84 × 4.84"], ["Заряд, кг", charge]],
    block_rows: [["Объём блока, м³", String(payload.block_volume_m3)], ["Масса ВВ на блок, кг", String(Number(charge) * 97)]],
  };
}

describe("CalcPage: схемы заряда, сравнение и паспорт", () => {
  beforeEach(() => {
    const inputs = savedInputs("UNIT_PERM");
    inputs.panels.right.explosive_key = "ПЭВВ ЭВЕРСИН Э-100";
    api.calcInputs.mockResolvedValue({ work_object_name: "Карьер Анна", inputs, updated_at: "then" });
    api.optimize.mockResolvedValue({
      variants: [{ crown_mm: 152, specific_q_kg_m3: 0.6, line_of_least_resistance_m: 4.84, grid_a_m: 4.84, grid_b_m: 4.84, grid_label: "4.84 × 4.84", x50_mm: 72.9, oversize_pct: 3.9, target_q_kg_m3: 0.6 }],
    });
    api.geometry.mockImplementation(async (payload: { explosive_key: string; block_volume_m3: number }) => geometryFor(payload));
    api.economics.referenceSnapshot.mockResolvedValue({ revision_id: "REV", sections: { sites: [{ code: "SITE_A", name: "Карьер Анна", is_active: true }] } });
  });

  it("обе схемы доходят до таблиц сравнения и до паспорта, правка карточки пересчитывает свой вариант", async () => {
    renderSheet("Карьер Анна");
    const chargeRow = await screen.findByRole("rowheader", { name: "Заряд, кг" }, { timeout: 3000 });
    expect([...chargeRow.closest("tr")!.querySelectorAll("td")].map((cell) => cell.textContent)).toEqual(["136", "179"]);
    expect(screen.getByText(/В паспорт пойдёт «Вариант 1»: 13\s192 кг ВВ, 97 скважин/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Сохранить паспорт" })).toBeEnabled();

    const leftCard = screen.getByRole("group", { name: "Вариант 1" });
    fireEvent.change(within(leftCard).getByLabelText("Тип ВВ"), { target: { value: "ПЭВВ ЭВЕРСИН Э-100" } });
    // Пересчёт виден сразу: сохранить прошлый блок в паспорт нельзя.
    expect(screen.getByRole("button", { name: "Сохранить паспорт" })).toBeDisabled();
    await waitFor(() =>
      expect([...screen.getByRole("rowheader", { name: "Заряд, кг" }).closest("tr")!.querySelectorAll("td")].map((cell) => cell.textContent)).toEqual(["179", "179"]),
    );
    expect(api.geometry).toHaveBeenLastCalledWith(expect.objectContaining({ explosive_key: "ПЭВВ ЭВЕРСИН Э-100", view: "charge" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Сохранить паспорт" })).toBeEnabled());
  });
});
