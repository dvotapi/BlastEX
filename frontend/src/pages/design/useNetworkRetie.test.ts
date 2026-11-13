// @vitest-environment jsdom
// Пересчёт коммутации после сдвига (TASK-017, PR 3): сеть шаблона —
// сама, сразу после отпускания или через секунду после серии стрелок;
// правленая — только кнопкой; ответ к сменившемуся документу не применяется.
import { act, renderHook } from "@testing-library/react";
import { useReducer } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { emptyDesign, emptyHoleGeology, emptyNetwork, type Hole, type InitiationNetwork, type TieGenerateResponse } from "../../types/design";
import { designReducer, initDesignState, MOVE_SERIES_GAP_MS } from "./designReducer";
import { GEOMETRY_STALE_TEXT, RETIE_INCOMPLETE_HINT } from "./retie";
import { useNetworkRetie, type RetieFetcher } from "./useNetworkRetie";

function hole(id: string, x: number): Hole {
  return {
    id,
    row: 0,
    col: 0,
    collar: { x, y: 0, z: 0 },
    toe: { x, y: 0, z: -10 },
    diameter_mm: 165,
    subdrill_m: 1,
    kind: "production",
    source: "generated",
    enabled: true,
    ...emptyHoleGeology(),
  };
}

function network(origin?: string): InitiationNetwork {
  return {
    ...emptyNetwork(),
    starters: ["a"],
    connectors: [{ from_hole: "a", to_hole: "b", delay_ms: 25, kind: "surface_nsi" }],
    timing_params: { scheme: "trunk_chains", trunk_ms: 25, chain_ms: 42, ...(origin ? { origin } : {}) },
  };
}

const REBUILT: InitiationNetwork = {
  ...emptyNetwork(),
  starters: ["b"],
  connectors: [{ from_hole: "b", to_hole: "a", delay_ms: 25, kind: "surface_nsi" }],
  timing_params: { scheme: "trunk_chains", origin: "template", trunk_ms: 25, chain_ms: 42 },
};

function reply(net: InitiationNetwork = REBUILT, warnings: string[] = []): TieGenerateResponse {
  return { network: net, starters_count: 1, connectors_count: 1, warnings };
}

type Call = { resolve: (value: TieGenerateResponse) => void; reject: (reason: unknown) => void; signal?: AbortSignal; scheme: string; params: Record<string, unknown> };

