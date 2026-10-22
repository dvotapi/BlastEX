// @vitest-environment jsdom
// Панель «Коммутация»: шаблон «Магистраль + цепочки» — ступени НСИ, вруб у фланга,
// подбор внутрискважинного замедления сервером и предупреждения построения.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_TIE_PARAMS, type InitiationNetwork } from "../../types/design";
import { TiePanel } from "./TiePanel";

afterEach(cleanup);

const noop = () => {};

function renderPanel(over: Record<string, unknown> = {}) {
  const props = {
    scheme: "row",
    params: DEFAULT_TIE_PARAMS,
    network: { starters: [], connectors: [], surface_connectors: [], starter_items: [] } as unknown as InitiationNetwork,
    selectedCount: 0,
    pendingFromId: null,
    warnings: [],
    onSchemeChange: noop,
    onParamsChange: noop,
    onGenerate: noop,
    onUpdateTie: noop,
    onRemoveTie: noop,
    onToggleStarters: noop,
    busy: false,
    ...over,
  } as unknown as Parameters<typeof TiePanel>[0];
  return render(<TiePanel {...props} />);
}

describe("TiePanel trunk_chains", () => {
  it("selects the scheme by its button", () => {
    const onSchemeChange = vi.fn();
    renderPanel({ onSchemeChange });
    fireEvent.click(screen.getByText("Магистраль + цепочки"));
    expect(onSchemeChange).toHaveBeenCalledWith("trunk_chains");
    expect(screen.getByText("вруб у фланга, 25 / 42 мс")).toBeInTheDocument();
  });

  it("shows trunk, chain and flank fields and disables downhole delay for nonel", () => {
    renderPanel({ scheme: "trunk_chains" });
    expect(screen.getByLabelText("Магистраль, мс")).toBeInTheDocument();
    expect(screen.getByLabelText("Цепочки, мс")).toBeInTheDocument();
    expect(screen.getByLabelText("Вруб у фланга")).toBeInTheDocument();
    expect(screen.queryByLabelText("Интервал замедления, мс")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Внутрискважинное замедление, мс")).toBeDisabled();
  });

  it("keeps downhole delay editable for electronic system", () => {
    renderPanel({ scheme: "trunk_chains", params: { ...DEFAULT_TIE_PARAMS, system: "electronic" } });
    expect(screen.getByLabelText("Внутрискважинное замедление, мс")).not.toBeDisabled();
  });

  it("keeps the interval field for other schemes", () => {
    renderPanel({ scheme: "row" });
    expect(screen.getByLabelText("Интервал замедления, мс")).toBeInTheDocument();
    expect(screen.getByLabelText("Внутрискважинное замедление, мс")).not.toBeDisabled();
  });

  it("prints warnings", () => {
    renderPanel({ scheme: "trunk_chains", warnings: ["Фронт инициирования отстаёт."] });
    expect(screen.getByText("Фронт инициирования отстаёт.")).toBeInTheDocument();
  });
});
