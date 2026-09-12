// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
    items: [{ key: "ПВВ Гранулит-РП", name: "Гранулит-РП", density_t_m3: 0.9, power_mj_kg: 3.8, chart_label: "ГРАНУЛИТ-РП" }],
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

async function loaded(objectPart: string) {
  await waitFor(() => expect(screen.getByRole("button", { name: "Рассчитать варианты" })).toBeEnabled());
  expect(screen.getByLabelText("Объект")).toHaveValue(OBJECTS.find((o) => o.name.includes(objectPart))!.name);
}

/** Дождаться, пока отложенная запись автосохранения (800 мс) точно успела бы уйти. */
const autosaveWindow = () => act(() => new Promise((resolve) => setTimeout(resolve, 1100)));

describe("CalcPage: юнит в шапке и автосохранение", () => {
  it("открытие объекта с юнитом показывает его юнит и ничего не записывает", async () => {
    api.calcInputs.mockResolvedValue({ work_object_name: "Карьер Анна", inputs: null, updated_at: null });
    renderSheet("Карьер Анна");
    await loaded("Анна");
    await waitFor(() => expect(screen.getByLabelText("Юнит")).toHaveValue("UNIT_PERM"));
    await autosaveWindow();
    expect(api.saveCalcInputs).not.toHaveBeenCalled();
  });

  it("сохранённые до юнитов настройки объекта с юнитом не переписываются при открытии", async () => {
    api.calcInputs.mockResolvedValue({ work_object_name: "Карьер Лом", inputs: savedInputs(""), updated_at: "then" });
    renderSheet("Карьер Лом");
    await loaded("Лом");
    await waitFor(() => expect(screen.getByLabelText("Юнит")).toHaveValue("UNIT_URAL"));
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
    await waitFor(() => expect(screen.getByLabelText("Юнит")).toHaveValue("UNIT_PERM"));
    fireEvent.change(screen.getByLabelText("Объект"), { target: { value: "Карьер Жуков" } });
    await loaded("Жуков");
    await waitFor(() => expect(screen.getByLabelText("Юнит")).toHaveValue("UNIT_PERM"));
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
    await waitFor(() => expect(screen.getByLabelText("Юнит")).toBeInTheDocument());
    expect(screen.getByLabelText("Юнит")).toBeDisabled();
    await act(async () => release({ work_object_name: "Карьер Анна", inputs: null, updated_at: null }));
    await waitFor(() => expect(screen.getByLabelText("Юнит")).toBeEnabled());
  });
});
