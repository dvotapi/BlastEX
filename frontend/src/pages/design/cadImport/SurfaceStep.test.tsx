// @vitest-environment jsdom
// Шаг «Поверхность» и его слой на холсте (TASK-013, PR 3): роли линий в
// кровле, подошва, перебур паспорта, качество, выбросы, конфликты и пороги.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { initialSurface, type SurfaceState } from "./surfaceState";
import { SurfaceOverlay } from "./SurfaceOverlay";
import { SurfaceStep, type SurfaceStepProps } from "./SurfaceStep";
import { CAD_META, cadSource, contourResult, surfaceResult } from "./testing/fixtures";

afterEach(cleanup);

const SOURCE = cadSource();

function renderStep(extra: Partial<SurfaceStepProps> = {}) {
  const props: SurfaceStepProps = {
    source: SOURCE,
    meta: CAD_META,
    state: initialSurface(SOURCE),
    onChange: vi.fn(),
    result: surfaceResult(),
    pending: false,
    error: "",
    contour: contourResult(),
    subdrill: 1.5,
    disabled: false,
    onFocus: vi.fn(),
    ...extra,
  };
  render(<SurfaceStep {...props} />);
  return props;
}

function lastState(props: SurfaceStepProps): SurfaceState {
  const calls = (props.onChange as ReturnType<typeof vi.fn>).mock.calls;
  return calls[calls.length - 1][0];
}

describe("SurfaceStep", () => {
  it("роли линий в кровле — флажки с подписью «как входит»", () => {
    const props = renderStep();

    const roles = screen.getByRole("group", { name: "Линии в кровле" });
    const top = within(roles).getByLabelText(/Бровка верхняя/) as HTMLInputElement;
    expect(top.checked).toBe(true);
    expect(within(roles).getAllByText(/жёсткий ограничитель, вершины через 1 м/, { selector: "small" })).toHaveLength(2);
    expect(within(roles).getByText(/точки через 2 м и мягкий ограничитель/)).toBeTruthy();

    fireEvent.click(within(roles).getByLabelText(/Горизонталь/));
    expect(lastState(props).roles).not.toContain("contour_line");
  });

  it("счётчик отметок — точки и линии, без подписей: подписи в кровлю не входят", () => {
    renderStep();

    const roles = screen.getByRole("group", { name: "Линии в кровле" });
    expect(within(roles).getByLabelText(/Отметки поверхности/).closest("label")?.textContent).toContain("Отметки поверхности · 1");
  });

  it("подошва предзаполнена из контура, перебур паспорта — только чтение", () => {
    const props = renderStep();

    const floor = screen.getByLabelText("Подошва, м") as HTMLInputElement;
    expect(floor.value).toBe("");
    expect(floor.placeholder).toContain("410");
    fireEvent.change(floor, { target: { value: "409,5" } });
    expect(lastState(props).floor).toBe("409,5");
    const subdrill = screen.getByLabelText("Перебур паспорта, м") as HTMLInputElement;
    expect(subdrill.readOnly).toBe(true);
    expect(subdrill.value).toBe("1,5");
  });

  it("метрики качества видны", () => {
    renderStep();

    const quality = screen.getByRole("group", { name: "Качество кровли" });
    expect(within(quality).getByText("Отметок").nextSibling?.textContent).toBe("206");
    expect(within(quality).getByText("Покрытие контура").nextSibling?.textContent).toBe("99,9 %");
    expect(within(quality).getByText("До ближайшей отметки").nextSibling?.textContent).toBe("до 10,9 м");
    expect(within(quality).getByText("Средняя высота уступа").nextSibling?.textContent).toBe("10,5 м");
    expect(within(quality).getByText("Построение").nextSibling?.textContent).toBe("CDT");
  });

  it("выброс исключается, исключённая отметка возвращается, наведение подсвечивает место", () => {
    const props = renderStep();

    const outliers = screen.getByRole("list", { name: "Выбросы" });
    const row = within(outliers).getByText(/51C/).closest("li") as HTMLElement;
    expect(row.textContent).toContain("+9,2 м");
    fireEvent.mouseEnter(row);
    expect(props.onFocus).toHaveBeenLastCalledWith({ points: [[110, 190, 410.84]], segments: [] });
    fireEvent.click(within(row).getByRole("button", { name: "Исключить" }));
    expect(lastState(props).excluded).toEqual(["51C"]);

    cleanup();
    const excluded = renderStep({
      state: { ...initialSurface(SOURCE), excluded: ["51C"] },
      result: surfaceResult({ outliers: [], excluded_points: [{ id: "51C", point: [110, 190, 410.84] }] }),
    });
    fireEvent.click(within(screen.getByRole("list", { name: "Исключённые отметки" })).getByRole("button", { name: "Вернуть" }));
    expect(lastState(excluded).excluded).toEqual([]);
  });

  it("конфликты отметок и пороги — списком", () => {
    renderStep();

    const conflicts = screen.getByRole("list", { name: "Конфликты отметок" });
    expect(conflicts.textContent).toContain("Бровка верхняя 420,40");
    expect(conflicts.textContent).toContain("Характерная линия 419,90");
    expect(conflicts.textContent).toContain("принята 420,40");
    expect(screen.getByRole("list", { name: "Возможные пороги" }).textContent).toContain("+1,7 м");
  });

  it("ошибка построения и предупреждения кровли видны", () => {
    renderStep({
      result: surfaceResult({
        ok: false,
        issues: [{ code: "no_marks", message: "Отметок и верхней бровки нет — кровлю не из чего построить.", point: null }],
        warnings: [{ code: "no_crest_top", message: "Верхней бровки нет — первый ряд без бровки.", level: "warning" }],
      }),
    });

    expect(screen.getByRole("alert").textContent).toContain("кровлю не из чего построить");
    expect(screen.getByText(/первый ряд без бровки/)).toBeTruthy();
  });

  it("без построенного контура — подсказка", () => {
    renderStep({ contour: contourResult({ ok: false }), result: null });

    expect(screen.getByText(/Сначала постройте контур/)).toBeTruthy();
  });
});

describe("SurfaceOverlay", () => {
  const toScreen = (point: number[]) => ({ x: point[0], y: point[1] });

  it("рёбра TIN, выбросы, конфликты, пороги и подсветка места", () => {
    const { container } = render(
      <svg>
        <SurfaceOverlay toScreen={toScreen} result={surfaceResult()} focus={{ points: [[110, 190]], segments: [] }} />
      </svg>,
    );

    const tin = container.querySelector(".cad-tin") as SVGPathElement;
    // 2 треугольника с общим ребром — 5 рёбер.
    expect(tin.getAttribute("d")?.match(/M/g)).toHaveLength(5);
    expect(container.querySelectorAll(".cad-outlier")).toHaveLength(1);
    expect(container.querySelectorAll(".cad-conflict")).toHaveLength(1);
    expect(container.querySelectorAll(".cad-threshold")).toHaveLength(1);
    expect(container.querySelectorAll(".cad-surface-focus")).toHaveLength(1);
  });
});
