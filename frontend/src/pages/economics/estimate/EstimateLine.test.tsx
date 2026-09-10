// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EstimateLine } from "./EstimateLine";

afterEach(cleanup);

/** Обязательный минимум пропсов строки — тесты переопределяют только своё. */
function baseProps() {
  return {
    number: "1.1",
    name: "Гранулит РП",
    origin: "REFERENCE" as const,
    quantity: 100,
    unit: "кг",
    price: 46,
    amount: 4600,
    volume: 30000,
    share: 0.5,
  };
}

describe("EstimateLine", () => {
  it("склеивает пункты раздела и «Формулу» в одно меню строки", async () => {
    const remove = vi.fn();
    render(
      <EstimateLine
        {...baseProps()}
        formula="100 кг × 46 ₽/кг"
        menuLabel="Действия: Основное ВВ"
        menuItems={[{ label: "Убрать", onSelect: remove, danger: true }]}
      />,
    );

    // Одна кнопка «⋯» на строку, а не две рядом.
    expect(screen.getAllByRole("button", { name: /^Действия/ })).toHaveLength(1);

    await userEvent.click(screen.getByRole("button", { name: "Действия: Основное ВВ" }));
    const items = screen.getAllByRole("menuitem").map((item) => item.textContent);
    expect(items).toEqual(["Формула", "Убрать"]);
  });

  it("пункт редактора открывает панель, ставит в неё фокус и закрывается по Escape", async () => {
    const user = userEvent.setup();
    render(
      <EstimateLine
        {...baseProps()}
        menuLabel="Действия: Мастер БВР"
        editorMenuLabel="Смены на блок"
        editor={<input aria-label="Смен на блок: Мастер БВР" />}
      />,
    );

    expect(screen.queryByRole("group", { name: /параметры/ })).not.toBeInTheDocument();

    const trigger = screen.getByRole("button", { name: "Действия: Мастер БВР" });
    await user.click(trigger);
    const item = screen.getByRole("menuitem", { name: "Смены на блок" });
    expect(item).toHaveAttribute("aria-expanded", "false");

    await user.click(item);

    expect(screen.getByRole("group", { name: "Действия: Мастер БВР: параметры" })).toBeInTheDocument();
    expect(screen.getByLabelText("Смен на блок: Мастер БВР")).toHaveFocus();

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("group", { name: /параметры/ })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("подписи под названием идут одной строкой со своими бейджами", () => {
    render(
      <EstimateLine
        {...baseProps()}
        captions={[
          { label: "Смены на блок", value: "18", origin: "CALC", originLabel: "Расчёт", originTitle: "по условиям блока" },
          { label: "Плановые смены в месяц", value: "норматив", origin: "NORM" },
        ]}
      />,
    );

    expect(screen.getByText("Смены на блок: 18")).toBeInTheDocument();
    expect(screen.getByText("Плановые смены в месяц: норматив")).toBeInTheDocument();
    expect(screen.getByTitle("по условиям блока")).toHaveTextContent("Расчёт");
  });

  it("подпись-ссылка уводит туда, где величина учтена", async () => {
    const open = vi.fn();
    render(
      <EstimateLine
        {...baseProps()}
        amount={null}
        share={null}
        captions={[{ label: "Затраты станка", value: "309 095 ₽ — в разделе «Бурение»", onClick: open }]}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /Затраты станка/ }));

    expect(open).toHaveBeenCalledOnce();
  });

  it("ссылочная строка не показывает чужие деньги ни суммой, ни долей", () => {
    render(<EstimateLine {...baseProps()} amount={null} share={null} />);

    const row = screen.getByRole("row");
    expect(row.querySelector(".estimate-col-amount")).toHaveTextContent("—");
    expect(row.querySelector(".estimate-col-perm3")).toHaveTextContent("—");
    expect(row.querySelector(".estimate-col-share")).toHaveTextContent("");
    expect(row).toHaveClass("is-reference");
  });

  it("поле количества встаёт в свою колонку, а цена не пересчитывается под него", () => {
    render(
      <EstimateLine
        {...baseProps()}
        quantity={100}
        price={46}
        amount={4600}
        quantityEditor={<input aria-label="Численность: Мастер БВР" defaultValue="1" />}
      />,
    );

    const row = screen.getByRole("row");
    expect(row.querySelector(".estimate-col-quantity")).toContainElement(
      screen.getByLabelText("Численность: Мастер БВР"),
    );
    expect(row.querySelector(".estimate-col-price")).toHaveTextContent("46,00");
  });

  it("без пунктов и формулы кнопка «⋯» не рисуется", () => {
    render(<EstimateLine {...baseProps()} />);
    expect(screen.queryByRole("button", { name: /^Действия/ })).not.toBeInTheDocument();
  });
});
