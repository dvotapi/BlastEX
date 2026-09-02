import { describe, expect, it } from "vitest";
import {
  applyViewPreset,
  defaultDesignViewState,
  layerGroups,
  resetLayersToPreset,
  stageDefaultPreset,
  holeMarkerRadiusPx,
  visibleLabelIds,
} from "./viewPresets";

describe("viewPresets", () => {
  it("applies seven presets with distinct color modes", () => {
    const review = applyViewPreset("review");
    const timing = applyViewPreset("timing");
    expect(review.colorMode).toBe("health");
    expect(timing.colorMode).toBe("delay_ms");
    expect(timing.layers.isolines).toBe(true);
  });

  it("maps workflow stages to default presets", () => {
    expect(stageDefaultPreset("pattern")).toBe("pattern");
    expect(stageDefaultPreset("timing")).toBe("network");
    expect(stageDefaultPreset("execution")).toBe("actual");
  });

  it("resets manual layer overrides back to active preset", () => {
    const state = defaultDesignViewState("charge");
    const overridden = { ...state, layers: { ...state.layers, network: true } };
    const reset = resetLayersToPreset(overridden);
    expect(reset.layers.network).toBe(false);
  });

  it("filters layer search by keyword", () => {
    const groups = layerGroups("азимут");
    const labels = groups.flatMap((g) => g.items.map((i) => i.label));
    expect(labels.some((label) => /подпис/i.test(label))).toBe(true);
  });

  it("keeps higher-priority labels in collision resolution", () => {
    const visible = visibleLabelIds([
      { id: "a", x: 0, y: 0, w: 30, h: 12, priority: 1 },
      { id: "b", x: 5, y: 2, w: 30, h: 12, priority: 50 },
      { id: "c", x: 100, y: 100, w: 20, h: 12, priority: 10 },
    ]);
    expect(visible.has("b")).toBe(true);
    expect(visible.has("a")).toBe(false);
    expect(visible.has("c")).toBe(true);
  });

  it("shrinks hole markers at small scale so a 5 m grid stays separable", () => {
    // 1,9 px/м: соседние скважины в 9,5 px друг от друга — маркер должен быть меньше половины шага.
    expect(holeMarkerRadiusPx(152, 1.9)).toBeLessThan(4.75);
    expect(holeMarkerRadiusPx(152, 1.9)).toBeGreaterThanOrEqual(2.5);
    // На рабочем масштабе — прежние 5 px, выбранная скважина крупнее.
    expect(holeMarkerRadiusPx(152, 6.6)).toBe(5);
    expect(holeMarkerRadiusPx(152, 6.6, true)).toBe(6.5);
    // При сильном приближении маркер растёт вместе с физическим диаметром.
    expect(holeMarkerRadiusPx(152, 200)).toBeCloseTo(15.2, 5);
  });
});
