// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { COMPONENT_COLORS, DrillingPriceDonut, donutSlices } from "./DrillingPriceDonut";

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
    // Взносы и резерв отпусков — своя группа своего цвета, не серый по умолчанию.
    const charges = donutSlices([
      ...components,
      { code: "PAYROLL_CHARGES", label: "Страховые взносы и резерв отпусков", rub_per_m: 30 },
    ]).find((slice) => slice.code === "PAYROLL_CHARGES")!;
    expect(charges.color).toBe(COMPONENT_COLORS.PAYROLL_CHARGES);
    expect(new Set(Object.values(COMPONENT_COLORS)).size).toBe(Object.keys(COMPONENT_COLORS).length);
    // У ФОТ экипажа без подстрок внешнего кольца нет.
    expect(slices.find((slice) => slice.code === "CREW_PAYROLL")!.partSlices).toEqual([]);
  });

  it("должность ФОТ раскладывается на статьи третьим уровнем легенды, у строк — сумма на блок", () => {
    render(
      <DrillingPriceDonut
        components={[
          { code: "DRILL_FUEL", label: "ДТ", rub_per_m: 60, rub: 60000 },
          {
            code: "CREW_PAYROLL",
            label: "ФОТ экипажа",
            rub_per_m: 40,
            rub: 40000,
            parts: [
              {
                code: "LABOR_P_DRILLER#0",
                label: "Машинист буровой установки",
                rub_per_m: 40,
                rub: 40000,
                note: "1 в смене · 3 в штате · 17,39 смены блока",
                parts: [
                  { code: "LABOR_P_DRILLER#0:SALARY", label: "Оклад", rub_per_m: 25, rub: 25000, note: "60 000 ₽/мес на человека" },
                  { code: "LABOR_P_DRILLER#0:CONTRIBUTIONS", label: "Отчисления", rub_per_m: 15, rub: 15000 },
                ],
              },
            ],
          },
        ]}
      />,
    );
    const donut = screen.getByRole("figure", { name: "Слагаемые стоимости метра" });
    const salary = within(donut).getByText("Оклад").closest("li")!;
    expect(salary).toHaveClass("price-donut-subpart");
    // Оклад 25 из 100 ₽/м — 25 %, 25 000 ₽ на блок.
    expect(within(salary).getByText("25 %")).toBeInTheDocument();
    expect(within(salary).getByText(/25\s000/)).toBeInTheDocument();
    const driller = within(donut).getByText("Машинист буровой установки").closest("li")!;
    expect(within(driller).getByText(/40\s000/)).toBeInTheDocument();
    expect(within(donut).getByText("₽ на блок")).toBeInTheDocument();
    // За кого посчитан ФОТ: люди в смене и штат, оклад одного человека.
    expect(within(driller).getByText("1 в смене · 3 в штате · 17,39 смены блока")).toBeInTheDocument();
    expect(within(salary).getByText("60 000 ₽/мес на человека")).toBeInTheDocument();
  });
});
