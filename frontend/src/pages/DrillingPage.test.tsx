// @vitest-environment jsdom
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithWorkspace } from "../test/render";

vi.mock("../api/endpoints", () => ({
  api: {
    economics: { technicalPassports: vi.fn(), revisions: vi.fn(), referenceSnapshot: vi.fn() },
    blockEconomics: { modelDefaults: vi.fn(), runs: vi.fn(), variants: vi.fn(), exportUrl: (id: string) => `/x/${id}` },
    drillingUnit: vi.fn(),
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
  vi.mocked(api.drillingUnit).mockResolvedValue(new Promise(() => {}) as never);
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

  it("старый калькулятор спрятан в сворачиваемый блок", async () => {
    renderWithWorkspace(
      <BlockEconomicsSessionProvider passportId="PASSPORT-1">
        <DrillingPage />
      </BlockEconomicsSessionProvider>,
    );
    await screen.findByRole("radio", { name: "Методика ФОТ" });
    const legacy = document.querySelector("details.drilling-legacy") as HTMLDetailsElement;
    expect(legacy).not.toBeNull();
    expect(legacy.open).toBe(false);
  });
});
