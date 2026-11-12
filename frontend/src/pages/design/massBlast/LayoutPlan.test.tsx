// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { LayoutPlan } from "./LayoutPlan";
import { validation } from "./testFixtures";

afterEach(cleanup);

beforeAll(() => {
  // jsdom без PointerEvent: события указателя — как события мыши (clientX/clientY).
  const globals = window as unknown as Record<string, unknown>;
  if (!globals.PointerEvent) globals.PointerEvent = globals.MouseEvent;
  // jsdom не считает геометрию SVG: экран = координаты вида (y вида = −северная).
  const proto = window.SVGSVGElement.prototype as unknown as Record<string, unknown>;
  proto.getScreenCTM = () => ({ inverse: () => ({}) });
  proto.createSVGPoint = () => {
    const point = { x: 0, y: 0, matrixTransform: () => ({ x: point.x, y: point.y }) };
    return point;
  };
});

const graphics = validation().context.graphics!;

describe("план Г.5 для точек", () => {
  it("щелчок ставит точку выбранного вида в координатах объекта (север вверх)", () => {
    const onPlace = vi.fn();
    render(<LayoutPlan graphics={graphics} points={[]} kind="guard_post" postRef="2" editable onPlace={onPlace} onMove={() => {}} />);
    const plan = screen.getByRole("img", { name: /Ситуационный план/ });
    fireEvent.pointerDown(plan, { clientX: 12, clientY: -30, pointerId: 1 });
    fireEvent.pointerUp(plan, { clientX: 12, clientY: -30, pointerId: 1 });
    expect(onPlace).toHaveBeenCalledWith("guard_post", "2", 12, 30);
  });

  it("перетаскивание точки двигает её, а не ставит новую", () => {
    const onPlace = vi.fn();
    const onMove = vi.fn();
    render(
      <LayoutPlan graphics={graphics} points={[{ kind: "blast_station", ref: "", x: "5", y: "5", label: "" }]} kind="shelter" postRef=""
        editable onPlace={onPlace} onMove={onMove} />,
    );
    const point = screen.getByTestId("point-0");
    fireEvent.pointerDown(point, { clientX: 5, clientY: -5, pointerId: 1 });
    fireEvent.pointerMove(point, { clientX: 25, clientY: -15, pointerId: 1 });
    fireEvent.pointerUp(point, { clientX: 25, clientY: -15, pointerId: 1 });
    expect(onMove).toHaveBeenCalledWith(0, 25, 15);
    expect(onPlace).not.toHaveBeenCalled();
  });

  it("только для чтения — щелчок ничего не ставит", () => {
    const onPlace = vi.fn();
    render(<LayoutPlan graphics={graphics} points={[]} kind="gather" postRef="" editable={false} onPlace={onPlace} onMove={() => {}} />);
    const plan = screen.getByRole("img", { name: /Ситуационный план/ });
    fireEvent.pointerDown(plan, { clientX: 1, clientY: 1, pointerId: 1 });
    fireEvent.pointerUp(plan, { clientX: 1, clientY: 1, pointerId: 1 });
    expect(onPlace).not.toHaveBeenCalled();
    expect(screen.getByText(/Ситуации карьера нет/)).toBeTruthy();
  });
});
