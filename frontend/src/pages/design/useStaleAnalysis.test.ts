// @vitest-environment jsdom
// Результат «Рассчитать тайминг» сбрасывается, когда меняется набор скважин,
// их устья в плане, вид или включённость, сеть коммутации (и отменой/повтором),
// порода или сетка a × b: иначе слой темпа и сводка панели «Тайминг» показывают
// старую сетку и старые границы. Правки, не трогающие эти входы (глубина,
// геология), и запись времён срабатывания после расчёта анализ не сбрасывают.
import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { emptyHoleGeology, emptyNetwork, type BlockContour, type Hole, type InitiationNetwork } from "../../types/design";
import {
  analysisInputsKey,
  holesLayoutKey,
  isResponseCurrent,
  MAPS_REFRESH_DELAY_MS,
  mapsInputsKey,
  shouldRefetchMaps,
  useKeyChangeReset,
  useStaleAnalysisReset,
  useStaleMapsRefresh,
  type AnalysisInputs,
} from "./useStaleAnalysis";

const CONTOUR: AnalysisInputs["contour"] = {
  vertices: [{ x: 0, y: 0, z: 420 }, { x: 20, y: 0, z: 420 }, { x: 20, y: 16, z: 420 }],
  free_faces: [[0, 1]],
};

function hole(id: string, extra: Partial<Hole> = {}): Hole {
  return {
    id,
    row: 0,
    col: 0,
    collar: { x: 10, y: 5, z: 420 },
    toe: { x: 10, y: 5, z: 408 },
    diameter_mm: 152,
    subdrill_m: 1,
    kind: "production",
    source: "generated",
    enabled: true,
    ...emptyHoleGeology(),
    ...extra,
  };
}

describe("holesLayoutKey", () => {
  const base = [hole("1-01"), hole("1-02", { collar: { x: 14, y: 5, z: 420 } })];

  it("ignores depth, z and geology", () => {
    const deeper = base.map((h) => ({ ...h, toe: { ...h.toe, z: 400 }, collar: { ...h.collar, z: 421 }, subdrill_m: 2 }));
    expect(holesLayoutKey(deeper)).toBe(holesLayoutKey(base));
  });

  it("changes on move, toggle, kind, add and delete", () => {
    const key = holesLayoutKey(base);
    expect(holesLayoutKey([{ ...base[0], collar: { x: 10.5, y: 5, z: 420 } }, base[1]])).not.toBe(key);
    expect(holesLayoutKey([{ ...base[0], enabled: false }, base[1]])).not.toBe(key);
    expect(holesLayoutKey([{ ...base[0], kind: "presplit" }, base[1]])).not.toBe(key);
    expect(holesLayoutKey([...base, hole("1-03")])).not.toBe(key);
    expect(holesLayoutKey([base[0]])).not.toBe(key);
  });
});

describe("analysisInputsKey", () => {
  const inputs: AnalysisInputs = { holes: [hole("1-01")], network: emptyNetwork(), rockName: "Гранит", spacingAM: 4.41, burdenBM: 3.53, contour: CONTOUR, defaultKind: "production" };

  it("changes on rock, spacing and burden", () => {
    const key = analysisInputsKey(inputs);
    expect(analysisInputsKey({ ...inputs })).toBe(key);
    expect(analysisInputsKey({ ...inputs, rockName: "Базальт" })).not.toBe(key);
    expect(analysisInputsKey({ ...inputs, spacingAM: 5 })).not.toBe(key);
    expect(analysisInputsKey({ ...inputs, burdenBM: 4 })).not.toBe(key);
  });

  it("changes on contour in plan, free faces and default kind, not on vertex z", () => {
    const key = analysisInputsKey(inputs);
    const moved = { ...CONTOUR, vertices: [CONTOUR.vertices[0], { x: 22, y: 0, z: 420 }, CONTOUR.vertices[2]] };
    expect(analysisInputsKey({ ...inputs, contour: moved })).not.toBe(key);
    expect(analysisInputsKey({ ...inputs, contour: { ...CONTOUR, free_faces: [[1, 2]] } })).not.toBe(key);
    expect(analysisInputsKey({ ...inputs, defaultKind: "buffer" })).not.toBe(key);
    const lowered = { ...CONTOUR, vertices: CONTOUR.vertices.map((v) => ({ ...v, z: 410 })) };
    expect(analysisInputsKey({ ...inputs, contour: lowered })).toBe(key);
  });
});

