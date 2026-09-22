// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ruNumber } from "../../../lib/format";
import { KuzRamHelp } from "./KuzRamHelp";
import examples from "./helpExamples.json";
import { gridText, trimmed } from "./kuzramFormat";

afterEach(cleanup);

describe("KuzRamHelp", () => {
  it("разделы справки", () => {
    render(<KuzRamHelp />);
    for (const title of ["Что делает модель", "Порядок работы", "Настройки", "Как читать результаты", "Примеры"]) {
      expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    }
    expect(screen.getByText("Формулы и источники")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /20 years on/ })).toHaveAttribute("href", expect.stringContaining("smctesting.com"));
  });

  it("цифры примеров — из helpExamples.json", () => {
    render(<KuzRamHelp />);
    const basic = screen.getByRole("region", { name: "Базовый расчёт" });
    expect(basic).toHaveTextContent(`q ${ruNumber(examples.basic.kuzram.q_kg_m3, 2)} кг/м³`);
    expect(basic).toHaveTextContent("q 1,26 кг/м³, сетка 4,42 × 3,54 м");
    expect(basic).toHaveTextContent("−6 %");

    const calibration = screen.getByRole("region", { name: "Подбор C(A) по фактическим взрывам" });
    expect(calibration).toHaveTextContent("условные");
    expect(calibration).toHaveTextContent(`C(A) = ${trimmed(examples.calibration.rock_factor_correction)}`);
    expect(calibration).toHaveTextContent(`${gridText(examples.basic.kuzram.grid_a_m, examples.basic.kuzram.grid_b_m)} → 4,12 × 3,30 м`);

    const methods = screen.getByRole("region", { name: "Выбор способа расчёта A" });
    expect(methods).toHaveTextContent("По трещиноватости (JF)");
    expect(methods).toHaveTextContent("1,98");

    const notReached = screen.getByRole("region", { name: "Порог не достигнут" });
    expect(notReached).toHaveTextContent("негабарит 5,40 %");
    expect(notReached).toHaveTextContent("q 1,53 и негабарит 4,93 %");

    const jointSwitch = screen.getByRole("region", { name: "Скачок при способе JF" });
    expect(jointSwitch).toHaveTextContent("11,48 %");
    expect(jointSwitch).toHaveTextContent("4,00 %");
    expect(jointSwitch).toHaveTextContent("JPS падает до 50");
  });
});