function setup(origin: string | null = "template", editable = true) {
  const calls: Call[] = [];
  const fetcher: RetieFetcher = (_holes, scheme, params, _contour, options) =>
    new Promise((resolve, reject) => calls.push({ resolve, reject, signal: options?.signal, scheme, params }));
  const onApplied = vi.fn();
  const design = { ...emptyDesign(), design_id: "d", holes: [hole("a", 0), hole("b", 5)], network: network(origin ?? undefined) };
  const view = renderHook(() => {
    const [state, dispatch] = useReducer(designReducer, design, initDesignState);
    return { state, dispatch, retie: useNetworkRetie({ state, dispatch, editable, fetcher, onApplied }) };
  });
  const move = (series?: number) =>
    act(() => view.result.current.dispatch({ type: "MOVE_HOLES", ids: ["a"], dx: 1, dy: 0, ...(series !== undefined ? { series } : {}) }));
  return { view, calls, move, onApplied };
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("useNetworkRetie", () => {
  it("сеть шаблона пересчитывается сразу после сдвига и вливается в запись отмены", async () => {
    const { view, calls, move, onApplied } = setup();
    move();
    expect(view.result.current.retie.stale).toBe(true);
    await act(async () => vi.advanceTimersByTime(0));
    expect(calls).toHaveLength(1);
    expect(calls[0].scheme).toBe("trunk_chains");
    expect(calls[0].params).toEqual({ trunk_ms: 25, chain_ms: 42, system: "nonel" });
    calls[0].resolve(reply(REBUILT, ["Ряды идут поперёк бровки"]));
    await flush();
    const { state, retie } = view.result.current;
    expect(state.present.network.starters).toEqual(["b"]);
    expect(state.past).toHaveLength(1);
    expect(retie.stale).toBe(false);
    expect(retie.summary).toBe("Коммутация пересчитана: изменилось связей — 2, вруб сменился.");
    expect(onApplied).toHaveBeenCalledWith(REBUILT, ["Ряды идут поперёк бровки"]);
  });

  it("после серии стрелок — через секунду после последнего нажатия", async () => {
    const { calls, move } = setup();
    move(1000);
    await act(async () => vi.advanceTimersByTime(MOVE_SERIES_GAP_MS - 100));
    move(1500);
    await act(async () => vi.advanceTimersByTime(MOVE_SERIES_GAP_MS - 100));
    expect(calls).toHaveLength(0);
    await act(async () => vi.advanceTimersByTime(200));
    expect(calls).toHaveLength(1);
  });

  it("правленая сеть и сеть до PR 3 — только пометка, без запроса", async () => {
    for (const origin of ["edited", null]) {
      const { view, calls, move } = setup(origin);
      move();
      await act(async () => vi.advanceTimersByTime(MOVE_SERIES_GAP_MS * 2));
      expect(calls).toHaveLength(0);
      expect(view.result.current.retie.stale).toBe(true);
      expect(view.result.current.retie.staleText).toBe(GEOMETRY_STALE_TEXT);
      expect(view.result.current.retie.canRecompute).toBe(origin === "edited");
      expect(view.result.current.retie.hint).toBe(origin ? "" : RETIE_INCOMPLETE_HINT);
      view.unmount();
    }
  });

  it("второй сдвиг до ответа отменяет запрос, поздний ответ не применяется", async () => {
    const { view, calls, move } = setup();
    move();
    await act(async () => vi.advanceTimersByTime(0));
    move();
    expect(calls[0].signal?.aborted).toBe(true);
    calls[0].resolve(reply());
    await flush();
    expect(view.result.current.state.present.network.starters).toEqual(["a"]);
    await act(async () => vi.advanceTimersByTime(0));
    expect(calls).toHaveLength(2);
  });

  it("ошибка сервера — пометка остаётся, повторного запроса нет", async () => {
    const { view, calls, move } = setup();
    move();
    await act(async () => vi.advanceTimersByTime(0));
    calls[0].reject(new Error("Сервер недоступен"));
    await flush();
    await act(async () => vi.advanceTimersByTime(MOVE_SERIES_GAP_MS * 3));
    expect(calls).toHaveLength(1);
    expect(view.result.current.retie.stale).toBe(true);
    expect(view.result.current.retie.error).toBe("Сервер недоступен");
  });

  it("утверждённый паспорт не пересчитывается и кнопка закрыта", async () => {
    const { view, calls, move } = setup("template", false);
    move();
    await act(async () => vi.advanceTimersByTime(MOVE_SERIES_GAP_MS));
    expect(calls).toHaveLength(0);
    expect(view.result.current.retie.canRecompute).toBe(false);
  });

  it("ручной пересчёт — своя запись отмены", async () => {
    const { view, calls, move } = setup("edited");
    move();
    act(() => view.result.current.retie.recompute());
    expect(view.result.current.retie.pending).toBe(true);
    calls[0].resolve(reply());
    await flush();
    expect(view.result.current.state.past).toHaveLength(2);
    expect(view.result.current.retie.pending).toBe(false);
  });

  it("ручной пересчёт: документ сменился сам до ответа — сообщение, а не тишина", async () => {
    const { view, calls, move } = setup("edited");
    move();
    act(() => view.result.current.retie.recompute());
    const present = view.result.current.state.present;
    act(() =>
      view.result.current.dispatch({
        type: "RECOMPUTE_HOLES",
        holes: present.holes.map((h) => ({ ...h, collar: { ...h.collar, z: 7 } })),
      }),
    );
    expect(calls[0].signal?.aborted).toBe(false);
    calls[0].resolve(reply());
    await flush();
    expect(view.result.current.state.present.network.starters).toEqual(["a"]);
    expect(view.result.current.retie.error).toBe("Проект изменился, пока пересчитывалась коммутация, — пересчитайте ещё раз.");
  });
});
