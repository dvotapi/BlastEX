import { describe, expect, it } from "vitest";
import {
  applyViewPreset,
  contourLayersFromView,
  defaultDesignViewState,
  filterLayers,
  resolveLabelCollisions,
  stageDefaultPreset,
} from "./viewPresets";

describe("viewPresets", () => {
  it("maps workflow stages to sensible defaults", () => {
    expect(stageDefaultPreset("pattern")).toBe("pattern");
    expect(stageDefaultPreset("charge")).toBe("charge");
    expect(stageDefaultPreset("execution")).toBe("actual");
    expect(stageDefaultPreset("report")).toBe("review");
  });

  it("applies preset overrides", () => {
    const review = applyViewPreset("review");
    expect(review.preset).toBe("review");
    expect(review.layers.health).toBe(true);
    expect(review.colorMode).toBe("health");
    expect(review.showHealth).toBe(true);

    const survey = applyViewPreset("survey");
    expect(survey.layers.labels).toBe(false);
    expect(survey.labelField).toBe("none");
  });

  it("derives contour layers for legacy legend", () => {
    const view = applyViewPreset("pattern");
    const contour = contourLayersFromView(view.layers);
    expect(contour.holes).toBe(true);
    expect(contour.face).toBe(true);
    expect(Object.keys(contour)).toEqual(["fill", "crest", "toe", "face", "holes"]);
  });

  it("filters layers by Russian label", () => {
    expect(filterLayers("бров")).toContain("crest");
    expect(filterLayers("бров")).toContain("toe");
    expect(filterLayers("zzz")).toHaveLength(0);
  });

  it("hides overlapping labels", () => {
    const resolved = resolveLabelCollisions([
      { id: "a", x: 10, y: 10, text: "A" },
      { id: "b", x: 12, y: 11, text: "B" },
      { id: "c", x: 40, y: 10, text: "C" },
    ], 14);
    const hidden = resolved.filter((item) => item.hidden).map((item) => item.id);
    expect(hidden).toContain("b");
    expect(resolved.find((item) => item.id === "c")?.hidden).toBeFalsy();
  });

  it("builds default state from stage", () => {
    const state = defaultDesignViewState("timing");
    expect(state.preset).toBe("timing");
    expect(state.layers.isolines).toBe(true);
  });
});
