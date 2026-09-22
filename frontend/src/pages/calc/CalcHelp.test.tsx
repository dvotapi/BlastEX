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

  it("описывает модель Kuz-Ram, кнопку окна и значок «!»", () => {
    render(<CalcHelp />);
    expect(screen.getByText(/Кнопка в заголовке панели «Варианты сетки» открывает окно/)).toBeInTheDocument();
    expect(screen.getByText(/вкладке окна «Как пользоваться»/)).toBeInTheDocument();
    expect(screen.getByText(/значок «!» — порог не\s+достигнут даже на верхней/)).toBeInTheDocument();
  });
});
