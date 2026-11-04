// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { DrillingPriceDonut, donutSlices } from "./DrillingPriceDonut";

afterEach(cleanup);

const components = [
  { code: "DRILL_FUEL", label: "ДТ", rub_per_m: 100 },
  {
    code: "SERVICES",
    label: "Услуги сторонних организаций",
    rub_per_m: 40,
    parts: [
      { code: "DRILL_INSPECTION", label: "Выпуск на линию и медосмотр экипажа станка", rub_per_m: 10 },
      { code: "RULE_TRAWL", label: "Услуги трала", rub_per_m: 30 },
    ],
  },
  { code: "CREW_PAYROLL", label: "ФОТ экипажа", rub_per_m: 40 },
  {
    code: "SITE_STAFF",
    label: "ФОТ ИТР и ремонтного персонала",
    rub_per_m: 20,
    parts: [
      { code: "UNIT_MECH", label: "Механик", rub_per_m: 12 },
      { code: "UNIT_FITTER", label: "Слесарь", rub_per_m: 8 },
    ],
  },
];

describe("DrillingPriceDonut", () => {
  it("группы услуг и персонала участка: подстроки с долей от цены метра и своими оттенками", () => {
    render(<DrillingPriceDonut components={components} />);
    const donut = screen.getByRole("figure", { name: "Слагаемые стоимости метра" });

    // 4 группы + 2 услуги + 2 должности участка.
    expect(within(donut).getAllByRole("listitem")).toHaveLength(8);
    expect(within(donut).getByText("Услуги трала")).toBeInTheDocument();
    // Трал 30 из 200 — 15 % цены метра.
    expect(within(donut).getByText("15 %")).toBeInTheDocument();
    expect(within(donut).getByText("Механик")).toBeInTheDocument();
    expect(within(donut).getByText("200")).toBeInTheDocument();
  });

  it("сегменты подстатей лежат во внешнем кольце напротив своей группы, цвета групп различны", () => {
    const slices = donutSlices(components);
    const services = slices.find((slice) => slice.code === "SERVICES")!;
    const staff = slices.find((slice) => slice.code === "SITE_STAFF")!;
    expect(services.partSlices.map((part) => part.share)).toEqual([0.05, 0.15]);
    expect(services.color).not.toBe(staff.color);
    expect(services.partSlices[0].color).not.toBe(staff.partSlices[0].color);
    // У ФОТ экипажа без подстрок внешнего кольца нет.
    expect(slices.find((slice) => slice.code === "CREW_PAYROLL")!.partSlices).toEqual([]);
  });
});