describe("useStaleAnalysisReset", () => {
  function inputsOf(holes: Hole[], extra: Partial<AnalysisInputs> = {}): AnalysisInputs {
    return { holes, network: emptyNetwork(), rockName: "Гранит", spacingAM: 4.41, burdenBM: 3.53, contour: CONTOUR, defaultKind: "production", ...extra };
  }

  it("resets only when the hole layout changes", () => {
    const reset = vi.fn();
    const first = [hole("1-01"), hole("1-02", { collar: { x: 14, y: 5, z: 420 } })];
    const { rerender } = renderHook(({ inputs }) => useStaleAnalysisReset(inputs, reset), {
      initialProps: { inputs: inputsOf(first) },
    });
    expect(reset).not.toHaveBeenCalled();

    // Новый массив с той же раскладкой (сеть, пересчёт глубины) — не сброс.
    rerender({ inputs: inputsOf(first.map((h) => ({ ...h, toe: { ...h.toe, z: 400 } }))) });
    expect(reset).not.toHaveBeenCalled();

    rerender({ inputs: inputsOf([first[0], { ...first[1], collar: { x: 15, y: 5, z: 420 } }]) });
    expect(reset).toHaveBeenCalledTimes(1);

    rerender({ inputs: inputsOf([first[0], { ...first[1], collar: { x: 15, y: 5, z: 420 }, enabled: false }]) });
    expect(reset).toHaveBeenCalledTimes(2);
  });

  it("resets when rock, spacing or burden change", () => {
    const reset = vi.fn();
    const holes = [hole("1-01")];
    const { rerender } = renderHook(({ inputs }) => useStaleAnalysisReset(inputs, reset), {
      initialProps: { inputs: inputsOf(holes) },
    });
    rerender({ inputs: inputsOf(holes) });
    expect(reset).not.toHaveBeenCalled();

    rerender({ inputs: inputsOf(holes, { rockName: "Базальт" }) });
    expect(reset).toHaveBeenCalledTimes(1);

    rerender({ inputs: inputsOf(holes, { rockName: "Базальт", spacingAM: 5 }) });
    expect(reset).toHaveBeenCalledTimes(2);

    rerender({ inputs: inputsOf(holes, { rockName: "Базальт", spacingAM: 5, burdenBM: 4 }) });
    expect(reset).toHaveBeenCalledTimes(3);
  });

  it("resets when the contour or default kind change", () => {
    const reset = vi.fn();
    const holes = [hole("1-01")];
    const { rerender } = renderHook(({ inputs }) => useStaleAnalysisReset(inputs, reset), {
      initialProps: { inputs: inputsOf(holes) },
    });
    // Новый объект контура с той же геометрией — не сброс.
    rerender({ inputs: inputsOf(holes, { contour: { ...CONTOUR, vertices: [...CONTOUR.vertices] } }) });
    expect(reset).not.toHaveBeenCalled();

    const moved = { ...CONTOUR, vertices: [CONTOUR.vertices[0], { x: 22, y: 0, z: 420 }, CONTOUR.vertices[2]] };
    rerender({ inputs: inputsOf(holes, { contour: moved }) });
    expect(reset).toHaveBeenCalledTimes(1);

    rerender({ inputs: inputsOf(holes, { contour: moved, defaultKind: "buffer" }) });
    expect(reset).toHaveBeenCalledTimes(2);
  });

  it("resets on undo-like network change but not on firing_events", () => {
    const reset = vi.fn();
    const holes = [hole("1-01"), hole("1-02", { collar: { x: 14, y: 5, z: 420 } })];
    const tied: InitiationNetwork = {
      ...emptyNetwork(),
      starters: ["1-01"],
      starter_items: [{ id: "st-1-01", hole_id: "1-01", delay_ms: 0, kind: "starter" }],
      surface_connectors: [{ id: "c1", from_hole: "1-01", to_hole: "1-02", delay_ms: 25, kind: "surface", product: "" }],
      connectors: [{ from_hole: "1-01", to_hole: "1-02", delay_ms: 25, kind: "surface" }],
    };
    const { rerender } = renderHook(({ inputs }) => useStaleAnalysisReset(inputs, reset), {
      initialProps: { inputs: inputsOf(holes, { network: tied }) },
    });

    // «Рассчитать тайминг» дописывает в сеть только времена срабатывания — не сброс.
    const fired = { ...tied, firing_events: [{ hole_id: "1-01", time_ms: 0 }] } as unknown as InitiationNetwork;
    rerender({ inputs: inputsOf(holes, { network: fired }) });
    expect(reset).not.toHaveBeenCalled();

    // Отмена: связь и стартер вернулись к пустой сети.
    rerender({ inputs: inputsOf(holes, { network: emptyNetwork() }) });
    expect(reset).toHaveBeenCalledTimes(1);

    // Повтор: сеть снова со связью.
    rerender({ inputs: inputsOf(holes, { network: tied }) });
    expect(reset).toHaveBeenCalledTimes(2);

    // Правка замедления связи — сброс.
    const slower = {
      ...tied,
      surface_connectors: [{ ...tied.surface_connectors[0], delay_ms: 42 }],
    };
    rerender({ inputs: inputsOf(holes, { network: slower }) });
    expect(reset).toHaveBeenCalledTimes(3);
  });
});

