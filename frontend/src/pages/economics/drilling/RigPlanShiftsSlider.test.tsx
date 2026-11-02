// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RIG_PLAN_SHIFTS_SETTLE_MS, RigPlanShiftsSlider } from "./RigPlanShiftsSlider";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const slider = () => screen.getByRole("slider", { name: "Плановые смены станка в месяц" }) as HTMLInputElement;

describe("RigPlanShiftsSlider", () => {
  it("пустое значение показывает норматив, движение уходит в черновик один раз по отпусканию", () => {
    const onChange = vi.fn();
    render(<RigPlanShiftsSlider value={null} norm={40} onChange={onChange} />);
    expect(slider().value).toBe("40");
    expect(screen.getByText("40 смен")).toBeInTheDocument();
    expect(screen.getByText("норматив 40")).toBeInTheDocument();

    fireEvent.change(slider(), { target: { value: "35" } });
    fireEvent.change(slider(), { target: { value: "30" } });
    fireEvent.change(slider(), { target: { value: "25" } });
    // Пока ползунок держат — черновик не трогаем, но число уже видно.
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText("25 смен")).toBeInTheDocument();

    fireEvent.pointerUp(slider());
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith("25");
  });

  it("шаги клавиатурой уходят после паузы одним значением", () => {
    vi.useFakeTimers();
    const onChange = vi.fn();
    render(<RigPlanShiftsSlider value="40" norm={40} onChange={onChange} />);

    fireEvent.change(slider(), { target: { value: "41" } });
    fireEvent.change(slider(), { target: { value: "42" } });
    act(() => {
      vi.advanceTimersByTime(RIG_PLAN_SHIFTS_SETTLE_MS - 1);
    });
    expect(onChange).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith("42");
  });

  it("сброс возвращает норматив (null), на нормативе кнопка выключена", () => {
    const onChange = vi.fn();
    const { rerender } = render(<RigPlanShiftsSlider value="25" norm={40} onChange={onChange} />);
    expect(slider().value).toBe("25");
    const reset = screen.getByRole("button", { name: "Сбросить к нормативу" });
    expect(reset).toBeEnabled();
    fireEvent.click(reset);
    expect(onChange).toHaveBeenCalledWith(null);

    rerender(<RigPlanShiftsSlider value="40" norm={40} onChange={onChange} />);
    expect(screen.getByRole("button", { name: "Сбросить к нормативу" })).toBeDisabled();
  });

  it("без норматива кнопки сброса нет, значение вне диапазона показывается числом", () => {
    render(<RigPlanShiftsSlider value="80" norm={null} onChange={vi.fn()} rubPerM="260.5" />);
    expect(screen.queryByRole("button", { name: "Сбросить к нормативу" })).toBeNull();
    expect(screen.getByText("норматив не задан")).toBeInTheDocument();
    expect(screen.getByText("80 смен")).toBeInTheDocument();
    expect(slider().value).toBe("60");
    expect(screen.getByText("260,50 ₽/м")).toBeInTheDocument();
  });

  it("без права правки бегунок и сброс выключены", () => {
    render(<RigPlanShiftsSlider value="25" norm={40} onChange={vi.fn()} disabled />);
    expect(slider()).toBeDisabled();
    expect(screen.getByRole("button", { name: "Сбросить к нормативу" })).toBeDisabled();
  });
});
