// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { KuzRamCalibrateResponse } from "../../../types";
import { KuzRamDialog, type KuzRamDialogProps } from "./KuzRamDialog";
import { defaultKuzramBlock } from "./kuzramSettings";
import { gabbroVariant } from "./testing/fixtures";

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
  crownsMm: [110, 152, 250],
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
    variants: [],
    selectedIndex: 0,
    onSelect: vi.fn(),
    thresholdPct: 5,
    onFactsChange: vi.fn(),
    onCalibrate: vi.fn(),
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

  it("исходные данные — строкой с листа, включая коронки", () => {
    renderDialog();
    expect(
      screen.getByText(
        /Габбро-диабаз · ЭВЕРСИН Э-100 · уступ 10 м, перебур 1 м · кусок 400 мм · коронки 110, 152, 250 мм · допустимый негабарит 5 %/,
      ),
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

  it("показывает сводку, таблицу и график; выбор строки уходит листу", () => {
    const props = renderDialog({ variants: [gabbroVariant(110), gabbroVariant(152), gabbroVariant(250)], selectedIndex: 1 });
    expect(screen.getByRole("region", { name: "Коронка 152 мм" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Удельный расход q по диаметрам коронок/ })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Разбор расчёта" })).toBeInTheDocument();
    // Таблиц в окне несколько (разбор, факты) — берём таблицу вариантов по её карточке.
    const table = within(screen.getByRole("region", { name: "Варианты сетки" })).getByRole("table");
    fireEvent.click(within(table).getAllByRole("row")[2]);
    expect(props.onSelect).toHaveBeenCalledWith(0);
  });

  it("фактические взрывы — в окне, правка строк уходит листу", () => {
    const props = renderDialog();
    fireEvent.click(screen.getByRole("button", { name: "Добавить взрыв" }));
    expect(props.onFactsChange).toHaveBeenCalledWith([{ crown_mm: null, q_kg_m3: null, oversize_pct: null }]);
  });

  it("вкладка «Как пользоваться» показывает справку, вкладка «Расчёт» остаётся в DOM скрытой", () => {
    renderDialog();
    expect(screen.getByRole("tab", { name: "Расчёт" })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("tab", { name: "Как пользоваться" }));
    expect(screen.getByRole("tab", { name: "Как пользоваться" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "Как пользоваться" })).toHaveTextContent("Что делает модель");
    // Вкладка «Расчёт» не размонтирована — скрыта атрибутом `hidden`, поэтому
    // в обычном запросе по роли её не видно, а по факту она в DOM. (Скрытому
    // элементу testing-library не приписывает доступное имя из
    // `aria-labelledby`, поэтому ищем среди всех панелей по атрибуту.)
    expect(screen.queryByRole("tabpanel", { name: "Расчёт" })).not.toBeInTheDocument();
    const panels = screen.getAllByRole("tabpanel", { hidden: true });
    const calcPanel = panels.find((panel) => panel.hasAttribute("hidden"))!;
    expect(calcPanel).toBeTruthy();
    expect(within(calcPanel).getByLabelText("Поправка C(A)")).toBeInTheDocument();
  });

  it("стрелками переключаются вкладки, фокус уходит на новую", () => {
    renderDialog();
    const calcTab = screen.getByRole("tab", { name: "Расчёт" });
    const helpTab = screen.getByRole("tab", { name: "Как пользоваться" });
    calcTab.focus();
    fireEvent.keyDown(calcTab, { key: "ArrowRight" });
    expect(helpTab).toHaveAttribute("aria-selected", "true");
    expect(helpTab).toHaveFocus();
    fireEvent.keyDown(helpTab, { key: "ArrowLeft" });
    expect(calcTab).toHaveAttribute("aria-selected", "true");
    expect(calcTab).toHaveFocus();
  });

  it("подбор C(A), начатый на «Расчёт», не прерывается переключением на «Как пользоваться» и обратно", async () => {
    let release: (value: KuzRamCalibrateResponse) => void = () => {};
    const onCalibrate = vi.fn(() => new Promise<KuzRamCalibrateResponse>((resolve) => { release = resolve; }));
    const props = renderDialog({
      block: { ...defaultKuzramBlock(), facts: [{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 }] },
      onCalibrate,
    });
    fireEvent.click(screen.getByRole("button", { name: "Подобрать C(A) по факту" }));
    expect(onCalibrate).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("tab", { name: "Как пользоваться" }));
    fireEvent.click(screen.getByRole("tab", { name: "Расчёт" }));
    await act(async () => {
      release({
        rows: [
          { crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8, legacy_oversize_pct: 5.3, model_oversize_pct: 4.29, rock_factor_correction: 1.132, note: null },
        ],
        rock_factor_correction: 1.132,
        used: 1,
        skipped: 0,
        model_version: "kuzram-cunningham-1.0",
      });
    });
    expect(props.onSettingsChange).toHaveBeenCalledWith(expect.objectContaining({ rock_factor_correction: 1.132 }));
    await waitFor(() => expect(screen.getByText(/записана в настройки/)).toBeInTheDocument());
  });
});
