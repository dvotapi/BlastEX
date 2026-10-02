// @vitest-environment jsdom
// Шаг «Итог» (TASK-013, PR 3): площади, средняя высота, объём по
// поверхностям, S ср × H, объём с карты и расхождение, подтверждение высоты.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { initialSurface, type SurfaceState } from "./surfaceState";
import { SummaryStep, type SummaryStepProps } from "./SummaryStep";
import { cadSource, contourResult, surfaceResult } from "./testing/fixtures";

afterEach(cleanup);

function renderStep(extra: Partial<SummaryStepProps> = {}) {
  const props: SummaryStepProps = {
    contour: contourResult(),
    surface: surfaceResult(),
    state: initialSurface(cadSource()),
    onChange: vi.fn(),
    mapArea: null,
    disabled: false,
    ...extra,
  };
  render(<SummaryStep {...props} />);
  return props;
}

function lastState(props: SummaryStepProps): SurfaceState {
  const calls = (props.onChange as ReturnType<typeof vi.fn>).mock.calls;
  return calls[calls.length - 1][0];
}

function value(group: HTMLElement, term: string): string {
  return within(group).getByText(term).nextSibling?.textContent ?? "";
}

describe("SummaryStep", () => {
  it("площади, высота, объёмы", () => {
    renderStep();

    const totals = screen.getByRole("group", { name: "Итоги блока" });
    expect(value(totals, "S верх")).toBe("2789,9 м²");
    expect(value(totals, "S низ")).toBe("4120,9 м²");
    expect(value(totals, "S ср")).toBe("3455,4 м²");
    expect(value(totals, "Средняя высота")).toBe("10,50 м");
    expect(value(totals, "Объём по поверхностям")).toBe("36939 м³");
    expect(value(totals, "S ср × H")).toBe("36282 м³");
    expect(screen.getByText(/по нижней бровке/)).toBeTruthy();
  });

  it("объём с карты и расхождение в процентах", () => {
    const props = renderStep({ state: { ...initialSurface(cadSource()), mapVolume: "28279,39" }, mapArea: 2772.49 });

    const totals = screen.getByRole("group", { name: "Итоги блока" });
    expect(value(totals, "Объём по поверхностям")).toBe("36939 м³ (+30,62 %)");
    expect(value(totals, "S ср × H")).toBe("36282 м³ (+28,30 %)");
    expect(value(totals, "S верх")).toBe("2789,9 м² (+0,63 %)");
    fireEvent.change(screen.getByLabelText("Объём с карты, м³"), { target: { value: "30000" } });
    expect(lastState(props).mapVolume).toBe("30000");
  });

  it("высота вне 2–25 м — флажок подтверждения", () => {
    const surface = surfaceResult({ bench: { floor_z_m: 410, mean_height_m: 0.6, needs_confirmation: true } });
    const props = renderStep({ surface });

    const confirm = screen.getByLabelText(/Подтверждаю высоту уступа 0,6 м/) as HTMLInputElement;
    expect(confirm.checked).toBe(false);
    fireEvent.click(confirm);
    expect(lastState(props).confirmHeight).toBe(0.6);
  });

  it("кровля-плоскость: объём — S ср × H", () => {
    renderStep({
      surface: surfaceResult({ plane: true, volume: { ...surfaceResult().volume, basis: "mean", volume_m3: 36281.9 } }),
    });

    expect(screen.getByText(/кровля — плоскость/)).toBeTruthy();
  });

  it("обычная высота подтверждения не просит", () => {
    renderStep();

    expect(screen.queryByLabelText(/Подтверждаю высоту/)).toBeNull();
  });

  it("что сделает «Построить блок»", () => {
    renderStep();

    expect(screen.getByText(/кровлю из чертежа/).textContent).toContain("поверхность подошвы снимается");
  });
});
