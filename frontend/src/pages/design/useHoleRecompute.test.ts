// @vitest-environment jsdom
// Автопересчёт скважин на странице «Проектирование» (TASK-013, PR 3): запрос
// через 300 мс после изменения кровли, подошвы, перебура или сетки; устаревший
// ответ не применяется; открытие паспорта скважины не меняет.
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { emptyDesign, emptyHoleGeology, type BlastDesign, type Hole, type HoleRecomputeResponse } from "../../types/design";
import { recomputeKey, useHoleRecompute } from "./useHoleRecompute";

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

function design(extra: Partial<BlastDesign> = {}): BlastDesign {
  const base = emptyDesign();
  return {
    ...base,
    design_id: "d-1",
    updated_at: "2026-10-02T10:00:00Z",
    contour: {
      ...base.contour,
      vertices: [
        { x: 0, y: 0, z: 420 },
        { x: 40, y: 0, z: 420 },
        { x: 40, y: 20, z: 420 },
      ],
      bench: { crest_z_m: 420, toe_z_m: 410, face_angle_deg: 90 },
    },
    holes: [hole("a")],
    ...extra,
  };
}

function response(z: number, extra: Partial<HoleRecomputeResponse> = {}): HoleRecomputeResponse {
  return {
    holes: [hole("a", { collar: { x: 10, y: 5, z }, toe: { x: 10, y: 5, z: 409 } })],
    flags: { a: ["outside_surface"] },
    block_volume_m3: 8000,
    drilling_m: z - 409,
    mean_height_m: 10,
    ...extra,
  };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

async function settle() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(350);
  });
}

describe("useHoleRecompute", () => {
  it("открытие паспорта: флаги и объём есть, скважины не меняются", async () => {
    const dispatch = vi.fn();
    const fetcher = vi.fn(async () => response(420.1));
    const { result } = renderHook(() => useHoleRecompute(design(), {}, { apply: true, dispatch, fetcher }));

    await settle();

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(dispatch).not.toHaveBeenCalled();
    expect(result.current.flags).toEqual({ a: ["outside_surface"] });
    expect(result.current.blockVolumeM3).toBe(8000);
    expect(result.current.meanHeightM).toBe(10);
  });

  it("правка подошвы — один запрос через 300 мс и ответ применяется вне истории", async () => {
    const dispatch = vi.fn();
    const fetcher = vi.fn(async (_payload: { contour: BlastDesign["contour"] }) => response(420.1));
    const { rerender } = renderHook(({ value }) => useHoleRecompute(value, {}, { apply: true, dispatch, fetcher }), {
      initialProps: { value: design() },
    });
    await settle();

    const lower = (toe: number) => design({ contour: { ...design().contour, bench: { crest_z_m: 420, toe_z_m: toe, face_angle_deg: 90 } } });
    rerender({ value: lower(409.5) });
    rerender({ value: lower(409) });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(250);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    await settle();

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher.mock.calls[1][0].contour.bench.toe_z_m).toBe(409);
    expect(dispatch).toHaveBeenCalledWith({ type: "RECOMPUTE_HOLES", holes: response(420.1).holes });
  });

  it("устаревший ответ не применяется", async () => {
    const dispatch = vi.fn();
    const resolvers: Array<(value: HoleRecomputeResponse) => void> = [];
    const fetcher = vi.fn(() => new Promise<HoleRecomputeResponse>((resolve) => resolvers.push(resolve)));
    const { result, rerender } = renderHook(({ value }) => useHoleRecompute(value, {}, { apply: true, dispatch, fetcher }), {
      initialProps: { value: design() },
    });
    await settle();
    rerender({ value: design({ holes: [hole("a", { subdrill_m: 1.5 })] }) });
    await settle();
    rerender({ value: design({ holes: [hole("a", { subdrill_m: 2 })] }) });
    await settle();

    await act(async () => {
      resolvers[2](response(422));
      resolvers[1](response(421));
    });

    expect(dispatch).toHaveBeenCalledTimes(1);
    expect(dispatch.mock.calls[0][0].holes[0].collar.z).toBe(422);
    expect(result.current.blockVolumeM3).toBe(8000);
  });

  it("утверждённый паспорт: только флаги и объём, скважины не трогаются", async () => {
    const dispatch = vi.fn();
    const fetcher = vi.fn(async () => response(420.1));
    const { rerender } = renderHook(({ value }) => useHoleRecompute(value, {}, { apply: false, dispatch, fetcher }), {
      initialProps: { value: design() },
    });
    await settle();
    rerender({ value: design({ holes: [hole("a", { subdrill_m: 2 })] }) });
    await settle();

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(dispatch).not.toHaveBeenCalled();
  });

  it("без контура пересчитывать нечего", async () => {
    const fetcher = vi.fn(async () => response(420));
    const base = design();
    const { result } = renderHook(() =>
      useHoleRecompute({ ...base, contour: { ...base.contour, vertices: [] } }, {}, { apply: true, dispatch: vi.fn(), fetcher }),
    );

    await settle();

    expect(fetcher).not.toHaveBeenCalled();
    expect(result.current.blockVolumeM3).toBeNull();
  });
});

