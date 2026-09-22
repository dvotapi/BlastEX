// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { KuzRamChart, niceStep } from "./KuzRamChart";
import { gabbroVariant } from "./testing/fixtures";

afterEach(cleanup);

const VARIANTS = [gabbroVariant(110), gabbroVariant(152), gabbroVariant(250)];
const FACTS = [{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 }];

describe("KuzRamChart", () => {
  it("шаг делений оси — круглый", () => {
    expect(niceStep(1.53)).toBe(0.25);
    expect(niceStep(2)).toBe(0.5);
    expect(niceStep(0.74)).toBe(0.1);
  });

  it("две линии, полые точки там, где порог не достигнут, ромбы фактов", () => {
    const { container } = render(<KuzRamChart variants={VARIANTS} facts={FACTS} selectedIndex={1} onSelect={vi.fn()} />);
    expect(screen.getByRole("img", { name: /Удельный расход q по диаметрам коронок/ })).toBeInTheDocument();
    expect(container.querySelectorAll("polyline")).toHaveLength(2);
    expect(container.querySelectorAll("circle.open")).toHaveLength(2);
    expect(container.querySelectorAll(".kuzram-chart-fact")).toHaveLength(1);
    expect(screen.getByText("фактический взрыв")).toBeInTheDocument();
  });

  it("наведение показывает подсказку, щелчок выбирает коронку", () => {
    const onSelect = vi.fn();
    const { container } = render(<KuzRamChart variants={VARIANTS} facts={FACTS} selectedIndex={1} onSelect={onSelect} />);
    const zones = container.querySelectorAll(".kuzram-chart-hit");
    fireEvent.mouseEnter(zones[2]);
    const tip = screen.getByRole("tooltip");
    expect(tip).toHaveTextContent("Коронка 250 мм");
    expect(tip).toHaveTextContent("Kuz-Ram 1,50 кг/м³");
    expect(tip).toHaveTextContent("До исправления 1,50 кг/м³");
    expect(tip).toHaveTextContent("порог не достигнут: Kuz-Ram, до исправления");
    fireEvent.mouseLeave(zones[2]);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    fireEvent.mouseEnter(zones[1]);
    expect(screen.getByRole("tooltip")).toHaveTextContent("Факт 1,30 кг/м³");
    fireEvent.click(zones[0]);
    expect(onSelect).toHaveBeenCalledWith(0);
  });
});
