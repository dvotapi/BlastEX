// @vitest-environment jsdom
// Сдвиг скважин на плане (TASK-017, PR 1): по осям сетки повёрнутой
// раскладки, с привязкой, стрелками, парой у откоса, подсказкой у курсора и
// живой подсветкой нарушений.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { BlockContour, Hole, PatternParams, ToeLine } from "../../types/design";
import { fromAxes, layoutAxes, toAxes } from "./holeMove";
import { PlanCanvas } from "./PlanCanvas";
import fixture from "./testing/liveLspFixture.json";

type Case = { name: string; pattern_params: Partial<PatternParams>; holes: Hole[]; toe_line: ToeLine };

const contour = fixture.contour as unknown as BlockContour;
const cases = fixture.cases as unknown as Case[];
const plain = cases.find((c) => c.name === "plain")!;
const pair = cases.find((c) => c.name === "pair")!;
const axes = layoutAxes(30, contour);

afterEach(cleanup);

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  // jsdom без PointerEvent: события указателя — как события мыши (clientX/clientY).
  const globals = globalThis as unknown as Record<string, unknown>;
  if (!globals.PointerEvent) globals.PointerEvent = globals.MouseEvent;
  Element.prototype.setPointerCapture ??= () => {};
});

const noop = () => {};
const SCALE = 40;
const VIEW = { width: 800, height: 520 };

function setup(item: Case, center: string, selected: string[] = [], scale = SCALE, extra: { placingReceptor?: boolean } = {}) {
  const holes = item.holes;
  const c = holes.find((h) => h.id === center)!.collar;
  const camera = { x: c.x, y: c.y, scale };
  const onMoveHoles = vi.fn();
  const onCameraChange = vi.fn();
  const view = render(
    <PlanCanvas
      contour={contour}
      holes={holes}
      mode="holes"
      selected={new Set(selected)}
      onSelectedChange={noop}
      onContourChange={noop}
      onToggleFreeFace={noop}
      onMoveHoles={onMoveHoles}
      patternParams={item.pattern_params}
      onAddHole={noop}
      onDeleteHoles={noop}
      onSetHolesEnabled={noop}
      camera={camera}
      onCameraChange={onCameraChange}
      pendingFit={false}
      onFitApplied={noop}
      spacingHint={{ a: 5, b: 4 }}
      floorToeLine={item.toe_line}
      placingReceptor={extra.placingReceptor}
    />,
  );
  const toScreen = (x: number, y: number) => ({
    clientX: VIEW.width / 2 + (x - camera.x) * scale,
    clientY: VIEW.height / 2 - (y - camera.y) * scale,
  });
  const at = (id: string) => {
    const h = holes.find((hole) => hole.id === id)!;
    return toScreen(h.collar.x, h.collar.y);
  };
  const plan = screen.getByRole("application");
  return { view, plan, at, onMoveHoles, onCameraChange };
}

function drag(plan: HTMLElement, from: { clientX: number; clientY: number }, worldDelta: { x: number; y: number }, opts: { shiftKey?: boolean; release?: boolean } = {}) {
  const to = { clientX: from.clientX + worldDelta.x * SCALE, clientY: from.clientY - worldDelta.y * SCALE };
  fireEvent.pointerDown(plan, { ...from, button: 0 });
  fireEvent.pointerMove(plan, { ...to, shiftKey: opts.shiftKey ?? false });
  if (opts.release !== false) fireEvent.pointerUp(plan, to);
}

