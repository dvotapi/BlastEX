// @vitest-environment jsdom
// Вкладка «Сетка»: поля наклона рядов у откоса пишут ключи в параметры только
// когда пользователь их задал.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_PATTERN_PARAMS, type PatternParams } from "../../types/design";
import { PatternPanel } from "./PatternPanel";

afterEach(cleanup);

function mount(params: PatternParams = DEFAULT_PATTERN_PARAMS) {
  const onChange = vi.fn();
  render(<PatternPanel params={params} onChange={onChange} onGenerate={() => {}} busy={false} />);
  return onChange;
}

const SCHEME = "Первый ряд у откоса";
const TILT = "Наибольший наклон, ° от вертикали";
const RECT: PatternParams = { ...DEFAULT_PATTERN_PARAMS, pattern: "rectangular" };
const STAGGERED_HINT = /не применяется к шахматной сетке/;

function taperOption(): HTMLOptionElement {
  return screen.getByRole("option", { name: /Плавный переход/ }) as HTMLOptionElement;
}

describe("PatternPanel: первый ряд у откоса", () => {
  it("по умолчанию «Вертикальный», поля скрыты", () => {
    mount();
    expect((screen.getByLabelText(SCHEME) as HTMLSelectElement).value).toBe("vertical");
    expect(screen.queryByLabelText(TILT)).toBeNull();
    expect(screen.queryByLabelText("Рядов перехода")).toBeNull();
  });

  it("«Пара» пишет front_rows_mode: pair и показывает угол без числа рядов", () => {
    const onChange = mount();
    fireEvent.change(screen.getByLabelText(SCHEME), { target: { value: "pair" } });
    expect(onChange).toHaveBeenCalledWith({ front_rows_mode: "pair", front_rows_tilt_count: undefined });
    cleanup();
    mount({ ...DEFAULT_PATTERN_PARAMS, front_rows_mode: "pair" });
    expect(screen.getByLabelText(TILT)).toBeTruthy();
    expect(screen.queryByLabelText("Рядов перехода")).toBeNull();
  });

  it("«Плавный переход» пишет taper и показывает «Рядов перехода»", () => {
    const onChange = mount(RECT);
    fireEvent.change(screen.getByLabelText(SCHEME), { target: { value: "taper" } });
    expect(onChange).toHaveBeenCalledWith({ front_rows_mode: "taper", front_rows_tilt_count: 1 });
    cleanup();
    const onChange2 = mount({ ...RECT, front_rows_mode: "taper", front_rows_tilt_count: 1 });
    fireEvent.change(screen.getByLabelText("Рядов перехода"), { target: { value: "2" } });
    expect(onChange2).toHaveBeenCalledWith({ front_rows_tilt_count: 2 });
  });

  it("старый паспорт только с front_rows_tilt_count показывается как «Плавный переход»", () => {
    mount({ ...RECT, front_rows_tilt_count: 2 });
    expect((screen.getByLabelText(SCHEME) as HTMLSelectElement).value).toBe("taper");
    expect((screen.getByLabelText("Рядов перехода") as HTMLSelectElement).value).toBe("2");
  });

  it("угол по умолчанию 15, ввод 40 пишется как 30", () => {
    const onChange = mount({ ...DEFAULT_PATTERN_PARAMS, front_rows_mode: "pair" });
    const field = screen.getByLabelText(TILT) as HTMLInputElement;
    expect(field.value).toBe("");
    expect(field.placeholder).toBe("15");
    fireEvent.change(field, { target: { value: "40" } });
    expect(onChange).toHaveBeenCalledWith({ front_rows_tilt_deg: 30 });
  });

  it("пустой наклон убирает ключ, а не пишет 0", () => {
    const onChange = mount({ ...DEFAULT_PATTERN_PARAMS, front_rows_mode: "pair", front_rows_tilt_deg: 20 });
    fireEvent.change(screen.getByLabelText(TILT), { target: { value: "" } });
    const [patch] = onChange.mock.calls[0];
    expect("front_rows_tilt_deg" in patch).toBe(true);
    expect(patch.front_rows_tilt_deg).toBeUndefined();
  });

  it("«Вертикальный» убирает ключи схемы и отступа", () => {
    const onChange = mount({ ...DEFAULT_PATTERN_PARAMS, front_rows_mode: "taper", front_rows_tilt_count: 2, front_rows_tilt_deg: 20, min_crest_offset_m: 2 });
    fireEvent.change(screen.getByLabelText(SCHEME), { target: { value: "vertical" } });
    const [patch] = onChange.mock.calls[0];
    expect(Object.keys(patch).sort()).toEqual(["front_rows_mode", "front_rows_tilt_count", "front_rows_tilt_deg", "min_crest_offset_m"]);
    expect(Object.values(patch).every((v) => v === undefined)).toBe(true);
  });

  it("у вертикального первого ряда отступа от кромки нет, если он не задан", () => {
    mount();
    expect(screen.queryByLabelText("Мин. отступ устья от кромки, м")).toBeNull();
    cleanup();
    mount({ ...DEFAULT_PATTERN_PARAMS, min_crest_offset_m: 1.5 });
    expect((screen.getByLabelText("Мин. отступ устья от кромки, м") as HTMLInputElement).value).toBe("1.5");
  });

  it("«Мин. отступ устья от кромки» пишет ключ, умолчание 1 — подсказка", () => {
    const onChange = mount({ ...DEFAULT_PATTERN_PARAMS, front_rows_mode: "pair" });
    const field = screen.getByLabelText("Мин. отступ устья от кромки, м") as HTMLInputElement;
    expect(field.value).toBe("");
    expect(field.placeholder).toBe("1");
    fireEvent.change(field, { target: { value: "1.5" } });
    expect(onChange).toHaveBeenCalledWith({ min_crest_offset_m: 1.5 });
  });

  it("вид «Наклонная у откоса» не предлагается для сетки", () => {
    mount();
    expect(screen.queryByText("Наклонная у откоса")).toBeNull();
  });

  it("у шахматной сетки «Плавный переход» недоступен, у прямоугольной — доступен", () => {
    expect(DEFAULT_PATTERN_PARAMS.pattern).toBe("staggered");
    mount();
    expect(taperOption().disabled).toBe(true);
    expect(taperOption().textContent).toMatch(STAGGERED_HINT);
    expect(screen.queryByRole("note")).toBeNull();
    cleanup();
    mount(RECT);
    expect(taperOption().disabled).toBe(false);
    expect(taperOption().textContent).not.toMatch(STAGGERED_HINT);
  });

  it("сохранённый taper у шахматной сетки — неактивен с подсказкой, параметры не переписываются", () => {
    const onChange = mount({ ...DEFAULT_PATTERN_PARAMS, front_rows_mode: "taper", front_rows_tilt_count: 2 });
    expect((screen.getByLabelText(SCHEME) as HTMLSelectElement).value).toBe("taper");
    expect((screen.getByLabelText("Рядов перехода") as HTMLSelectElement).disabled).toBe(true);
    expect(screen.getByRole("note").textContent).toMatch(STAGGERED_HINT);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("переключение на шахматную при выбранном переходе показывает подсказку", () => {
    const params: PatternParams = { ...RECT, front_rows_mode: "taper", front_rows_tilt_count: 1 };
    const onChange = vi.fn();
    const { rerender } = render(<PatternPanel params={params} onChange={onChange} onGenerate={() => {}} busy={false} />);
    expect(screen.queryByRole("note")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Шахматная/ }));
    expect(onChange).toHaveBeenCalledWith({ pattern: "staggered" });
    rerender(<PatternPanel params={{ ...params, pattern: "staggered" }} onChange={onChange} onGenerate={() => {}} busy={false} />);
    expect(screen.getByRole("note").textContent).toMatch(STAGGERED_HINT);
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});

describe("PatternPanel: шаг b у квадратной сетки", () => {
  it("квадрат — и без вида сетки (старый паспорт): b заблокирован и равен a", () => {
    for (const pattern of ["square", undefined, "непонятный"]) {
      mount({ ...DEFAULT_PATTERN_PARAMS, pattern, spacing_a_m: 4.6, burden_b_m: 3.7 } as unknown as PatternParams);
      const b = screen.getByLabelText("Шаг между рядами b, м") as HTMLInputElement;
      expect(b.disabled).toBe(true);
      expect(b.value).toBe("4.6");
      cleanup();
    }
    mount({ ...RECT, spacing_a_m: 4.6, burden_b_m: 3.7 });
    const b = screen.getByLabelText("Шаг между рядами b, м") as HTMLInputElement;
    expect(b.disabled).toBe(false);
    expect(b.value).toBe("3.7");
  });
});
