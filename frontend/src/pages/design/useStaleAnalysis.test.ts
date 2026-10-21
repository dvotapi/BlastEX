// @vitest-environment jsdom
// Результат «Рассчитать тайминг» сбрасывается, когда меняется набор скважин,
// их устья в плане, вид или включённость, порода или сетка a × b: иначе слой
// темпа и сводка панели «Тайминг» показывают старую сетку и старые границы.
// Правки, не трогающие эти входы (глубина, геология), анализ не сбрасывают.
import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { emptyHoleGeology, type Hole } from "../../types/design";
import { analysisInputsKey, holesLayoutKey, useStaleAnalysisReset, type AnalysisInputs } from "./useStaleAnalysis";

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
  const inputs: AnalysisInputs = { holes: [hole("1-01")], rockName: "Гранит", spacingAM: 4.41, burdenBM: 3.53 };

  it("changes on rock, spacing and burden", () => {
    const key = analysisInputsKey(inputs);
    expect(analysisInputsKey({ ...inputs })).toBe(key);
    expect(analysisInputsKey({ ...inputs, rockName: "Базальт" })).not.toBe(key);
    expect(analysisInputsKey({ ...inputs, spacingAM: 5 })).not.toBe(key);
    expect(analysisInputsKey({ ...inputs, burdenBM: 4 })).not.toBe(key);
  });
});

describe("useStaleAnalysisReset", () => {
  function inputsOf(holes: Hole[], extra: Partial<AnalysisInputs> = {}): AnalysisInputs {
    return { holes, rockName: "Гранит", spacingAM: 4.41, burdenBM: 3.53, ...extra };
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
});
