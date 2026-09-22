// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { KuzRamCalibrateResponse } from "../../../types";
import { KuzRamFacts } from "./KuzRamFacts";
import { MAX_FACTS, type KuzRamFact } from "./kuzramSettings";

afterEach(cleanup);

function renderFacts(initial: KuzRamFact[], onCalibrate = vi.fn()) {
  const onApplyCorrection = vi.fn();
  const changes: KuzRamFact[][] = [];
  function Harness() {
    const [facts, setFacts] = useState(initial);
    return (
      <KuzRamFacts
        facts={facts}
        onChange={(next) => {
          changes.push(next);
          setFacts(next);
        }}
        defaultCrownMm={152}
        onCalibrate={onCalibrate}
        onApplyCorrection={onApplyCorrection}
      />
    );
  }
  render(<Harness />);
  return { onCalibrate, onApplyCorrection, changes };
}

const calibrateButton = () => screen.getByRole("button", { name: "Подобрать C(A) по факту" });

function response(overrides: Partial<KuzRamCalibrateResponse>): KuzRamCalibrateResponse {
  return { rows: [], rock_factor_correction: null, used: 0, skipped: 0, model_version: "kuzram-cunningham-1.0", ...overrides };
}

describe("KuzRamFacts", () => {
  it("«Добавить взрыв» — пустая строка с выбранной коронкой; без полных строк подбор выключен", () => {
    const { changes } = renderFacts([]);
    expect(screen.getByText("Фактических взрывов пока нет.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Добавить взрыв" }));
    expect(changes.at(-1)).toEqual([{ crown_mm: 152, q_kg_m3: null, oversize_pct: null }]);
    expect(screen.getByLabelText("Коронка, строка 1")).toHaveValue("152");
    expect(calibrateButton()).toBeDisabled();
  });

  it("неверное значение подсвечивается, строка в подбор не идёт", () => {
    renderFacts([{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: null }]);
    const oversize = screen.getByLabelText("Фактический негабарит, строка 1");
    fireEvent.change(oversize, { target: { value: "120" } });
    expect(oversize).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Фактический негабарит — больше 0 и меньше 100 %.")).toBeInTheDocument();
    expect(calibrateButton()).toBeDisabled();
    fireEvent.change(oversize, { target: { value: "8,0" } });
    expect(oversize).not.toHaveAttribute("aria-invalid");
    expect(calibrateButton()).toBeEnabled();
  });

  it("удаление строки сдвигает следующие", () => {
    renderFacts([
      { crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 },
      { crown_mm: 165, q_kg_m3: 1.35, oversize_pct: 7.5 },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Удалить взрыв 1" }));
    expect(screen.getByLabelText("Коронка, строка 1")).toHaveValue("165");
    expect(screen.queryByLabelText("Коронка, строка 2")).not.toBeInTheDocument();
  });

  it("удаление строки не переносит непринятый черновик соседней ячейки (ключ строки — не место в массиве)", () => {
    renderFacts([
      { crown_mm: 152, q_kg_m3: null, oversize_pct: 8 },
      { crown_mm: 165, q_kg_m3: null, oversize_pct: 7.5 },
    ]);
    fireEvent.change(screen.getByLabelText("Фактический q, строка 1"), { target: { value: "1ю3" } });
    fireEvent.click(screen.getByRole("button", { name: "Удалить взрыв 1" }));
    expect(screen.getByLabelText("Фактический q, строка 1")).toHaveValue("");
    expect(screen.queryByText("Введите число.")).not.toBeInTheDocument();
  });

  it("подбор C(A): только полные строки, C(A) записывается, по строкам видны прогнозы", async () => {
    const onCalibrate = vi.fn().mockResolvedValue(
      response({
        rows: [
          { crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8, legacy_oversize_pct: 5.3, model_oversize_pct: 4.29, rock_factor_correction: 1.132, note: null },
          { crown_mm: 130, q_kg_m3: 1.2, oversize_pct: 60, legacy_oversize_pct: 5.45, model_oversize_pct: 4.72, rock_factor_correction: null, note: "Фактический негабарит не получается ни при каком C(A) от 0,1 до 10." },
        ],
        rock_factor_correction: 1.132,
        used: 1,
        skipped: 1,
      }),
    );
    const { onApplyCorrection } = renderFacts(
      [
        { crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 },
        { crown_mm: 165, q_kg_m3: null, oversize_pct: 7 },
        { crown_mm: 130, q_kg_m3: 1.2, oversize_pct: 60 },
      ],
      onCalibrate,
    );
    fireEvent.click(calibrateButton());
    await waitFor(() => expect(onApplyCorrection).toHaveBeenCalledWith(1.132));
    expect(onCalibrate).toHaveBeenCalledWith([
      { crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 },
      { crown_mm: 130, q_kg_m3: 1.2, oversize_pct: 60 },
    ]);
    expect(screen.getByRole("status")).toHaveTextContent(
      "C(A) = 1,132 записана в настройки — посчитано по строкам: 1 из 2. Пропущено строк: 1 — для них нет C(A) от 0,1 до 10. Неполные или неверные строки не учитывались: 1.",
    );
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("5,304,291,132");
    expect(rows[1]).toHaveTextContent("———");
    expect(within(rows[2]).getByText("нет")).toHaveAttribute("title", expect.stringContaining("ни при каком C(A)"));
  });

  it("ни одна строка не решилась — C(A) не меняется", async () => {
    const onCalibrate = vi.fn().mockResolvedValue(response({ rock_factor_correction: null, used: 0, skipped: 1, rows: [
      { crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 90, legacy_oversize_pct: 5.3, model_oversize_pct: 4.29, rock_factor_correction: null, note: "вне 0,1–10" },
    ] }));
    const { onApplyCorrection } = renderFacts([{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 90 }], onCalibrate);
    fireEvent.click(calibrateButton());
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("поправка не изменена"));
    expect(onApplyCorrection).not.toHaveBeenCalled();
  });

  it("ошибка сервера видна, правка строки сбрасывает прошлый результат", async () => {
    const onCalibrate = vi.fn().mockRejectedValueOnce(new Error("Фактор породы A = −0,5 — он должен быть больше нуля."));
    renderFacts([{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 }], onCalibrate);
    fireEvent.click(calibrateButton());
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Фактор породы A = −0,5"));
    fireEvent.change(screen.getByLabelText("Фактический q, строка 1"), { target: { value: "1,4" } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("правка строки во время подбора отменяет применение уже летевшего ответа", async () => {
    let release: (value: KuzRamCalibrateResponse) => void = () => {};
    const onCalibrate = vi.fn(() => new Promise<KuzRamCalibrateResponse>((resolve) => { release = resolve; }));
    const { onApplyCorrection } = renderFacts([{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 }], onCalibrate);
    fireEvent.click(calibrateButton());
    await waitFor(() => expect(onCalibrate).toHaveBeenCalledTimes(1));
    // Правка строки, пока подбор летит, — ответ, когда он придёт, уже не про эти строки.
    fireEvent.change(screen.getByLabelText("Фактический q, строка 1"), { target: { value: "1,4" } });
    await act(async () =>
      release(
        response({
          rows: [
            { crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8, legacy_oversize_pct: 5.3, model_oversize_pct: 4.29, rock_factor_correction: 1.132, note: null },
          ],
          rock_factor_correction: 1.132,
          used: 1,
          skipped: 0,
        }),
      ),
    );
    expect(onApplyCorrection).not.toHaveBeenCalled();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("на MAX_FACTS строках «Добавить взрыв» выключена и показан текст «Не больше 50 строк.»", () => {
    const facts = Array.from({ length: MAX_FACTS }, () => ({ crown_mm: 152, q_kg_m3: null, oversize_pct: null }));
    renderFacts(facts);
    expect(screen.getByRole("button", { name: "Добавить взрыв" })).toBeDisabled();
    expect(screen.getByText(`Не больше ${MAX_FACTS} строк.`)).toBeInTheDocument();
  });
});
