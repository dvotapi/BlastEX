// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DrillingPayrollPanel } from "./DrillingPayrollPanel";
import { economicsFixture, paramsFixture, payrollFixture } from "../testFixtures";
import type { BlockEconomics } from "../../../types/blockEconomics";

afterEach(cleanup);

function view(options: {
  source?: "RATES" | "PAYROLL";
  executor?: "OWN" | "SUBCONTRACTOR";
  canEdit?: boolean;
  economics?: BlockEconomics | null;
  onChange?: () => void;
}) {
  const economics = options.economics === undefined ? economicsFixture() : options.economics;
  const params = {
    ...paramsFixture(),
    payroll_source: options.source ?? "RATES",
    drilling_executor: options.executor ?? "OWN",
  };
  const onChange = options.onChange ?? vi.fn();
  render(<DrillingPayrollPanel params={params} economics={economics} canEdit={options.canEdit ?? true} onChange={onChange} />);
  return onChange;
}

describe("DrillingPayrollPanel", () => {
  it("выбор «Методика ФОТ» передаёт payroll_source", async () => {
    const onChange = vi.fn();
    view({ onChange });
    await userEvent.setup().click(screen.getByRole("radio", { name: "Методика ФОТ" }));
    expect(onChange).toHaveBeenCalledWith({ payroll_source: "PAYROLL" });
    expect(screen.getByRole("radio", { name: "Ставки" })).toBeChecked();
  });

  it("без права правки переключатель недоступен", () => {
    view({ canEdit: false });
    expect(screen.getByRole("radio", { name: "Ставки" })).toBeDisabled();
    expect(screen.getByRole("radio", { name: "Методика ФОТ" })).toBeDisabled();
  });

  it("при субподряде обе кнопки недоступны, сохранённый выбор остаётся, есть подсказка", () => {
    view({ executor: "SUBCONTRACTOR", source: "PAYROLL" });
    expect(screen.getByRole("radio", { name: "Методика ФОТ" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Методика ФОТ" })).toBeDisabled();
    expect(screen.getByRole("radio", { name: "Ставки" })).toBeDisabled();
    expect(
      screen.getByText("Бурение на субподряде: ФОТ экипажа считает подрядчик. Сохранённый выбор не применяется"),
    ).toBeInTheDocument();
  });

  it("в режиме ставок разбивки, скорости и подсказки субподряда нет", () => {
    view({});
    expect(document.querySelector(".payroll-breakdown")).toBeNull();
    expect(screen.queryByText(/Технологическая скорость/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Бурение на субподряде/)).not.toBeInTheDocument();
  });

  it("методика: разбивка показана, скорость и её источник — только чтение", () => {
    const economics = economicsFixture();
    view({
      source: "PAYROLL",
      economics: {
        ...economics,
        payroll: payrollFixture(),
        natural: {
          ...economics.natural,
          values: { ...economics.natural.values, drilling_tech_speed_m_per_h: "15.5", v_commercial_m_per_shift: "155" },
        },
      },
    });
    expect(document.querySelector(".payroll-breakdown")).not.toBeNull();
    expect(screen.getByText("Технологическая скорость").nextElementSibling).toHaveTextContent("15,5 м/ч");
    expect(screen.getByText("Коммерческая скорость").nextElementSibling).toHaveTextContent("155 м/смену");
    // Название строки матрицы, а не служебный код записи.
    expect(screen.getByText("Откуда скорость").nextElementSibling).toHaveTextContent("Гранит, коронка 160");
    expect(document.body.textContent).not.toMatch(/drilling_conditions\./);
    expect(screen.queryByRole("spinbutton")).toBeNull();
  });

  it("методика не применилась — скорости и подсказки про матрицу нет", () => {
    view({ source: "PAYROLL", economics: { ...economicsFixture(), payroll: null, warnings: ["Методика ФОТ не применена: нет экипажа бурения."] } });
    expect(screen.queryByText("Технологическая скорость")).not.toBeInTheDocument();
    expect(screen.queryByText(/здесь не правятся/)).not.toBeInTheDocument();
  });

  it("методика выбрана, ответ несёт причину — причина показана", () => {
    const economics = economicsFixture();
    for (const warning of [
      "Методика ФОТ не применена: нет норм бурения.",
      "ФОТ экипажа бурения посчитан по ставкам, а не по методике: ошибка",
    ]) {
      view({ source: "PAYROLL", economics: { ...economics, payroll: null, warnings: [warning] } });
      expect(screen.getByText(warning)).toBeInTheDocument();
      expect(screen.queryByText("Расчёт выполняется…")).not.toBeInTheDocument();
      cleanup();
    }
  });

  it("устаревший ответ без причины, расчёт не пришёл и субподряд — причины нет", () => {
    const economics = economicsFixture();
    view({ source: "PAYROLL", economics: { ...economics, payroll: null, warnings: ["Другое предупреждение"] } });
    expect(screen.queryByText(/Методика ФОТ не применена/)).not.toBeInTheDocument();
    cleanup();
    view({ source: "PAYROLL", economics: null });
    expect(screen.getByText("Расчёт выполняется…")).toBeInTheDocument();
    cleanup();
    view({
      source: "PAYROLL",
      executor: "SUBCONTRACTOR",
      economics: { ...economics, payroll: null, warnings: ["Методика ФОТ не применена: нет норм бурения."] },
    });
    expect(screen.queryByText(/Методика ФОТ не применена/)).not.toBeInTheDocument();
  });

  it("имя группы радио уникально у каждого экземпляра панели", () => {
    view({});
    view({});
    const names = new Set(Array.from(document.querySelectorAll<HTMLInputElement>("input[type=radio]")).map((i) => i.name));
    expect(names.size).toBe(2);
  });
});
