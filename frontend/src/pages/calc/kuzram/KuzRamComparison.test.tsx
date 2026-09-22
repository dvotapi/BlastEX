// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { KuzRamComparison } from "./KuzRamComparison";
import { gabbroVariant } from "./testing/fixtures";

afterEach(cleanup);

const VARIANTS = [gabbroVariant(110), gabbroVariant(152), gabbroVariant(250)];
const FLAG = { name: "Порог негабарита не достигнут" };

describe("KuzRamComparison", () => {
  it("сводка выбранной коронки: обе модели и разница q", () => {
    render(<KuzRamComparison variants={VARIANTS} selectedIndex={1} onSelect={vi.fn()} thresholdPct={5} />);
    const summary = screen.getByRole("region", { name: "Коронка 152 мм" });
    expect(within(summary).getByText("1,26")).toBeInTheDocument();
    expect(within(summary).getByText("1,34")).toBeInTheDocument();
    expect(summary).toHaveTextContent("сетка 4,42 × 3,54 м · негабарит 4,98 %");
    expect(summary).toHaveTextContent("сетка 4,29 × 3,43 м · негабарит 5,00 %");
    expect(summary).toHaveTextContent("−6 %");
  });

  it("таблица: строка на коронку, «!» у обеих моделей, выбор мышью и клавиатурой", () => {
    const onSelect = vi.fn();
    render(<KuzRamComparison variants={VARIANTS} selectedIndex={1} onSelect={onSelect} thresholdPct={5} />);
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(2);
    expect(rows).toHaveLength(3);
    expect(rows[1]).toHaveAttribute("aria-selected", "true");
    expect(within(rows[2]).getAllByRole("img", FLAG)).toHaveLength(2);
    expect(within(rows[0]).queryByRole("img", FLAG)).not.toBeInTheDocument();
    fireEvent.click(rows[0]);
    expect(onSelect).toHaveBeenLastCalledWith(0);
    fireEvent.keyDown(rows[2], { key: "Enter" });
    expect(onSelect).toHaveBeenLastCalledWith(2);
  });

  it("округлённый негабарит на пороге при недостигнутом пороге — «> 5»", () => {
    render(
      <KuzRamComparison variants={[gabbroVariant(250, { oversize_pct: 5 })]} selectedIndex={0} onSelect={vi.fn()} thresholdPct={5} />,
    );
    const row = within(screen.getByRole("table")).getAllByRole("row")[2];
    expect(row).toHaveTextContent("> 5");
  });

  it("без расчёта — подсказка вместо таблицы", () => {
    render(<KuzRamComparison variants={[]} selectedIndex={0} onSelect={vi.fn()} thresholdPct={5} />);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText(/Нет расчёта/)).toBeInTheDocument();
  });

  it("«!» в строке легенды советует верно: легенда — про верхнюю границу прежнего перебора, Kuz-Ram — про окно настроек", () => {
    render(<KuzRamComparison variants={VARIANTS} selectedIndex={2} onSelect={vi.fn()} thresholdPct={5} />);
    const summary = screen.getByRole("region", { name: "Коронка 250 мм" });
    const flags = within(summary).getAllByRole("img", FLAG);
    expect(flags).toHaveLength(2);
    expect(flags[0]).toHaveAttribute("title", expect.stringContaining("Поднимите границу"));
    expect(flags[1]).toHaveAttribute("title", expect.stringContaining("прежнего перебора"));
  });

  it("под таблицей — коронки с W/d выше 35", () => {
    const wide = gabbroVariant(110);
    wide.details.burden_to_diameter = 40.9;
    render(<KuzRamComparison variants={[wide, gabbroVariant(152)]} selectedIndex={1} onSelect={vi.fn()} thresholdPct={5} />);
    expect(screen.getByText(/W\/d выше 35 у коронок 110 мм/)).toBeInTheDocument();
  });
});
