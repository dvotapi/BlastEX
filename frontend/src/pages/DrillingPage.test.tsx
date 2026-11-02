// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithWorkspace } from "../test/render";

vi.mock("../api/endpoints", () => ({
  api: {
    economics: { technicalPassports: vi.fn(), revisions: vi.fn(), referenceSnapshot: vi.fn() },
    blockEconomics: { modelDefaults: vi.fn(), runs: vi.fn(), variants: vi.fn(), saveRun: vi.fn(), exportUrl: (id: string) => `/x/${id}` },
  },
}));

import { api } from "../api/endpoints";
import { BlockEconomicsSessionProvider } from "./economics/BlockEconomicsSessionContext";
import { defaultsFixture, economicsFixture } from "./economics/testFixtures";
import { DrillingPage } from "./DrillingPage";

beforeEach(() => {
  const defaults = defaultsFixture();
  vi.mocked(api.economics.technicalPassports).mockResolvedValue([defaults.passport]);
  vi.mocked(api.economics.revisions).mockResolvedValue([]);
  vi.mocked(api.economics.referenceSnapshot).mockResolvedValue({ sections: { sites: [] } } as never);
  vi.mocked(api.blockEconomics.modelDefaults).mockResolvedValue(defaults);
  vi.mocked(api.blockEconomics.runs).mockResolvedValue([]);
  vi.mocked(api.blockEconomics.variants).mockResolvedValue({
    reference_revision_id: "REV-1",
    variants: [{ name: "Вариант 1", economics: economicsFixture() }],
  });
});

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe("DrillingPage", () => {
  it("переключатель на методику меняет черновик блока, и расчёт идёт с payroll_source = PAYROLL", async () => {
    renderWithWorkspace(
      <BlockEconomicsSessionProvider passportId="PASSPORT-1">
        <DrillingPage />
      </BlockEconomicsSessionProvider>,
    );

    const methodology = await screen.findByRole("radio", { name: "Методика ФОТ" });
    expect(screen.getByRole("radio", { name: "Ставки" })).toBeChecked();

    await userEvent.setup().click(methodology);

    expect(screen.getByRole("radio", { name: "Методика ФОТ" })).toBeChecked();
    await waitFor(() => {
      const calls = vi.mocked(api.blockEconomics.variants).mock.calls;
      expect(calls[calls.length - 1][1][0].parameters.payroll_source).toBe("PAYROLL");
    });
  });

  it("старого калькулятора цены п.м. на странице нет", async () => {
    renderWithWorkspace(
      <BlockEconomicsSessionProvider passportId="PASSPORT-1">
        <DrillingPage />
      </BlockEconomicsSessionProvider>,
    );
    await screen.findByRole("radio", { name: "Методика ФОТ" });
    expect(document.querySelector("details.drilling-legacy")).toBeNull();
    expect(screen.queryByText(/Калькулятор цены п\.м\./)).toBeNull();
  });

  it("правка источника ФОТ сохраняется кнопкой сценария блока, а не полосой рабочего пространства", async () => {
    vi.mocked(api.blockEconomics.saveRun).mockResolvedValue({ id: "RUN-1" } as never);
    renderWithWorkspace(
      <BlockEconomicsSessionProvider passportId="PASSPORT-1">
        <DrillingPage />
      </BlockEconomicsSessionProvider>,
    );
    const user = userEvent.setup();
    const save = await screen.findByRole("button", { name: "Сохранить сценарий блока" });
    // Свежий сценарий ещё ни разу не сохранялся.
    expect(save).toBeEnabled();

    await user.click(await screen.findByRole("radio", { name: "Методика ФОТ" }));
    expect(screen.getByText(/не сохранён/)).toBeInTheDocument();

    await user.click(save);

    await waitFor(() => expect(api.blockEconomics.saveRun).toHaveBeenCalledTimes(1));
    const saved = vi.mocked(api.blockEconomics.saveRun).mock.calls[0];
    expect(saved[1].payroll_source).toBe("PAYROLL");
    await waitFor(() => expect(screen.getByText("Сценарий блока сохранён.")).toBeInTheDocument());
    expect(save).toBeDisabled();
  });

  it("бегунок смен станка меняет rig_plan_shifts черновика по отпусканию, пересчёт идёт с новым значением", async () => {
    const defaults = defaultsFixture();
    defaults.parameters.rig_plan_shifts = 40;
    vi.mocked(api.blockEconomics.modelDefaults).mockResolvedValue(defaults);
    renderWithWorkspace(
      <BlockEconomicsSessionProvider passportId="PASSPORT-1">
        <DrillingPage />
      </BlockEconomicsSessionProvider>,
    );

    const slider = (await screen.findByRole("slider", { name: "Плановые смены станка в месяц" })) as HTMLInputElement;
    expect(slider.value).toBe("40");
    expect(screen.getByText("норматив 40")).toBeInTheDocument();
    await waitFor(() => expect(api.blockEconomics.variants).toHaveBeenCalled());
    const before = vi.mocked(api.blockEconomics.variants).mock.calls.length;

    fireEvent.change(slider, { target: { value: "30" } });
    fireEvent.change(slider, { target: { value: "25" } });
    fireEvent.pointerUp(slider);

    await waitFor(() => {
      const calls = vi.mocked(api.blockEconomics.variants).mock.calls;
      expect(calls.length).toBe(before + 1);
      expect(calls[calls.length - 1][1][0].parameters.rig_plan_shifts).toBe("25");
    });
    // Стоимость метра на странице — из ответа расчёта.
    expect(screen.getAllByText("260,00 ₽/м").length).toBeGreaterThan(0);

    await userEvent.setup().click(screen.getByRole("button", { name: "Сбросить к нормативу" }));
    await waitFor(() => {
      const calls = vi.mocked(api.blockEconomics.variants).mock.calls;
      expect(calls[calls.length - 1][1][0].parameters.rig_plan_shifts).toBeNull();
    });
    expect(slider.value).toBe("40");
  });
});
