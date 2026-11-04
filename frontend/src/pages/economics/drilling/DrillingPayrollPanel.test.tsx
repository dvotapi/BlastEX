// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DrillingPayrollBreakdown, DrillingPayrollSource } from "./DrillingPayrollPanel";
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
  render(
    <>
      <DrillingPayrollSource params={params} economics={economics} canEdit={options.canEdit ?? true} onChange={onChange} />
      <DrillingPayrollBreakdown params={params} economics={economics} />
    </>,
  );
  return onChange;
}

describe("DrillingPayrollSource", () => {
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
    view({ executor: "SUBCONTRACTOR", source: "PAYROLL", economics: { ...economicsFixture(), payroll: payrollFixture() } });
    expect(screen.getByRole("radio", { name: "Методика ФОТ" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Методика ФОТ" })).toBeDisabled();
    expect(screen.getByRole("radio", { name: "Ставки" })).toBeDisabled();
    expect(
      screen.getByText("Бурение на субподряде: ФОТ экипажа считает подрядчик. Сохранённый выбор не применяется"),
    ).toBeInTheDocument();
    expect(document.querySelector(".payroll-breakdown")).toBeNull();
  });

  it("ставки: подпись о составе, разбивки нет", () => {
    view({});
    expect(screen.getByText(/ночных, праздничных и межвахты нет/)).toBeInTheDocument();
    expect(document.querySelector(".payroll-breakdown")).toBeNull();
  });

  it("методика применилась: свёрнутая разбивка без второй цены метра, скорость не повторяется", () => {
    view({ source: "PAYROLL", economics: { ...economicsFixture(), payroll: payrollFixture() } });
    expect(screen.getByText(/Оклад, ночные, праздничные, межвахта/)).toBeInTheDocument();
    expect(document.querySelector(".payroll-breakdown")).not.toBeNull();
    expect(document.querySelector(".payroll-summary-price")).toBeNull();
    expect(screen.queryByText("Технологическая скорость")).toBeNull();
  });

  it("методика выбрана, ответ несёт причину — причина показана вместо «Расчёт выполняется…»", () => {
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

  it("устаревший ответ без причины и ответ не пришёл — «Расчёт выполняется…»", () => {
    view({ source: "PAYROLL", economics: { ...economicsFixture(), payroll: null, warnings: ["Другое предупреждение"] } });
    expect(screen.getByText("Расчёт выполняется…")).toBeInTheDocument();
    expect(screen.queryByText(/Методика ФОТ не применена/)).not.toBeInTheDocument();
    cleanup();
    view({ source: "PAYROLL", economics: null });
    expect(screen.getByText("Расчёт выполняется…")).toBeInTheDocument();
  });

  it("имя группы радио уникально у каждого экземпляра", () => {
    view({});
    view({});
    const names = new Set(Array.from(document.querySelectorAll<HTMLInputElement>("input[type=radio]")).map((i) => i.name));
    expect(names.size).toBe(2);
  });
});