describe("isResponseCurrent", () => {
  it("accepts a response only for unchanged inputs", () => {
    expect(isResponseCurrent("a", "a")).toBe(true);
    expect(isResponseCurrent("a", "b")).toBe(false);
  });
});

describe("useKeyChangeReset", () => {
  it("resets on key change and reads the current key for an in-flight request", () => {
    const reset = vi.fn();
    const { result, rerender } = renderHook(({ key }) => useKeyChangeReset(key, reset), { initialProps: { key: "k1" } });
    expect(reset).not.toHaveBeenCalled();
    // Запрос начат при k1.
    const startKey = result.current();
    rerender({ key: "k1" });
    expect(reset).not.toHaveBeenCalled();
    expect(isResponseCurrent(startKey, result.current())).toBe(true);

    // Пока шёл запрос, входы поменялись: сброс, а поздний ответ — не текущий.
    const read = result.current;
    rerender({ key: "k2" });
    expect(reset).toHaveBeenCalledTimes(1);
    expect(result.current).toBe(read);
    expect(isResponseCurrent(startKey, read())).toBe(false);
  });

  it("useStaleAnalysisReset returns the current analysis key", () => {
    const inputs: AnalysisInputs = { holes: [hole("1-01")], network: emptyNetwork(), rockName: "Гранит", spacingAM: 4.41, burdenBM: 3.53, contour: CONTOUR, defaultKind: "production" };
    const { result, rerender } = renderHook(({ inputs }) => useStaleAnalysisReset(inputs, () => {}), { initialProps: { inputs } });
    const startKey = result.current();
    expect(startKey).toBe(analysisInputsKey(inputs));
    // Запись времён срабатывания — ответ остаётся текущим.
    const fired = { ...inputs.network, firing_events: [{ hole_id: "1-01", time_ms: 0 }] } as unknown as InitiationNetwork;
    rerender({ inputs: { ...inputs, network: fired } });
    expect(isResponseCurrent(startKey, result.current())).toBe(true);
    rerender({ inputs: { ...inputs, rockName: "Базальт" } });
    expect(isResponseCurrent(startKey, result.current())).toBe(false);
  });
});

