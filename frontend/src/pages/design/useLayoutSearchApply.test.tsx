// @vitest-environment jsdom
// «Применить» вариант подбора на уровне страницы: настоящий редьюсер, форма
// «Сетка» и коммутация в состоянии страницы, панель подбора — как на странице.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useReducer, useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/endpoints";
import {
  DEFAULT_PATTERN_PARAMS,
  DEFAULT_TIE_PARAMS,
  emptyDesign,
  emptyHoleGeology,
  emptyNetwork,
  type BlastDesign,
  type Hole,
  type InitiationNetwork,
  type LayoutSearchStatus,
  type LayoutSearchVariant,
  type PatternParams,
  type SchemeType,
  type TieParams,
} from "../../types/design";
import { designReducer, initDesignState, type DesignState } from "./designReducer";
import { LayoutSearchPanel } from "./LayoutSearchPanel";
import { layoutFingerprint } from "./useLayoutSearch";
import { useLayoutSearchApply } from "./useLayoutSearchApply";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function hole(id: string, source: Hole["source"] = "generated"): Hole {
  return {
    id,
    row: 0,
    col: 0,
    collar: { x: 10, y: 5, z: 420 },
    toe: { x: 10, y: 5, z: 408 },
    diameter_mm: 152,
    subdrill_m: 1,
    kind: "production",
    source,
    enabled: true,
    ...emptyHoleGeology(),
  };
}

const VARIANT_NETWORK: InitiationNetwork = {
  ...emptyNetwork(),
  starters: ["n1"],
  connectors: [{ id: "c1", from_hole: "n1", to_hole: "n2", delay_ms: 42, kind: "surface" } as InitiationNetwork["connectors"][number]],
};

function variant(extra: Partial<LayoutSearchVariant> = {}): LayoutSearchVariant {
  return {
    params: { ...DEFAULT_PATTERN_PARAMS, row_azimuth_deg: 35, spacing_a_m: 4.6, burden_b_m: 3.7, front_rows_mode: "pair" },
    cut_flank: "right",
    holes: [hole("n1"), hole("n2")],
    network: VARIANT_NETWORK,
    rejected: false,
    reject_codes: [],
    lsp_out: 0,
    fast_share: 0,
    converging_length_m: 0,
    outside_share: 0.1,
    robust_spread: 0.2,
    hole_count: 2,
    window8_max_holes: 1,
    downhole_ms: 500,
    warnings: [],
    ...extra,
  };
}

function base(extra: Partial<BlastDesign> = {}): BlastDesign {
  return {
    ...emptyDesign(),
    design_id: "d1",
    rock_name: "Гранит",
    holes: [hole("a")],
    network: { ...emptyNetwork(), starters: ["a"] },
    pattern_params: { spacing_a_m: 4, burden_b_m: 4 },
    ...extra,
  };
}

const FORM_A = 4.2;

/** Отпечаток входов страницы до правок: форма — поверх умолчаний, правка шага a. */
async function startFingerprint(design: BlastDesign): Promise<string> {
  const form = { ...DEFAULT_PATTERN_PARAMS, ...(design.pattern_params as Partial<PatternParams>), spacing_a_m: FORM_A };
  return layoutFingerprint({
    contour: design.contour,
    surfaces: design.surfaces,
    domains: design.domains,
    pattern_params: Object.fromEntries(Object.entries(form).filter(([, v]) => v !== undefined)),
    rock_name: design.rock_name,
  });
}

type Probe = {
  state: DesignState;
  patternParams: PatternParams;
  tieScheme: SchemeType;
  tieParams: TieParams;
  error: string;
  dispatch: (action: Parameters<typeof designReducer>[1]) => void;
  setPatternParams: (params: PatternParams) => void;
};

function Page({ design, probe }: { design: BlastDesign; probe: { current: Probe | null } }) {
  const [state, dispatch] = useReducer(designReducer, design, initDesignState);
  // Форма разошлась с паспортом: шаг a поправлен и не сохранён.
  const [patternParams, setPatternParams] = useState<PatternParams>(() => ({
    ...DEFAULT_PATTERN_PARAMS,
    ...(design.pattern_params as Partial<PatternParams>),
    spacing_a_m: FORM_A,
  }));
  const [tieScheme, setTieScheme] = useState<SchemeType>("row");
  const [tieParams, setTieParams] = useState<TieParams>(DEFAULT_TIE_PARAMS);
  const [error, setError] = useState("");
  const layout = useLayoutSearchApply({
    state,
    dispatch,
    patternParams,
    setPatternParams,
    setTieScheme,
    setTieParams,
    rejectLocked: () => false,
    setError,
  });
  probe.current = { state, patternParams, tieScheme, tieParams, error, dispatch, setPatternParams };
  return (
    <>
      <LayoutSearchPanel
        designId={state.present.design_id || null}
        status={layout.search.status}
        stale={layout.stale}
        error={layout.search.error}
        manualCount={state.present.holes.filter((h) => h.source === "manual").length}
        locked={false}
        previewIndex={layout.previewIndex}
        onStart={() => {}}
        onStop={() => {}}
        onPreview={layout.setPreviewIndex}
        onApply={(v) => void layout.apply(v)}
      />
      <output data-testid="preview">{layout.preview ? layout.preview.holes.length : "нет"}</output>
    </>
  );
}

function doneStatus(fingerprint: string, best: LayoutSearchVariant[]): LayoutSearchStatus {
  return {
    state: "done",
    stage: null,
    done: 0,
    total: 0,
    elapsed_s: 140,
    fingerprint,
    result: { best, evaluated: 10, rejected: 0, stopped_early: false, elapsed_s: 140, all_rejected: false, warnings: [] },
    error: null,
  };
}

