import { describe, expect, it } from "vitest";

import { reconcilingColumns } from "./format";

/** Так число читает сметчик: пробелы тысяч убираем, запятую делаем точкой. */
const num = (text: string) => Number(text.replace(/[\s\u00a0]/g, "").replace(",", "."));

const reconciles = (quantity: number, price: number, amountRub: number) => {
  const shown = reconcilingColumns(quantity, price, amountRub);
  return Math.round(num(shown.quantity) * num(shown.price)) === Math.round(amountRub);
};

describe("норма и цена в колонках сметы", () => {
  it("показывает копейки, когда и так сходится", () => {
    const shown = reconcilingColumns(29554.55, 46, 29554.55 * 46);

    expect(num(shown.quantity)).toBe(29554.55);
    expect(shown.price).toBe("46,00");
  });

  it("добавляет знаки цене, полученной делением", () => {
    // Литр ДТ — из цены за тонну: 44,37 ₽ × 10 890 л расходится с суммой.
    const price = 52200 / 1176.47;

    expect(reconcilingColumns(10890, price, 10890 * price).price).toBe("44,37002");
    expect(reconciles(10890, price, 10890 * price)).toBe(true);
  });

  it("добавляет знаки норме, когда цена ровная", () => {
    // Смены станка на блок: 27,5875 см × 750 ₽; 27,59 дало бы лишний рубль.
    const shown = reconcilingColumns(27.5875, 750, 27.5875 * 750);

    expect(shown.quantity).toBe("27,5875");
    expect(shown.price).toBe("750,00");
    expect(reconciles(27.5875, 750, 27.5875 * 750)).toBe(true);
  });

  it("сходится и там, где сумма округлена до копеек", () => {
    const cases: Array<[number, number]> = [
      [2420, 237966.66666666666 / 2420],
      [3.386875, 6110.5],
      [220, 335.2],
      [0.129, 1 / 3],
    ];

    for (const [quantity, price] of cases) {
      expect(reconciles(quantity, price, Math.round(quantity * price * 100) / 100)).toBe(true);
    }
  });
});