describe("mapsInputsKey", () => {
  const contour: BlockContour = { ...CONTOUR, bench: { crest_z_m: 420, toe_z_m: 408, face_angle_deg: 75 }, name: "Б-1", cad: null };
  const holes = [hole("1-01")];

  it("changes on toe geometry: contour, faces, bench, CAD, holes", () => {
    const key = mapsInputsKey(holes, contour);
    expect(mapsInputsKey([...holes], { ...contour, vertices: [...contour.vertices] })).toBe(key);
    const moved = { ...contour, vertices: [contour.vertices[0], { x: 22, y: 0, z: 420 }, contour.vertices[2]] };
    expect(mapsInputsKey(holes, moved)).not.toBe(key);
    expect(mapsInputsKey(holes, { ...contour, free_faces: [[1, 2]] })).not.toBe(key);
    expect(mapsInputsKey(holes, { ...contour, bench: { ...contour.bench, face_angle_deg: 70 } })).not.toBe(key);
    expect(mapsInputsKey(holes, { ...contour, bench: { ...contour.bench, toe_z_m: 405 } })).not.toBe(key);
    expect(mapsInputsKey(holes, { ...contour, bench: { ...contour.bench, crest_z_m: 421 } })).not.toBe(key);
    const cad = { source_id: "s1", built_at: "2026-10-01", edited: false } as BlockContour["cad"];
    const withCad = mapsInputsKey(holes, { ...contour, cad });
    expect(withCad).not.toBe(key);
    expect(mapsInputsKey(holes, { ...contour, cad: { ...cad!, source_id: "s2" } })).not.toBe(withCad);
    expect(mapsInputsKey(holes, { ...contour, cad: { ...cad!, edited: true } })).not.toBe(withCad);
    expect(mapsInputsKey([{ ...holes[0], collar: { x: 10, y: 5, z: 421 } }], contour)).not.toBe(key);
    expect(mapsInputsKey([{ ...holes[0], toe: { x: 10, y: 5, z: 400 } }], contour)).not.toBe(key);
    expect(mapsInputsKey([...holes, hole("1-02")], contour)).not.toBe(key);
  });

  it("ignores the contour name", () => {
    expect(mapsInputsKey(holes, { ...contour, name: "Б-2" })).toBe(mapsInputsKey(holes, contour));
  });
});

describe("shouldRefetchMaps", () => {
  it("refetches when maps were loaded or a map metric is selected", () => {
    expect(shouldRefetchMaps(true, false)).toBe(true);
    expect(shouldRefetchMaps(false, true)).toBe(true);
    expect(shouldRefetchMaps(true, true)).toBe(true);
    expect(shouldRefetchMaps(false, false)).toBe(false);
  });
});

describe("useStaleMapsRefresh", () => {
  afterEach(() => vi.useRealTimers());

  function setup(active: boolean) {
    vi.useFakeTimers();
    const clear = vi.fn();
    const refetch = vi.fn();
    const view = renderHook(({ key }) => useStaleMapsRefresh(key, { active: () => active, clear, refetch }), {
      initialProps: { key: "k1" },
    });
    return { clear, refetch, ...view };
  }

  it("grid build: maps loaded, depth recompute changes key — clear now, refetch once after the pause", () => {
    const { clear, refetch, rerender } = setup(true);
    // «Построить сетку» и сразу автопересчёт глубин — две смены подряд.
    rerender({ key: "k2" });
    rerender({ key: "k3" });
    expect(clear).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(MAPS_REFRESH_DELAY_MS - 1);
    expect(refetch).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("maps not viewed — only clear", () => {
    const { clear, refetch, rerender } = setup(false);
    rerender({ key: "k2" });
    vi.advanceTimersByTime(MAPS_REFRESH_DELAY_MS * 2);
    expect(clear).toHaveBeenCalledTimes(1);
    expect(refetch).not.toHaveBeenCalled();
  });

  it("unmount cancels a pending refetch", () => {
    const { refetch, rerender, unmount } = setup(true);
    rerender({ key: "k2" });
    unmount();
    vi.advanceTimersByTime(MAPS_REFRESH_DELAY_MS);
    expect(refetch).not.toHaveBeenCalled();
  });
});
