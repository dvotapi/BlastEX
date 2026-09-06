import { describe, expect, it } from "vitest";
import { formatMetric } from "./CalcTopStrip";

describe("formatMetric", () => {
  it("округляет до заданного числа знаков", () => {
    expect(formatMetric(0.816, 2)).toBe("0.82");
    expect(formatMetric(1.2, 2)).toBe("1.20");
    expect(formatMetric(412.3, 1)).toBe("412.3");
  });

  it("без значения возвращает прочерк", () => {
    expect(formatMetric(null, 2)).toBe("—");
  });

  it("ноль — валидное значение, не путается с отсутствием расчёта", () => {
    expect(formatMetric(0, 1)).toBe("0.0");
  });
});
