// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { KuzRamDialog, type KuzRamDialogProps } from "./KuzRamDialog";
import { defaultKuzramBlock } from "./kuzramSettings";

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

const SOURCE = {
  rockName: "Габбро-диабаз",
  explosiveName: "ЭВЕРСИН Э-100",
  benchHeightM: 10,
  overdrillM: 1,
  lumpSizeMm: 400,
  thresholdPct: 5,
};

function renderDialog(overrides: Partial<KuzRamDialogProps> = {}) {
  const props: KuzRamDialogProps = {
    open: true,
    onClose: vi.fn(),
    block: defaultKuzramBlock(),
    onSettingsChange: vi.fn(),
    source: SOURCE,
    busy: false,
    error: "",
    ...overrides,
  };
  render(<KuzRamDialog {...props} />);
  return props;
}

describe("KuzRamDialog", () => {
  it("открывается модально и закрывается кнопкой", () => {
    const props = renderDialog();
    expect(HTMLDialogElement.prototype.showModal).toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Модель Kuz-Ram" })).toHaveAttribute("open");
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    expect(props.onClose).toHaveBeenCalled();
  });

  it("закрытое окно не рисует содержимое", () => {
    renderDialog({ open: false });
    expect(screen.queryByLabelText("Поправка C(A)")).not.toBeInTheDocument();
  });

  it("исходные данные — строкой с листа", () => {
    renderDialog();
    expect(
      screen.getByText(/Габбро-диабаз · ЭВЕРСИН Э-100 · уступ 10 м, перебур 1 м · кусок 400 мм · допустимый негабарит 5 %/),
    ).toBeInTheDocument();
  });

  it("правка настроек уходит листу", () => {
    const props = renderDialog();
    fireEvent.change(screen.getByLabelText("Поправка C(A)"), { target: { value: "1,2" } });
    expect(props.onSettingsChange).toHaveBeenCalledWith(expect.objectContaining({ rock_factor_correction: 1.2 }));
  });

  it("пока идёт пересчёт — «Пересчёт…», ошибка расчёта видна в окне", () => {
    renderDialog({ busy: true, error: "Фактор породы A = −0,5 — он должен быть больше нуля." });
    const dialog = screen.getByRole("dialog", { name: "Модель Kuz-Ram" });
    expect(within(dialog).getByRole("status")).toHaveTextContent("Пересчёт…");
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Фактор породы A = −0,5");
  });
});
