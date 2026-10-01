// @vitest-environment jsdom
// Холст импорта на шаге «Контур»: щелчок отдаёт мировые координаты, линию и
// привязку; на шаге «Слои» щелчок по линии — выбор, как в PR 1.
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CadCanvas } from "./CadCanvas";
import { SnapIndex } from "./contourGeometry";
import { cadSource } from "./testing/fixtures";

afterEach(cleanup);

const SOURCE = cadSource();

function renderCanvas(extra: Partial<Parameters<typeof CadCanvas>[0]> = {}) {
  const props = {
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
    fireEvent.click(svg, { clientX: 400, clientY: 300 });

    expect(onPick).toHaveBeenCalledTimes(1);
    const [pick] = onPick.mock.calls[0];
    expect(pick.handle).toBeNull();
    // Центр холста — центр габарита чертежа.
    expect(pick.world[0]).toBeCloseTo(115, 0);
    expect(pick.world[1]).toBeCloseTo(192.5, 0);
    expect(props.onSelect).not.toHaveBeenCalled();
  });

  it("щелчок по линии — её handle и привязка", () => {
    const onPick = vi.fn();
    const snapIndex = new SnapIndex(SOURCE.entities.filter((entity) => entity.geometry_type === "line"), []);
    renderCanvas({ tool: true, onPick, snapIndex });

    fireEvent.click(document.querySelector('.cad-hit[data-handle="769"]') as Element, { clientX: 400, clientY: 300 });

    expect(onPick.mock.calls[0][0].handle).toBe("769");
  });

  it("на шаге «Слои» щелчок по линии — выбор", () => {
    const onPick = vi.fn();
    const props = renderCanvas({ onPick });

    fireEvent.click(document.querySelector('.cad-hit[data-handle="769"]') as Element);

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
