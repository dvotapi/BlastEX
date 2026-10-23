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

  it("prints warnings in the warning style, repeated texts included", () => {
    renderPanel({ scheme: "trunk_chains", warnings: ["Фронт инициирования отстаёт.", "Фронт инициирования отстаёт."] });
    const items = screen.getAllByText("Фронт инициирования отстаёт.");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveClass("frag-warnings");
  });

  it("shows the server-picked downhole delay of a trunk_chains network", () => {
    const network = {
      starters: [],
      connectors: [],
      surface_connectors: [],
      starter_items: [],
      system: "nonel",
      timing_params: { scheme: "trunk_chains", downhole_delay_ms: 700 },
    } as unknown as InitiationNetwork;
    renderPanel({ scheme: "trunk_chains", network, params: { ...DEFAULT_TIE_PARAMS, downhole_delay_ms: 500 } });
    expect(screen.getByLabelText("Внутрискважинное замедление, мс")).toHaveValue(700);
  });

  it("leaves the downhole field empty until the scheme is built", () => {
    const network = {
      starters: [],
      connectors: [],
      surface_connectors: [],
      starter_items: [],
      timing_params: { scheme: "row", downhole_delay_ms: 500 },
    } as unknown as InitiationNetwork;
    renderPanel({ scheme: "trunk_chains", network, params: { ...DEFAULT_TIE_PARAMS, downhole_delay_ms: 500 } });
    const field = screen.getByLabelText("Внутрискважинное замедление, мс");
    expect(field).toHaveValue(null);
    expect(field).toHaveAttribute("placeholder", "подбирается");
    expect(
      screen.getByText(
        "Подбирается: наименьшее из 500 / 700 / 1000 мс, при котором импульс успевает пройти трубки в радиусе 30 м до взрыва скважины.",
      ),
    ).toBeInTheDocument();
  });

  it("does not show the downhole delay of a network built by another system", () => {
    const network = {
      system: "detcord",
      starters: [],
      connectors: [],
      surface_connectors: [],
      starter_items: [],
      timing_params: { scheme: "trunk_chains", downhole_delay_ms: 500 },
    } as unknown as InitiationNetwork;
    renderPanel({ scheme: "trunk_chains", network, params: { ...DEFAULT_TIE_PARAMS, system: "nonel" } });
    const field = screen.getByLabelText("Внутрискважинное замедление, мс");
    expect(field).toBeDisabled();
    expect(field).toHaveValue(null);
    expect(field).toHaveAttribute("placeholder", "подбирается");
  });

  it("drops a stale electronic timing mode when trunk_chains is chosen", () => {
    const onSchemeChange = vi.fn();
    const onParamsChange = vi.fn();
    const params = { ...DEFAULT_TIE_PARAMS, system: "electronic" as const, timing_mode: "direction" as const };
    renderPanel({ scheme: "row", params, onSchemeChange, onParamsChange });
    fireEvent.click(screen.getByText("Магистраль + цепочки"));
    expect(onSchemeChange).toHaveBeenCalledWith("trunk_chains");
    expect(onParamsChange).toHaveBeenCalledWith({ timing_mode: "" });
    onParamsChange.mockClear();
    fireEvent.click(screen.getByText("Порядная"));
    expect(onParamsChange).not.toHaveBeenCalled();
  });

  it("hides electronic timing modes for trunk_chains", () => {
    const params = { ...DEFAULT_TIE_PARAMS, system: "electronic" as const, timing_mode: "direction" as const };
    renderPanel({ scheme: "trunk_chains", params });
    expect(screen.queryByText("Электронный тайминг")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Азимут направления, °")).not.toBeInTheDocument();
    expect(screen.queryByText("Назначить электронный тайминг")).not.toBeInTheDocument();
    expect(screen.getByText("Построить схему")).toBeInTheDocument();
    cleanup();
    renderPanel({ scheme: "row", params });
    expect(screen.getByText("Электронный тайминг")).toBeInTheDocument();
    expect(screen.getByText("Назначить электронный тайминг")).toBeInTheDocument();
  });

  it("sends the downhole delay of detcord and electronic to the server params", () => {
    for (const system of ["detcord", "electronic"] as const) {
      const onParamsChange = vi.fn();
      renderPanel({ scheme: "trunk_chains", params: { ...DEFAULT_TIE_PARAMS, system }, onParamsChange });
      const field = screen.getByLabelText("Внутрискважинное замедление, мс");
      expect(field).not.toBeDisabled();
      expect(field).toHaveValue(500);
      fireEvent.change(field, { target: { value: "300" } });
      expect(onParamsChange).toHaveBeenCalledWith({ downhole_delay_ms: 300 });
      cleanup();
    }
  });

  it("snaps trunk and chain steps to the new system's nominals on system change", () => {
    const onParamsChange = vi.fn();
    renderPanel({ scheme: "trunk_chains", params: { ...DEFAULT_TIE_PARAMS, trunk_ms: 17, chain_ms: 67 }, onParamsChange });
    fireEvent.change(screen.getByLabelText("Система инициирования"), { target: { value: "detcord" } });
    expect(onParamsChange).toHaveBeenCalledWith({ system: "detcord", trunk_ms: 20, chain_ms: 42 });
    cleanup();
    const back = vi.fn();
    renderPanel({ scheme: "trunk_chains", params: { ...DEFAULT_TIE_PARAMS, system: "detcord", trunk_ms: 10, chain_ms: 35 }, onParamsChange: back });
    fireEvent.change(screen.getByLabelText("Система инициирования"), { target: { value: "nonel" } });
    expect(back).toHaveBeenCalledWith({ system: "nonel", trunk_ms: 17, chain_ms: 42 });
  });

  it("keeps any step when switching to the electronic system", () => {
    const onParamsChange = vi.fn();
    renderPanel({ scheme: "trunk_chains", params: { ...DEFAULT_TIE_PARAMS, system: "detcord", trunk_ms: 35, chain_ms: 10 }, onParamsChange });
    fireEvent.change(screen.getByLabelText("Система инициирования"), { target: { value: "electronic" } });
    expect(onParamsChange).toHaveBeenCalledWith({ system: "electronic", trunk_ms: 35, chain_ms: 10 });
  });

  it("offers number fields instead of nominal lists for the electronic system", () => {
    const onParamsChange = vi.fn();
    renderPanel({ scheme: "trunk_chains", params: { ...DEFAULT_TIE_PARAMS, system: "electronic", trunk_ms: 30 }, onParamsChange });
    const trunk = screen.getByLabelText("Магистраль, мс");
    expect(trunk.tagName).toBe("INPUT");
    expect(trunk).toHaveAttribute("type", "number");
    expect(trunk).toHaveAttribute("min", "1");
    expect(trunk).toHaveValue(30);
    expect(screen.getByLabelText("Цепочки, мс").tagName).toBe("INPUT");
    fireEvent.change(screen.getByLabelText("Цепочки, мс"), { target: { value: "50" } });
    expect(onParamsChange).toHaveBeenCalledWith({ chain_ms: 50 });
  });

  it("offers detcord relay steps for detcord", () => {
    renderPanel({ scheme: "trunk_chains", params: { ...DEFAULT_TIE_PARAMS, system: "detcord" } });
    const options = Array.from((screen.getByLabelText("Магистраль, мс") as HTMLSelectElement).options).map((o) => o.value);
    expect(options).toEqual(["10", "20", "25", "35", "42"]);
    cleanup();
    renderPanel({ scheme: "trunk_chains" });
    const nsi = Array.from((screen.getByLabelText("Цепочки, мс") as HTMLSelectElement).options).map((o) => o.value);
    expect(nsi).toEqual(["17", "25", "42", "67", "109"]);
  });
});
