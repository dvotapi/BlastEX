// @vitest-environment jsdom
// Холст импорта на шаге «Контур»: щелчок отдаёт мировые координаты, линию и
// привязку; на шаге «Слои» щелчок по линии — выбор, как в PR 1.
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CadCanvas, type ScreenProjector } from "./CadCanvas";
import { SnapIndex } from "./contourGeometry";
import { cadSource } from "./testing/fixtures";

afterEach(cleanup);

const SOURCE = cadSource();

/** Экранная точка мировой — через тот же проектор, что у холста (наложение отдаёт его). */
let project: ScreenProjector = () => ({ x: 0, y: 0 });
const capture = (toScreen: ScreenProjector) => {
  project = toScreen;
  return null;
};

function at(x: number, y: number) {
  const point = project([x, y]);
  return { clientX: point.x, clientY: point.y };
}

function renderCanvas(extra: Partial<Parameters<typeof CadCanvas>[0]> = {}) {
  const props = {
    overlay: capture,
    entities: SOURCE.entities,
    fitKey: "k",
    hover: null,
    selected: null,
    emphasized: [],
    onHover: vi.fn(),
    onSelect: vi.fn(),
    ...extra,
  };
  render(<CadCanvas {...props} />);
  return props;
}

describe("CadCanvas: указание точки", () => {
  it("щелчок по пустому месту — мировые координаты без линии", () => {
    const onPick = vi.fn();
    const props = renderCanvas({ tool: true, onPick });

    const svg = document.querySelector("svg.cad-canvas") as SVGSVGElement;
    // Центр холста — центр габарита чертежа, и через него идёт замыкающее
    // ребро контура 769; пустое место — в стороне от линий.
    expect(project([115, 192.5])).toEqual({ x: 400, y: 300 });
    fireEvent.click(svg, at(95, 210));

    expect(onPick).toHaveBeenCalledTimes(1);
    const [pick] = onPick.mock.calls[0];
    expect(pick.handle).toBeNull();
    expect(pick.world[0]).toBeCloseTo(95, 1);
    expect(pick.world[1]).toBeCloseTo(210, 1);
    expect(props.onSelect).not.toHaveBeenCalled();
  });

  it("щелчок по линии — её handle и привязка", () => {
    const onPick = vi.fn();
    const snapIndex = new SnapIndex(SOURCE.entities.filter((entity) => entity.geometry_type === "line"), []);
    renderCanvas({ tool: true, onPick, snapIndex });

    // Нижнее ребро контура 769: (90; 170) → (140; 170).
    fireEvent.click(document.querySelector("svg.cad-canvas") as Element, at(120, 170));

    expect(onPick.mock.calls[0][0].handle).toBe("769");
    expect(onPick.mock.calls[0][0].world[1]).toBeCloseTo(170, 0);
  });

  it("на шаге «Слои» щелчок по линии — выбор", () => {
    const onPick = vi.fn();
    const props = renderCanvas({ onPick });

    fireEvent.click(document.querySelector("svg.cad-canvas") as Element, at(120, 170));

    expect(props.onSelect).toHaveBeenCalledWith({ layer: "блок 66 вар 2", handle: "769" });
    expect(onPick).not.toHaveBeenCalled();
  });

  it("наложение рисуется в экранных координатах", () => {
    renderCanvas({ overlay: (toScreen) => <circle className="probe" cx={toScreen([115, 192.5]).x} cy={toScreen([115, 192.5]).y} r={2} /> });
    const probe = document.querySelector("circle.probe") as SVGCircleElement;
    expect(Number(probe.getAttribute("cx"))).toBeCloseTo(400, 0);
    expect(Number(probe.getAttribute("cy"))).toBeCloseTo(300, 0);
  });
});

describe("CadCanvas: базовый слой на canvas (PR 4)", () => {
  it("линии чертежа — один холст, а не узел SVG на линию", () => {
    renderCanvas();

    expect(document.querySelector("canvas.cad-base")).not.toBeNull();
    expect(document.querySelectorAll("svg.cad-canvas path.cad-line")).toHaveLength(0);
    expect(document.querySelectorAll("svg.cad-canvas .cad-hit")).toHaveLength(0);
  });

  it("наведение сообщает линию под курсором, уход — пусто", () => {
    const props = renderCanvas();
    const svg = document.querySelector("svg.cad-canvas") as Element;

    fireEvent.mouseMove(svg, at(115, 181));
    expect(props.onHover).toHaveBeenLastCalledWith({ layer: "Горизонт +410", handle: "733" });
    fireEvent.mouseMove(svg, at(115.2, 181));
    expect(props.onHover).toHaveBeenCalledTimes(1);

    fireEvent.mouseMove(svg, at(60, 60));
    expect(props.onHover).toHaveBeenLastCalledWith(null);
    fireEvent.mouseMove(svg, at(110, 190));
    expect(props.onHover).toHaveBeenLastCalledWith({ layer: "Отметка", handle: null });
    fireEvent.mouseLeave(svg);
    expect(props.onHover).toHaveBeenLastCalledWith(null);
  });

  it("подсветка наведённого слоя — SVG поверх холста", () => {
    renderCanvas({ hover: { layer: "Горизонт +410", handle: null } });

    expect(document.querySelector('.cad-highlight[data-handle="6C3"]')?.classList.contains("is-hovered")).toBe(true);
    expect(document.querySelector('.cad-highlight[data-handle="769"]')).toBeNull();
  });

  it("щелчок после панорамы — не выбор", () => {
    const props = renderCanvas();
    const svg = document.querySelector("svg.cad-canvas") as Element;

    fireEvent.pointerDown(svg, { button: 0, ...at(120, 170) });
    fireEvent.pointerMove(svg, { ...at(130, 180) });
    fireEvent.click(svg, at(130, 180));

    expect(props.onSelect).not.toHaveBeenCalled();
  });
});