describe("PlanCanvas: сдвиг скважин в осях сетки", () => {
  it("на повёрнутой раскладке Δ — по осям сетки с привязкой a/4 и b/4", () => {
    const { plan, at, onMoveHoles } = setup(plain, "5-02");
    drag(plan, at("5-02"), fromAxes(1.4, 0.7, axes));
    expect(onMoveHoles).toHaveBeenCalledTimes(1);
    const [ids, dx, dy, series] = onMoveHoles.mock.calls[0];
    expect(ids).toEqual(["5-02"]);
    expect(series).toBeUndefined();
    const parts = toAxes({ x: dx, y: dy }, axes);
    expect(parts.along).toBeCloseTo(1.25, 2);
    expect(parts.across).toBeCloseTo(1, 2);
  });

  it("Shift — только по преобладающей оси сетки", () => {
    const { plan, at, onMoveHoles } = setup(plain, "5-02");
    drag(plan, at("5-02"), fromAxes(0.6, 2.2, axes), { shiftKey: true });
    const [, dx, dy] = onMoveHoles.mock.calls[0];
    const parts = toAxes({ x: dx, y: dy }, axes);
    expect(parts.along).toBeCloseTo(0, 2);
    expect(parts.across).toBeCloseTo(2, 2);
  });

  it("клик без сдвига MOVE_HOLES не шлёт", () => {
    const { plan, at, onMoveHoles } = setup(plain, "5-02");
    const p = at("5-02");
    fireEvent.pointerDown(plan, { ...p, button: 0 });
    fireEvent.pointerUp(plan, p);
    expect(onMoveHoles).not.toHaveBeenCalled();
  });

  it("вертикальная тянет пару у откоса, пара одна — одна", () => {
    const first = setup(pair, "4-01");
    drag(first.plan, first.at("4-01"), fromAxes(0, -1, axes));
    expect(first.onMoveHoles.mock.calls[0][0]).toEqual(["4-01", "4-01T"]);
    cleanup();
    const second = setup(pair, "4-01T");
    drag(second.plan, second.at("4-01T"), fromAxes(1.25, 0, axes));
    expect(second.onMoveHoles.mock.calls[0][0]).toEqual(["4-01T"]);
  });

  it("мелкий масштаб: нажатие на вертикальную берёт её, а не пару в метре от неё", () => {
    // 8 px/м: пара в 8 px — внутри радиуса попадания 12 px.
    const { plan, at, onMoveHoles } = setup(pair, "4-01", [], 8);
    const from = at("4-01");
    fireEvent.pointerDown(plan, { ...from, button: 0 });
    fireEvent.pointerMove(plan, { clientX: from.clientX + 20, clientY: from.clientY });
    fireEvent.pointerUp(plan, { clientX: from.clientX + 20, clientY: from.clientY });
    expect(onMoveHoles.mock.calls[0][0]).toEqual(["4-01", "4-01T"]);
  });

  it("вертикальная с парой — размерные линии до соседей остаются", () => {
    const { view, plan, at } = setup(pair, "4-02");
    drag(plan, at("4-02"), fromAxes(1.25, 0, axes), { release: false });
    expect(view.container.querySelectorAll("g.dimension").length).toBeGreaterThan(0);
    cleanup();
    const withPair = setup(pair, "4-01");
    drag(withPair.plan, withPair.at("4-01"), fromAxes(1.25, 0, axes), { release: false });
    const labels = [...withPair.view.container.querySelectorAll("g.dimension text")].map((t) => t.textContent);
    expect(labels.length).toBeGreaterThan(0);
    // До своей пары, которая едет вместе, линии нет (она была бы 1,00 м).
    expect(labels).not.toContain("1,00 м");
  });

  it("у курсора — Δ, сосед и ЛСП/W; первый ряд вглубь — красное кольцо", () => {
    const { view, plan, at, onMoveHoles } = setup(plain, "5-01");
    // На 1 м вглубь (против оси «к откосу»): ЛСП 4,68 м > W + 3 % = 4,12 м.
    drag(plan, at("5-01"), fromAxes(0, -1, axes), { release: false });
    const tip = screen.getByRole("status");
    expect(tip.textContent).toContain("Δ вдоль 0,00 м · Δ к откосу -1,00 м");
    expect(tip.textContent).toContain("До соседа");
    expect(tip.textContent).toContain("ЛСП 4,68 м / W 4,00 м");
    expect(tip.textContent).toContain("ЛСП 4,68 м больше допустимого 4,12 м (W + 3 %)");
    expect(view.container.querySelectorAll("g.hole-marker.live-violation")).toHaveLength(1);
    fireEvent.pointerUp(plan, at("5-01"));
    expect(onMoveHoles).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("status")).toBeNull();
    expect(view.container.querySelector("g.live-violation")).toBeNull();
  });

  it("сдвиг в допуске — без подсветки", () => {
    const { view, plan, at } = setup(plain, "5-02");
    drag(plan, at("5-02"), fromAxes(1.25, 0, axes), { release: false });
    expect(screen.getByRole("status").textContent).toContain("Δ вдоль +1,25 м");
    expect(view.container.querySelector("g.live-violation")).toBeNull();
  });
});

