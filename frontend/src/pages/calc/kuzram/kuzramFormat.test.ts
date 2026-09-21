import { describe, expect, it } from "vitest";
import { formatOversize, formatQ, gridText, LEGACY_Q_MIN_KG_M3, qDeltaText, trimmed } from "./kuzramFormat";

describe("kuzramFormat", () => {
  it("trimmed — запятая, без лишних нулей и разделителя тысяч", () => {
    expect(trimmed(1.127)).toBe("1,127");
    expect(trimmed(2)).toBe("2");
    expect(trimmed(0.5)).toBe("0,5");
    expect(trimmed(1.12345, 6)).toBe("1,12345");
    expect(trimmed(1000)).toBe("1000");
  });

  it("q на нижней границе перебора — «≤»", () => {
    expect(formatQ(1.26)).toBe("1,26");
    expect(formatQ(0.1)).toBe("≤ 0,10");
    expect(formatQ(0.1, ".")).toBe("≤ 0.10");
    expect(formatQ(0.3, ",", LEGACY_Q_MIN_KG_M3)).toBe("≤ 0,30");
    expect(formatQ(0.31, ",", LEGACY_Q_MIN_KG_M3)).toBe("0,31");
  });

  it("негабарит «> порога», когда порог не достигнут, а округление дало порог", () => {
    expect(formatOversize(4.98, true, 5)).toBe("4,98");
    expect(formatOversize(5.4, false, 5)).toBe("5,40");
    expect(formatOversize(5, false, 5)).toBe("> 5");
    expect(formatOversize(5.04, false, 5, 1, ".")).toBe("> 5");
    expect(formatOversize(5.04, false, 5, 2, ".")).toBe("5.04");
  });

  it("разница q в целых процентах со знаком", () => {
    expect(qDeltaText(1.26, 1.34)).toBe("−6 %");
    expect(qDeltaText(1.45, 1.34)).toBe("+8 %");
    expect(qDeltaText(1.34, 1.34)).toBe("0 %");
  });

  it("сетка a × b", () => {
    expect(gridText(4.42, 3.54)).toBe("4,42 × 3,54");
    expect(gridText(3.3, 4)).toBe("3,30 × 4,00");
  });
});
