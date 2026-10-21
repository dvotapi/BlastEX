// @vitest-environment jsdom
// Результат «Рассчитать тайминг» сбрасывается, когда меняется набор скважин,
// их устья в плане, вид или включённость: иначе слой темпа и сводка панели
// «Тайминг» показывают старую сетку. Правки, не трогающие раскладку
// (сеть коммутации, глубина, геология), анализ не сбрасывают.
import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { emptyHoleGeology, type Hole } from "../../types/design";
import { holesLayoutKey, useStaleAnalysisReset } from "./useStaleAnalysis";

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

describe("useStaleAnalysisReset", () => {
  it("resets only when the hole layout changes", () => {
    const reset = vi.fn();
    const first = [hole("1-01"), hole("1-02", { collar: { x: 14, y: 5, z: 420 } })];
    const { rerender } = renderHook(({ holes }) => useStaleAnalysisReset(holes, reset), {
      initialProps: { holes: first },
    });
    expect(reset).not.toHaveBeenCalled();

    // Новый массив с той же раскладкой (сеть, пересчёт глубины) — не сброс.
    rerender({ holes: first.map((h) => ({ ...h, toe: { ...h.toe, z: 400 } })) });
    expect(reset).not.toHaveBeenCalled();

    rerender({ holes: [first[0], { ...first[1], collar: { x: 15, y: 5, z: 420 } }] });
    expect(reset).toHaveBeenCalledTimes(1);

    rerender({ holes: [first[0], { ...first[1], collar: { x: 15, y: 5, z: 420 }, enabled: false }] });
    expect(reset).toHaveBeenCalledTimes(2);
  });
});
