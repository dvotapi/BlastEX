// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { KuzRamSettings } from "../../../types";
import { KuzRamSettingsForm } from "./KuzRamSettingsForm";
import { KUZRAM_DEFAULTS } from "./kuzramSettings";

afterEach(cleanup);

/** Форма с настоящим состоянием: как в окне, правка сразу возвращается в поля. */
function renderForm(initial: KuzRamSettings = KUZRAM_DEFAULTS) {
  const onChange = vi.fn();
  function Harness() {
    const [settings, setSettings] = useState(initial);
    return (
      <KuzRamSettingsForm
        settings={settings}
        onChange={(next) => {
          onChange(next);
          setSettings(next);
        }}
      />
    );
  }
  render(<Harness />);
  return onChange;
}

describe("KuzRamSettingsForm", () => {
  it("JCF и JPA — только при способе JF, A вручную — только при ручном вводе", () => {
    renderForm();
    expect(screen.queryByLabelText("Состояние трещин JCF")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("A вручную")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Фактор породы A"), { target: { value: "joint_factor" } });
    expect(screen.getByLabelText("Состояние трещин JCF")).toHaveDisplayValue("плотные — 1");
    expect(screen.getByLabelText("Ориентация трещин JPA")).toHaveDisplayValue("падение в сторону откоса — 20");
    fireEvent.change(screen.getByLabelText("Фактор породы A"), { target: { value: "manual" } });
    expect(screen.queryByLabelText("Состояние трещин JCF")).not.toBeInTheDocument();
    expect(screen.getByLabelText("A вручную")).toHaveValue("6");
  });

  it("верное значение сразу уходит в настройки, запятая допустима", () => {
    const onChange = renderForm();
    fireEvent.change(screen.getByLabelText("Поправка C(A)"), { target: { value: "1,15" } });
    expect(onChange).toHaveBeenLastCalledWith({ ...KUZRAM_DEFAULTS, rock_factor_correction: 1.15 });
  });

  it("неверное значение подсвечивается и в расчёт не идёт", () => {
    const onChange = renderForm();
    const input = screen.getByLabelText("Поправка C(A)");
    fireEvent.change(input, { target: { value: "20" } });
    expect(onChange).not.toHaveBeenCalled();
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription(/Поправка C\(A\) — от 0,1 до 10\./);
    fireEvent.change(input, { target: { value: "" } });
    expect(screen.getByText("Введите число.")).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("значение, пришедшее снаружи (подбор C(A)), показывается в поле", () => {
    const { rerender } = render(<KuzRamSettingsForm settings={KUZRAM_DEFAULTS} onChange={() => {}} />);
    rerender(<KuzRamSettingsForm settings={{ ...KUZRAM_DEFAULTS, rock_factor_correction: 1.127 }} onChange={() => {}} />);
    expect(screen.getByLabelText("Поправка C(A)")).toHaveValue("1,127");
  });

  it("«Сбросить к умолчаниям» возвращает умолчания и выключена на них", () => {
    const onChange = renderForm({ ...KUZRAM_DEFAULTS, rock_factor_method: "rmd10", q_max_kg_m3: 3 });
    fireEvent.click(screen.getByRole("button", { name: "Сбросить к умолчаниям" }));
    expect(onChange).toHaveBeenLastCalledWith(KUZRAM_DEFAULTS);
    expect(screen.getByRole("button", { name: "Сбросить к умолчаниям" })).toBeDisabled();
    expect(screen.getByLabelText("Верхняя граница перебора q, кг/м³")).toHaveValue("2");
  });

  it("неверный ввод при настройках по умолчанию включает «Сбросить к умолчаниям», сброс стирает его", () => {
    const onChange = renderForm();
    const reset = () => screen.getByRole("button", { name: "Сбросить к умолчаниям" });
    expect(reset()).toBeDisabled();
    // Мусор в поле в настройки не уходит — сохранённые значения остаются умолчаниями.
    fireEvent.change(screen.getByLabelText("Поправка C(A)"), { target: { value: "abc" } });
    expect(onChange).not.toHaveBeenCalled();
    expect(reset()).toBeEnabled();
    fireEvent.click(reset());
    expect(screen.getByLabelText("Поправка C(A)")).toHaveValue("1");
    expect(screen.getByLabelText("Поправка C(A)")).not.toHaveAttribute("aria-invalid");
    expect(reset()).toBeDisabled();
    // Настройки и так умолчания: сброс стирает только ввод — правки настроек,
    // а с ней и пересчёта листа, нет.
    expect(onChange).not.toHaveBeenCalled();
    // Число вне границ тоже не принято — и тоже включает сброс.
    fireEvent.change(screen.getByLabelText("Поправка C(A)"), { target: { value: "50" } });
    expect(reset()).toBeEnabled();
    // Исправили на верное значение, равное умолчанию, — сбрасывать нечего.
    fireEvent.change(screen.getByLabelText("Поправка C(A)"), { target: { value: "1" } });
    expect(reset()).toBeDisabled();
  });

  it("неверный ввод в поле, которое скрыли сменой способа, сброс не держит", () => {
    renderForm({ ...KUZRAM_DEFAULTS, rock_factor_method: "manual" });
    fireEvent.change(screen.getByLabelText("A вручную"), { target: { value: "abc" } });
    fireEvent.change(screen.getByLabelText("Фактор породы A"), { target: { value: "rmd50" } });
    // Поле «A вручную» скрыто, настройки снова умолчания — кнопка выключена.
    expect(screen.queryByLabelText("A вручную")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Сбросить к умолчаниям" })).toBeDisabled();
  });

  it("«Сбросить к умолчаниям» стирает и неверный ввод в поле, значение которого не менялось", () => {
    renderForm({ ...KUZRAM_DEFAULTS, q_max_kg_m3: 3 });
    // C(A) осталась умолчанием 1, в поле — мусор; сброс не меняет её значение.
    fireEvent.change(screen.getByLabelText("Поправка C(A)"), { target: { value: "abc" } });
    expect(screen.getByLabelText("Поправка C(A)")).toHaveAttribute("aria-invalid", "true");
    fireEvent.click(screen.getByRole("button", { name: "Сбросить к умолчаниям" }));
    expect(screen.getByLabelText("Поправка C(A)")).toHaveValue("1");
    expect(screen.getByLabelText("Поправка C(A)")).not.toHaveAttribute("aria-invalid");
  });
});