describe("recomputeKey", () => {
  const base = design();

  it("не зависит от того, что меняет сам пересчёт: отметки устья и забоя", () => {
    const moved = design({ holes: [hole("a", { collar: { x: 10, y: 5, z: 421 }, toe: { x: 10, y: 5, z: 400 } })] });
    expect(recomputeKey(moved, {})).toBe(recomputeKey(base, {}));
  });

  it("меняется от кровли, подошвы, перебура, сетки, ручной правки и параметров глубины", () => {
    const key = recomputeKey(base, {});
    const roof = { ...base.surfaces, top: { ...emptyDesign().surfaces.top, kind: "top", name: "Кровля", created_at: "t", tin: { vertices: [], triangles: [] } } };
    expect(recomputeKey({ ...base, surfaces: roof as BlastDesign["surfaces"] }, {})).not.toBe(key);
    expect(recomputeKey(design({ contour: { ...base.contour, bench: { ...base.contour.bench, toe_z_m: 409 } } }), {})).not.toBe(key);
    expect(recomputeKey(design({ holes: [hole("a", { subdrill_m: 2 })] }), {})).not.toBe(key);
    expect(recomputeKey(design({ holes: [hole("a", { collar: { x: 11, y: 5, z: 420 }, toe: { x: 11, y: 5, z: 408 } })] }), {})).not.toBe(key);
    expect(recomputeKey(design({ holes: [hole("a", { manual: ["length"] })] }), {})).not.toBe(key);
    expect(recomputeKey(base, { stab_depth_m: 4 })).not.toBe(key);
  });
});

describe("recomputeKey: содержимое поверхностей", () => {
  // Ревью Codex #104: замена поверхности в ту же секунду с тем же числом
  // вершин (правка Z внутри) не меняла ключ — длины оставались по старой.
  function surface(kind: "top" | "floor", z: number) {
    return {
      ...emptyDesign().surfaces.top,
      kind,
      name: "Съёмка",
      created_at: "2026-10-02T12:00:00",
      tin: {
        vertices: [
          { x: 0, y: 0, z: 420 },
          { x: 40, y: 0, z: 420 },
          { x: 20, y: 20, z },
        ],
        triangles: [[0, 1, 2]],
      },
    };
  }

  function withSurfaces(top: number, floor: number): BlastDesign {
    const base = design();
    return { ...base, surfaces: { ...base.surfaces, top: surface("top", top), floor: surface("floor", floor) } as BlastDesign["surfaces"] };
  }

  it("меняется от отметок кровли и подошвы при тех же имени, времени и числе вершин", () => {
    const key = recomputeKey(withSurfaces(421, 410), {});
    expect(recomputeKey(withSurfaces(421.5, 410), {})).not.toBe(key);
    expect(recomputeKey(withSurfaces(421, 409.5), {})).not.toBe(key);
  });

  it("не меняется от копии той же поверхности", () => {
    expect(recomputeKey(withSurfaces(421, 410), {})).toBe(recomputeKey(withSurfaces(421, 410), {}));
  });
});