async function mount(design: BlastDesign, statusFingerprint?: string, best: LayoutSearchVariant[] = [variant(), variant({ cut_flank: "left" })]) {
  const fp = statusFingerprint ?? (await startFingerprint(design));
  vi.spyOn(api.design, "layoutSearchStatus").mockResolvedValue(doneStatus(fp, best));
  const probe: { current: Probe | null } = { current: null };
  render(<Page design={design} probe={probe} />);
  await screen.findAllByRole("button", { name: /^Вариант \d/ });
  return probe as { current: Probe };
}

function card(index: number): HTMLElement {
  return screen.getAllByRole("button", { name: /^Вариант \d/ })[index].closest(".layout-variant-card") as HTMLElement;
}

async function applyVariant(index: number) {
  await act(async () => {
    fireEvent.click(within(card(index)).getByRole("button", { name: "Применить" }));
  });
}

describe("useLayoutSearchApply: «Применить» на странице", () => {
  it("один «Отменить» возвращает скважины, сеть и форму «Сетка»", async () => {
    const design = base();
    const probe = await mount(design);

    await applyVariant(0);
    await waitFor(() => expect(probe.current.state.present.holes.map((h) => h.id)).toEqual(["n1", "n2"]));
    expect(probe.current.state.present.network.connectors).toHaveLength(1);
    expect(probe.current.patternParams.spacing_a_m).toBe(4.6);
    expect(probe.current.patternParams.front_rows_mode).toBe("pair");

    act(() => probe.current.dispatch({ type: "UNDO" }));
    expect(probe.current.state.present.holes.map((h) => h.id)).toEqual(["a"]);
    expect(probe.current.state.present.network.starters).toEqual(["a"]);
    // Форма — как была до применения, с несохранённой правкой шага a.
    await waitFor(() => expect(probe.current.patternParams.spacing_a_m).toBe(FORM_A));
    expect(probe.current.patternParams.front_rows_mode).toBeUndefined();

    act(() => probe.current.dispatch({ type: "REDO" }));
    await waitFor(() => expect(probe.current.patternParams.spacing_a_m).toBe(4.6));
  });

  it("показ снимается; коммутация — «Магистраль + цепочки» с флангом варианта", async () => {
    const probe = await mount(base());
    fireEvent.click(screen.getAllByRole("button", { name: /^Вариант \d/ })[0]);
    expect(screen.getByTestId("preview").textContent).toBe("2");

    // Показан вариант 1, применяется вариант 2 (фланг левый).
    await applyVariant(1);
    await waitFor(() => expect(probe.current.tieScheme).toBe("trunk_chains"));
    expect(probe.current.tieParams.cut_flank).toBe("left");
    expect(probe.current.tieParams.system).toBe("nonel");
    expect(screen.getByTestId("preview").textContent).toBe("нет");
  });

  it("свежий результат после применения не помечается «Устарел»", async () => {
    await mount(base());
    expect(screen.queryByText(/Устарел/)).toBeNull();
    await applyVariant(0);
    // Отпечаток пересчитывается асинхронно — даём ему отработать.
    await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
    expect(screen.queryByText(/Устарел/)).toBeNull();
  });

  it("устаревший результат после применения остаётся «Устарел»", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await mount(base(), "другой-отпечаток");
    await screen.findByText(/^Устарел/);
    await applyVariant(0);
    await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
    expect(screen.getByText(/^Устарел/)).toBeTruthy();
  });

  it("отказ в подтверждении ручных правок — ничего не применено", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const design = base({ holes: [hole("a"), hole("m", "manual")] });
    const probe = await mount(design);
    await applyVariant(0);
    expect(confirm).toHaveBeenCalledWith("Ручные правки (1) будут потеряны. Применить вариант?");
    expect(probe.current.state.present.holes.map((h) => h.id)).toEqual(["a", "m"]);
    expect(probe.current.state.past).toHaveLength(0);
    expect(probe.current.tieScheme).toBe("row");
  });

  it("при доменах скважины варианта сначала пересекаются с геологией — один шаг отмены", async () => {
    const domain = { id: "dom", name: "Гранит" } as unknown as BlastDesign["domains"][number];
    const withGeology = variant().holes.map((h) => ({ ...h, water_intervals: [{ from_m: 0, to_m: 3 }] as unknown as Hole["water_intervals"] }));
    const intercept = vi.spyOn(api.design, "interceptGeology").mockResolvedValue({ holes: withGeology } as never);
    const design = base({ domains: [domain], water_table_z_m: 415 });
    const probe = await mount(design);

    await applyVariant(0);
    await waitFor(() => expect(probe.current.state.present.holes[0].water_intervals).toHaveLength(1));
    expect(intercept).toHaveBeenCalledWith(variant().holes, [domain], 415);
    expect(probe.current.state.past).toHaveLength(1);
  });

  it("сбой пересечения — вариант применяется без геологии, с предупреждением", async () => {
    const domain = { id: "dom", name: "Гранит" } as unknown as BlastDesign["domains"][number];
    vi.spyOn(api.design, "interceptGeology").mockRejectedValue(new Error("Сервер недоступен"));
    const probe = await mount(base({ domains: [domain] }));

    await applyVariant(0);
    await waitFor(() => expect(probe.current.state.present.holes.map((h) => h.id)).toEqual(["n1", "n2"]));
    expect(probe.current.error).toBe("Сервер недоступен");
    expect(probe.current.state.past).toHaveLength(1);
  });
});
