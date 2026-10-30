// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/endpoints", () => ({
  api: {
    economics: { technicalPassports: vi.fn(), revisions: vi.fn(), referenceSnapshot: vi.fn() },
    blockEconomics: { modelDefaults: vi.fn(), runs: vi.fn(), variants: vi.fn(), exportUrl: (id: string) => `/x/${id}` },
  },
}));

import { api } from "../../api/endpoints";
import { BlockEconomicsSessionProvider, useBlockEconomicsSessionContext } from "./BlockEconomicsSessionContext";
import { defaultsFixture, economicsFixture } from "./testFixtures";

function Reader() {
  const session = useBlockEconomicsSessionContext();
  return (
    <>
      <output data-testid="source">{session.activeDraft?.parameters.payroll_source ?? "—"}</output>
      <button type="button" onClick={() => session.patchDraft(session.activeId, { payroll_source: "PAYROLL" })}>
        на методику
      </button>
    </>
  );
}

function Pages() {
  const [shown, setShown] = useState(true);
  return (
    <BlockEconomicsSessionProvider passportId="PASSPORT-1">
      <button type="button" onClick={() => setShown((value) => !value)}>
        переключить
      </button>
      {shown && <Reader />}
    </BlockEconomicsSessionProvider>
  );
}

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

describe("BlockEconomicsSessionProvider", () => {
  it("правка черновика переживает уход страницы и возврат, каталог грузится один раз", async () => {
    render(<Pages />);
    await waitFor(() => expect(screen.getByTestId("source")).toHaveTextContent("RATES"));

    await act(async () => screen.getByRole("button", { name: "на методику" }).click());
    expect(screen.getByTestId("source")).toHaveTextContent("PAYROLL");

    await act(async () => screen.getByRole("button", { name: "переключить" }).click());
    expect(screen.queryByTestId("source")).toBeNull();
    await act(async () => screen.getByRole("button", { name: "переключить" }).click());

    expect(screen.getByTestId("source")).toHaveTextContent("PAYROLL");
    expect(api.blockEconomics.modelDefaults).toHaveBeenCalledTimes(1);
  });
});
