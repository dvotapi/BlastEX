// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MetricChips, formatMetric } from "./MetricChips";

afterEach(cleanup);

describe("formatMetric", () => {
  it("округляет до заданного числа знаков", () => {
    expect(formatMetric(0.816, 2)).toBe("0.82");
    expect(formatMetric(1.2, 2)).toBe("1.20");
    expect(formatMetric(412.3, 1)).toBe("412.3");
  });

  it("без расчёта показывает прочерк", () => {
    expect(formatMetric(null, 2)).toBe("—");
  });

  it("ноль — это значение, а не отсутствие расчёта", () => {
    expect(formatMetric(0, 1)).toBe("0.0");
  });
});

describe("MetricChips", () => {
  it("рисует четыре показателя выбранного варианта с единицами", () => {
    const { container } = render(<MetricChips metrics={{ q: 0.6, w: 3.87, x50: 212.44, oversize: 4.96 }} />);
    expect(container.querySelectorAll(".chip")).toHaveLength(4);
    expect(screen.getByText("Удельный q").parentElement).toHaveTextContent("Удельный q0.60кг/м³");
    expect(screen.getByText("ЛНС W").parentElement).toHaveTextContent("ЛНС W3.87м");
    expect(screen.getByText("x50").parentElement).toHaveTextContent("x50212.4мм");
    expect(screen.getByText("Негабарит").parentElement).toHaveTextContent("Негабарит5.0%");
  });
});
