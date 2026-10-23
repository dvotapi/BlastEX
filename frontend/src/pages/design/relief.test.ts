import { describe, expect, it } from "vitest";

import { formatSpread, reliefBand, reliefLegend } from "./relief";

describe("relief", () => {
  it("puts values within ±10 % of the median into the even band", () => {
    expect(reliefBand(15.33, 15.33)).toBe("even");
    expect(reliefBand(16.8, 15.33)).toBe("even");
    expect(reliefBand(18.0, 15.33)).toBe("slower");
    expect(reliefBand(20.0, 15.33)).toBe("much_slower");
    expect(reliefBand(11.0, 15.33)).toBe("much_faster");
    expect(reliefBand(13.0, 15.33)).toBe("faster");
  });

  it("treats zero median as simultaneous firing", () => {
    expect(reliefBand(0, 0)).toBe("even");
    expect(reliefBand(3, 0)).toBe("much_slower");
  });

  it("labels legend bands in ms/m with a comma", () => {
    expect(reliefLegend(15.33).map((b) => b.label)).toEqual([
      "до 11,5",
      "11,5–13,8",
      "13,8–16,9",
      "16,9–19,2",
      "больше 19,2",
    ]);
  });

  it("formats spread as percent", () => {
    expect(formatSpread(0.0712)).toBe("7 %");
    expect(formatSpread(null)).toBe("—");
  });
});
