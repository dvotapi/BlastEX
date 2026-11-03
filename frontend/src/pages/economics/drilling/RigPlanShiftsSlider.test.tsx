// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RIG_PLAN_SHIFTS_SETTLE_MS, RigPlanShiftsSlider, rigShiftNorm } from "./RigPlanShiftsSlider";
import { defaultsFixture } from "../testFixtures";

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

  it("пока указатель прижат, пауза в движении ничего не отправляет — только отпускание", () => {
    vi.useFakeTimers();
    const onChange = vi.fn();
    render(<RigPlanShiftsSlider value="40" norm={40} onChange={onChange} />);
    fireEvent.pointerDown(slider());
    fireEvent.change(slider(), { target: { value: "35" } });
    act(() => {
      vi.advanceTimersByTime(RIG_PLAN_SHIFTS_SETTLE_MS * 4);
    });
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.change(slider(), { target: { value: "30" } });
    fireEvent.pointerUp(slider());
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith("30");
  });

  it("отпускание клавиши паузу не обрывает: шаг уходит один раз после паузы, а не на каждое нажатие", () => {
    vi.useFakeTimers();
    const onChange = vi.fn();
    render(<RigPlanShiftsSlider value="40" norm={40} onChange={onChange} />);
    fireEvent.change(slider(), { target: { value: "41" } });
    fireEvent.keyUp(slider(), { key: "ArrowRight" });
    fireEvent.change(slider(), { target: { value: "42" } });
    fireEvent.keyUp(slider(), { key: "ArrowRight" });
    expect(onChange).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(RIG_PLAN_SHIFTS_SETTLE_MS);
    });
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith("42");
  });

  it("значение сменилось снаружи до паузы — незавершённый шаг не отправляется", () => {
    vi.useFakeTimers();
    const onChange = vi.fn();
    const { rerender } = render(<RigPlanShiftsSlider value="40" norm={40} onChange={onChange} />);
    fireEvent.change(slider(), { target: { value: "45" } });
    rerender(<RigPlanShiftsSlider value="30" norm={40} onChange={onChange} />);
    act(() => {
      vi.advanceTimersByTime(RIG_PLAN_SHIFTS_SETTLE_MS);
    });
    expect(onChange).not.toHaveBeenCalled();
    expect(slider().value).toBe("30");
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
    expect(slider().value).toBe("62");
    expect(screen.getByText("260,50 ₽/м")).toBeInTheDocument();
    expect(screen.queryByText("считается…")).toBeNull();
  });

  it("пока расчёт не пришёл, цена метра помечена «считается…»", () => {
    render(<RigPlanShiftsSlider value="25" norm={40} onChange={vi.fn()} rubPerM="260" rubPerMStale />);
    expect(screen.getByText("считается…")).toBeInTheDocument();
  });

  it("без права правки бегунок и сброс выключены", () => {
    render(<RigPlanShiftsSlider value="25" norm={40} onChange={vi.fn()} disabled />);
    expect(slider()).toBeDisabled();
    expect(screen.getByRole("button", { name: "Сбросить к нормативу" })).toBeDisabled();
  });
});

describe("rigShiftNorm", () => {
  it("норматив — у выбранного станка, а не у первого в списке", () => {
    const defaults = defaultsFixture();
    defaults.parameters.rig_plan_shifts = 40;
    defaults.rig_shift_norms = { RIG_SOLO: "40", RIG_ATLAS: "32", RIG_NONE: null };
    expect(rigShiftNorm(defaults, "RIG_ATLAS")).toBe("32");
    expect(rigShiftNorm(defaults, "RIG_SOLO")).toBe("40");
    // У типа норматива нет — null, а не норматив первого станка.
    expect(rigShiftNorm(defaults, "RIG_NONE")).toBeNull();
  });

  it("без карты нормативов (старый ответ) или без станка — норматив параметров", () => {
    const defaults = defaultsFixture();
    defaults.parameters.rig_plan_shifts = 40;
    expect(rigShiftNorm(defaults, "RIG_ATLAS")).toBe(40);
    defaults.rig_shift_norms = { RIG_SOLO: "40" };
    expect(rigShiftNorm(defaults, null)).toBe(40);
    expect(rigShiftNorm(defaults, "RIG_UNKNOWN")).toBe(40);
  });
});
