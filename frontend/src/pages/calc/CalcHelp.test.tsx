// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { CalcHelp } from "./CalcHelp";

afterEach(cleanup);

beforeAll(() => {
  // jsdom не реализует модальный `dialog`.
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false;
  });
});

describe("CalcHelp", () => {
  it("кнопка «Справка» открывает диалог с назначением листа", () => {
    render(<CalcHelp />);
    const dialog = screen.getByRole("dialog", { hidden: true });
    expect(dialog).not.toHaveAttribute("open");
    fireEvent.click(screen.getByRole("button", { name: "Справка" }));
    expect(dialog).toHaveAttribute("open");
    expect(dialog).toHaveAccessibleName("Подбор параметров БВР");
  });

  it("объясняет кнопку «Экономика», убранную из подсказки паспорта", () => {
    render(<CalcHelp />);
    expect(screen.getByText(/чтобы передать текущий\s+расчёт, сначала сохраните новый/)).toBeInTheDocument();
  });
});