describe("PlanCanvas: стрелки", () => {
  it("стрелка с выделением — сдвиг на шаг привязки по оси сетки, серией", () => {
    const { plan, onMoveHoles, onCameraChange } = setup(plain, "5-02", ["5-02"]);
    fireEvent.keyDown(plan, { key: "ArrowUp" });
    expect(onCameraChange).not.toHaveBeenCalled();
    const [ids, dx, dy, series] = onMoveHoles.mock.calls[0];
    expect(ids).toEqual(["5-02"]);
    expect(typeof series).toBe("number");
    const parts = toAxes({ x: dx, y: dy }, axes);
    expect(parts.along).toBeCloseTo(1.25, 2);
    expect(parts.across).toBeCloseTo(0, 2);
  });

  it("Alt+стрелка — на 0,1 м", () => {
    const { plan, onMoveHoles } = setup(plain, "5-02", ["5-02"]);
    fireEvent.keyDown(plan, { key: "ArrowRight", altKey: true });
    const [, dx, dy] = onMoveHoles.mock.calls[0];
    expect(Math.hypot(dx, dy)).toBeCloseTo(0.1, 3);
    expect(Math.abs(toAxes({ x: dx, y: dy }, axes).across)).toBeCloseTo(0.1, 3);
  });

  it("стрелка у вертикальной двигает и её пару", () => {
    const { plan, onMoveHoles } = setup(pair, "4-01", ["4-01"]);
    fireEvent.keyDown(plan, { key: "ArrowDown" });
    expect(onMoveHoles.mock.calls[0][0]).toEqual(["4-01", "4-01T"]);
  });

  it("при постановке рецептора стрелки двигают план, а не выделенные скважины", () => {
    const { plan, onMoveHoles, onCameraChange } = setup(plain, "5-02", ["5-02"], SCALE, { placingReceptor: true });
    fireEvent.keyDown(plan, { key: "ArrowUp" });
    expect(onMoveHoles).not.toHaveBeenCalled();
    expect(onCameraChange).toHaveBeenCalled();
  });

  it("без выделения стрелки двигают план", () => {
    const { plan, onMoveHoles, onCameraChange } = setup(plain, "5-02");
    fireEvent.keyDown(plan, { key: "ArrowUp" });
    expect(onMoveHoles).not.toHaveBeenCalled();
    expect(onCameraChange).toHaveBeenCalled();
  });
});

describe("PlanCanvas: привязка и справка", () => {
  it("привязка сдвига по осям — a/4 вдоль, b/4 поперёк; выкл — без привязки", () => {
    const { plan, at, onMoveHoles } = setup(plain, "5-02");
    expect((screen.getByLabelText("Привязка сдвига вдоль ряда") as HTMLSelectElement).value).toBe("a4");
    expect((screen.getByLabelText("Привязка сдвига поперёк ряда") as HTMLSelectElement).value).toBe("b4");
    fireEvent.change(screen.getByLabelText("Привязка сдвига вдоль ряда"), { target: { value: "off" } });
    drag(plan, at("5-02"), fromAxes(1.4, 0, axes));
    const [, dx, dy] = onMoveHoles.mock.calls[0];
    expect(toAxes({ x: dx, y: dy }, axes).along).toBeCloseTo(1.4, 2);
  });

  it("справка «？» описывает мышь, Shift, привязку и стрелки", () => {
    setup(plain, "5-02");
    fireEvent.click(screen.getByTitle("Управление планом"));
    const help = document.querySelector(".plan-help")!.textContent!;
    expect(help).toContain("Сдвиг скважин");
    expect(help).toContain("Shift");
    expect(help).toContain("Привязка сдвига");
    expect(help).toContain("Alt+стрелка");
    expect(help).toContain("Пара у откоса");
  });
});
