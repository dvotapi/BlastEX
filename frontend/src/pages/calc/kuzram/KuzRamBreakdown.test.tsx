// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { KuzRamBreakdown, rockFactorLines, uniformityText } from "./KuzRamBreakdown";
import { gabbroVariant } from "./testing/fixtures";

afterEach(cleanup);

const rowOf = (name: RegExp) => screen.getByRole("rowheader", { name }).closest("tr")!;
/** Ячейки строки разбора: Kuz-Ram и «до исправления» (заголовок строки — не ячейка). */
const cellsOf = (name: RegExp) => within(rowOf(name)).getAllByRole("cell").map((cell) => cell.textContent);

describe("KuzRamBreakdown", () => {
  it("величины обеих моделей для выбранной коронки", () => {
    render(<KuzRamBreakdown variant={gabbroVariant(152)} thresholdPct={5} />);
    expect(screen.getByText("Коронка 152 мм — каждая модель на своём подобранном q.")).toBeInTheDocument();
    expect(cellsOf(/^Удельный расход q/)).toEqual(["1,26", "1,34"]);
    expect(rowOf(/^Фактор породы A/)).toHaveTextContent("0,06·(RMD 50 + RDI 22,5 + HF 33,6)");
    expect(cellsOf(/^Фактор породы A/)).toEqual(["6,37", "2,72"]);
    expect(rowOf(/^Индекс равномерности n/)).toHaveTextContent("→ принято 0,80");
    expect(rowOf(/^W\/d/)).not.toHaveTextContent("выше 35");
    expect(screen.queryByText(/Каннингем рекомендует 25–35/)).not.toBeInTheDocument();
  });

  it("сетка в разборе — та же, что в сводке и таблице: сервер считает a от округлённой W", () => {
    // Коронка 110 мм: a/W · W без округления = 3,3949 → «3,39», а сервер от W = 2,72 даёт a = 3,40.
    render(<KuzRamBreakdown variant={gabbroVariant(110)} thresholdPct={5} />);
    expect(cellsOf(/^ЛНС W · сетка a × b/)).toEqual(["2,72 · 3,40 × 2,72", "2,65 · 3,31 × 2,65"]);
  });

  it("«!» у q «до исправления» советует про фиксированную верхнюю границу прежнего перебора", () => {
    const variant = gabbroVariant(250);
    render(<KuzRamBreakdown variant={variant} thresholdPct={5} />);
    const flags = within(rowOf(/^Удельный расход q/)).getAllByRole("img", { name: "Порог негабарита не достигнут" });
    expect(flags).toHaveLength(2);
    expect(flags[0]).toHaveAttribute("title", expect.stringContaining("Поднимите границу"));
    expect(flags[1]).toHaveAttribute("title", expect.stringContaining("прежнего перебора"));
  });

  it("W/d выше 35 — предупреждение, подбор при этом не ограничен", () => {
    const variant = gabbroVariant(152);
    variant.details.burden_to_diameter = 40.9;
    render(<KuzRamBreakdown variant={variant} thresholdPct={5} />);
    expect(rowOf(/^W\/d/)).toHaveTextContent("выше 35");
    expect(screen.getByText(/W\/d = 40,9 — выше 35: сетка редкая для этого диаметра/)).toBeInTheDocument();
  });

  it("состав A: JF с шагом трещин, массив без трещин, ручной ввод", () => {
    expect(
      rockFactorLines({
        method: "joint_factor", rmd: 100, rdi: 22.5, hf: 33.6, joint_spacing_m: 0.4545, reduced_pattern_m: 3.15,
        jps: 80, base: 9.366, correction: 1.15, value: 10.77,
      }),
    ).toEqual([
      "0,06·(JF 100 + RDI 22,5 + HF 33,6) · C(A) 1,15",
      "JF = JCF·JPS + JPA; JPS 80 при шаге трещин 0,45 м и приведённой сетке P = 3,15 м",
    ]);
    expect(
      rockFactorLines({
        method: "joint_factor", rmd: 50, rdi: 22.5, hf: 33.6, joint_spacing_m: null, reduced_pattern_m: null,
        jps: null, base: 6.366, correction: 1, value: 6.366,
      }),
    ).toEqual(["0,06·(RMD 50 + RDI 22,5 + HF 33,6)", "массив без трещин — RMD 50"]);
    expect(
      rockFactorLines({
        method: "manual", rmd: null, rdi: null, hf: null, joint_spacing_m: null, reduced_pattern_m: null,
        jps: null, base: 6, correction: 1.2, value: 7.2,
      }),
    ).toEqual(["задан вручную: 6 · C(A) 1,2"]);
    expect(rockFactorLines(null)).toEqual([]);
  });

  it("n: сырое → принятое и L/H", () => {
    const variant = gabbroVariant(152);
    expect(uniformityText(variant.details)).toBe("1,78 (L/H 0,88)");
    // Фикстура (crown 152, legacy): uniformity_n_raw = -336.1106.
    expect(uniformityText(variant.legacy.details)).toMatch(/^-336,11 → принято 0,80$/);
  });
});