describe("useHoleRecompute: правки по ревью", () => {
  it("включение и выключение скважины открытого паспорта — только флаги и объём, длины не трогаются", async () => {
    const dispatch = vi.fn();
    const fetcher = vi.fn(async () => response(420.1));
    const { rerender } = renderHook(({ value }) => useHoleRecompute(value, {}, { apply: true, dispatch, fetcher }), {
      initialProps: { value: design() },
    });
    await settle();

    rerender({ value: design({ holes: [hole("a", { enabled: false })] }) });
    await settle();

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(dispatch).not.toHaveBeenCalled();
  });

  it("пересчёт сменил длины при зарядах — заметка с числом скважин и разницей погонажа", async () => {
    const dispatch = vi.fn();
    const fetcher = vi.fn(async () => response(421));
    const charged = (extra: Partial<BlastDesign>) =>
      design({ loads: [{ hole_id: "a" } as unknown as BlastDesign["loads"][number]], ...extra });
    const { result, rerender } = renderHook(({ value }) => useHoleRecompute(value, {}, { apply: true, dispatch, fetcher }), {
      initialProps: { value: charged({}) },
    });
    await settle();
    expect(result.current.notice).toBe("");

    rerender({ value: charged({ holes: [hole("a", { subdrill_m: 1.5 })] }) });
    await settle();

    expect(result.current.notice).toContain("1 скважина");
    expect(result.current.notice).toContain("+0,0 м");
    expect(result.current.notice).toContain("заряды");
  });

  it("ошибка пересчёта видна, объём сбрасывается", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(response(420.1)).mockRejectedValueOnce(new Error("Нет связи с сервером."));
    const { result, rerender } = renderHook(({ value }) => useHoleRecompute(value, {}, { apply: true, dispatch: vi.fn(), fetcher }), {
      initialProps: { value: design() },
    });
    await settle();
    rerender({ value: design({ holes: [hole("a", { subdrill_m: 2 })] }) });
    await settle();

    expect(result.current.error).toBe("Нет связи с сервером.");
    expect(result.current.blockVolumeM3).toBeNull();
  });
});

describe("useHoleRecompute: повторное ревью", () => {
  const withToe = (toe: number, extra: Partial<BlastDesign> = {}) =>
    design({ contour: { ...design().contour, bench: { crest_z_m: 420, toe_z_m: toe, face_angle_deg: 90 } }, ...extra });

  it("подошва вернулась к значению при открытии — скважины пересчитываются снова", async () => {
    const dispatch = vi.fn();
    const fetcher = vi.fn(async () => response(420.1));
    const { rerender } = renderHook(({ value }) => useHoleRecompute(value, {}, { apply: true, dispatch, fetcher }), {
      initialProps: { value: withToe(410) },
    });
    await settle();
    rerender({ value: withToe(412) });
    await settle();
    rerender({ value: withToe(410) });
    await settle();

    expect(dispatch).toHaveBeenCalledTimes(2);
  });

  it("заметка — только своего паспорта и до пересчёта зарядов", async () => {
    const fetcher = vi.fn(async () => response(421));
    const loads = [{ hole_id: "a" } as unknown as BlastDesign["loads"][number]];
    const { result, rerender } = renderHook(({ value }) => useHoleRecompute(value, {}, { apply: true, dispatch: vi.fn(), fetcher }), {
      initialProps: { value: withToe(410, { loads }) },
    });
    await settle();
    rerender({ value: withToe(409, { loads }) });
    await settle();
    expect(result.current.notice).toContain("заряды");

    // Заряды пересчитали — заметка ушла.
    rerender({ value: withToe(409, { loads: [...loads] }) });
    expect(result.current.notice).toBe("");

    rerender({ value: withToe(408, { loads }) });
    await settle();
    expect(result.current.notice).toContain("заряды");
    // Открыт другой паспорт — заметка прошлого не видна.
    rerender({ value: withToe(408, { loads, design_id: "d-2" }) });
    expect(result.current.notice).toBe("");
  });

  it("ошибка пересчёта — флаги прошлого ответа не показываются", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(response(420.1)).mockRejectedValueOnce(new Error("Нет связи."));
    const { result, rerender } = renderHook(({ value }) => useHoleRecompute(value, {}, { apply: true, dispatch: vi.fn(), fetcher }), {
      initialProps: { value: withToe(410) },
    });
    await settle();
    expect(result.current.flags).toEqual({ a: ["outside_surface"] });
    rerender({ value: withToe(409) });
    await settle();

    expect(result.current.flags).toEqual({});
    expect(result.current.meanHeightM).toBeNull();
  });
});
