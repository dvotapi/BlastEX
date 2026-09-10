// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CostStructureDonut } from "./CostStructureDonut";
import { buildEstimate } from "../estimateModel";
import { money, percent } from "../format";
import { economicsFixture } from "../testFixtures";

afterEach(cleanup);

/**
 * `money()` разделяет разряды неразрывным пробелом (U+00A0), а нормализатор
 * `@testing-library` при сравнении текста DOM схлопывает пробельные символы
 * в обычные — но не трогает саму строку поиска. Точное текстовое совпадение
 * с суммой в рублях поэтому ищем через регэксп, а не через строку.
 */
function moneyPattern(text: string): RegExp {
  return new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+"));
}

describe("CostStructureDonut", () => {
  it("рисует по сегменту на непустой раздел и зовёт onSelect по клику", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(
      <CostStructureDonut
        groups={buildEstimate(economicsFixture())}
        costPerM3={93.5}
        unit="₽/м³"
        onUnitChange={() => {}}
        highlighted={null}
        onSelect={onSelect}
      />,
    );

    const segments = screen.getAllByRole("button", { name: /Взрывчатые материалы|Бурение|Персонал/ });
    expect(segments.length).toBeGreaterThan(1);

    await user.click(segments[0]);
    expect(onSelect).toHaveBeenCalledWith("EXPLOSIVES");
    expect(screen.getByRole("table", { hidden: true })).toBeInTheDocument();
  });

  it("доли легенды совпадают с итогами разделов", () => {
    const groups = buildEstimate(economicsFixture());
    render(
      <CostStructureDonut
        groups={groups}
        costPerM3={93.5}
        unit="₽/м³"
        onUnitChange={() => {}}
        highlighted={null}
        onSelect={() => {}}
      />,
    );

    // Те же числа продублированы в скрытой таблице для скринридеров —
    // легенда проверяется отдельно от неё через `within`.
    const legend = within(screen.getByRole("list"));
    const explosives = groups.find((group) => group.code === "EXPLOSIVES")!;
    expect(legend.getByText(percent(explosives.share))).toBeInTheDocument();

    const drilling = groups.find((group) => group.code === "DRILLING")!;
    expect(legend.getByText(percent(drilling.share))).toBeInTheDocument();
  });

  it("выделяет сегмент клавиатурой (Enter) и не путает его с чужим кодом", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(
      <CostStructureDonut
        groups={buildEstimate(economicsFixture())}
        costPerM3={93.5}
        unit="₽/м³"
        onUnitChange={() => {}}
        highlighted="DRILLING"
        onSelect={onSelect}
      />,
    );

    const [drillingSegment] = screen.getAllByRole("button", { name: /Бурение/ });
    drillingSegment.focus();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledWith("DRILLING");
  });

  it("переключатель единиц меняет числа легенды с ₽/м³ на ₽", async () => {
    const groups = buildEstimate(economicsFixture());
    const explosives = groups.find((group) => group.code === "EXPLOSIVES")!;
    const onUnitChange = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <CostStructureDonut
        groups={groups}
        costPerM3={93.5}
        unit="₽/м³"
        onUnitChange={onUnitChange}
        highlighted={null}
        onSelect={() => {}}
      />,
    );

    const legend = within(screen.getByRole("list"));
    expect(legend.getByText(moneyPattern(`${money(explosives.perM3 ?? 0)} ₽/м³`))).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "₽" }));
    expect(onUnitChange).toHaveBeenCalledWith("₽");

    rerender(
      <CostStructureDonut
        groups={groups}
        costPerM3={93.5}
        unit="₽"
        onUnitChange={onUnitChange}
        highlighted={null}
        onSelect={() => {}}
      />,
    );
    expect(legend.getByText(moneyPattern(`${money(explosives.total, 0)} ₽`))).toBeInTheDocument();
  });
});
