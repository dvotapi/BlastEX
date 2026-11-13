// @vitest-environment jsdom
// Правка коммутации на плане (TASK-017, PR 4): протяжка цепочки, клик по двум
// скважинам, «Ступень», выделение и Delete, перецепка конца, меню по линии,
// «без сигнала» и стартер.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { emptyNetwork, type BlockContour, type Hole, type InitiationNetwork } from "../../types/design";
import { PlanCanvas, type TieEditProps } from "./PlanCanvas";
import { TEST_TIE_CATALOG } from "./testing/tieCatalog";

afterEach(cleanup);

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  const globals = globalThis as unknown as Record<string, unknown>;
  // jsdom без PointerEvent: событие мыши с номером и видом указателя (тачскрин).
  if (!globals.PointerEvent) {
    globals.PointerEvent = class extends MouseEvent {
      pointerId: number;
      pointerType: string;
      constructor(type: string, init: PointerEventInit = {}) {
        super(type, init);
        this.pointerId = init.pointerId ?? 1;
        this.pointerType = init.pointerType ?? "mouse";
      }
    };
  }
  Element.prototype.setPointerCapture ??= () => {};
});

const noop = () => {};
const SCALE = 20;
const VIEW = { width: 800, height: 520 };
const CAMERA = { x: 7.5, y: 0, scale: SCALE };

function hole(id: string, x: number, y: number): Hole {
  return {
    id, row: 0, col: 0, collar: { x, y, z: 0 }, toe: { x, y, z: -11 }, diameter_mm: 165, subdrill_m: 1,
    kind: "production", source: "generated", enabled: true, intervals: [], water_intervals: [],
    measured_intervals: [], measured_water_intervals: [],
  } as Hole;
}

const HOLES = [hole("a", 0, 0), hole("b", 5, 0), hole("c", 10, 0), hole("d", 15, 0), hole("e", 0, 5)];
const NETWORK: InitiationNetwork = {
  ...emptyNetwork(),
  starters: ["a"],
  starter_items: [{ id: "st-a", hole_id: "a", delay_ms: 0, kind: "starter" }],
  surface_connectors: [{ id: "sc-a-b", from_hole: "a", to_hole: "b", delay_ms: 42, kind: "surface_nsi", product: "" }],
  connectors: [{ from_hole: "a", to_hole: "b", delay_ms: 42, kind: "surface_nsi" }],
};
const contour = { vertices: [], free_faces: [], bench: { crest_z_m: 0, toe_z_m: -10, face_angle_deg: 75 } } as unknown as BlockContour;

function point(x: number, y: number) {
  return { clientX: VIEW.width / 2 + (x - CAMERA.x) * SCALE, clientY: VIEW.height / 2 - (y - CAMERA.y) * SCALE };
}
const at = (id: string) => {
  const h = HOLES.find((item) => item.id === id)!;
  return point(h.collar.x, h.collar.y);
};

function setup(over: { unsignaled?: string[]; onHoleInspect?: (id: string) => void } = {}) {
  const tieEdit: TieEditProps = {
    catalog: TEST_TIE_CATALOG.systems.nonel,
    activeMs: 25,
    onActiveMsChange: vi.fn(),
    downholeMs: 500,
    onDownholeMsChange: vi.fn(),
    onEdit: vi.fn(),
    onTieContextMenu: vi.fn(),
  };
  const view = render(
    <PlanCanvas
      contour={contour}
      holes={HOLES}
      mode="tie"
      selected={new Set()}
      onSelectedChange={noop}
      onContourChange={noop}
      onToggleFreeFace={noop}
      onMoveHoles={noop}
      onAddHole={noop}
      onDeleteHoles={noop}
      onSetHolesEnabled={noop}
      camera={CAMERA}
      onCameraChange={noop}
      pendingFit={false}
      onFitApplied={noop}
      spacingHint={{ a: 5, b: 4 }}
      network={NETWORK}
      tieEdit={tieEdit}
      tieNominals={TEST_TIE_CATALOG.systems.nonel.surface_ms}
      unsignaledIds={new Set(over.unsignaled ?? [])}
      onHoleInspect={over.onHoleInspect}
    />,
  );
  return { view, plan: screen.getByRole("application"), tieEdit };
}

function click(plan: HTMLElement, p: { clientX: number; clientY: number }) {
  fireEvent.pointerDown(plan, { ...p, button: 0 });
  fireEvent.pointerUp(plan, p);
}

describe("PlanCanvas: правка коммутации", () => {
  it("протяжка через 4 скважины — одно действие с путём по порядку", () => {
    const { plan, tieEdit } = setup();
    fireEvent.pointerDown(plan, { ...at("a"), button: 0 });
    fireEvent.pointerMove(plan, at("b"));
    fireEvent.pointerMove(plan, point(7, 0.2));
    fireEvent.pointerMove(plan, at("c"));
    fireEvent.pointerMove(plan, at("d"));
    fireEvent.pointerUp(plan, at("d"));
    expect(tieEdit.onEdit).toHaveBeenCalledTimes(1);
    expect(tieEdit.onEdit).toHaveBeenCalledWith({ type: "add", path: ["a", "b", "c", "d"] });
  });

  it("клик по двум скважинам — одна связь", () => {
    const { plan, tieEdit } = setup();
    click(plan, at("c"));
    expect(tieEdit.onEdit).not.toHaveBeenCalled();
    expect(screen.getByText(/Связь от c/)).toBeInTheDocument();
    click(plan, at("d"));
    expect(tieEdit.onEdit).toHaveBeenCalledWith({ type: "add", path: ["c", "d"] });
  });

  it("«Ступень» (D): клик по линии ставит активный номинал", () => {
    const { plan, tieEdit } = setup();
    fireEvent.keyDown(plan, { key: "d" });
    expect(screen.getByRole("button", { name: /Ступень D/ })).toHaveAttribute("aria-pressed", "true");
    click(plan, point(2.5, 0));
    expect(tieEdit.onEdit).toHaveBeenCalledWith({ type: "delay", ids: ["sc-a-b"] });
  });

  it("«Ступень» рамкой — все захваченные линии", () => {
    const { plan, tieEdit } = setup();
    fireEvent.keyDown(plan, { key: "d" });
    fireEvent.pointerDown(plan, { ...point(2, 1.5), button: 0 });
    fireEvent.pointerMove(plan, point(3, -1.5));
    fireEvent.pointerUp(plan, point(3, -1.5));
    expect(tieEdit.onEdit).toHaveBeenCalledWith({ type: "delay", ids: ["sc-a-b"] });
  });

  it("клик по линии выделяет связь, Delete удаляет", () => {
    const { plan, tieEdit, view } = setup();
    click(plan, point(2.5, 0));
    expect(view.container.querySelector(".tie-link.selected")).not.toBeNull();
    fireEvent.keyDown(plan, { key: "Delete" });
    expect(tieEdit.onEdit).toHaveBeenCalledWith({ type: "remove", ids: ["sc-a-b"] });
  });

  it("перецепка конца выделенной связи на другую скважину", () => {
    const { plan, tieEdit } = setup();
    click(plan, point(2.5, 0));
    fireEvent.pointerDown(plan, { ...at("b"), button: 0 });
    fireEvent.pointerMove(plan, point(2, 3));
    fireEvent.pointerMove(plan, at("e"));
    fireEvent.pointerUp(plan, at("e"));
    expect(tieEdit.onEdit).toHaveBeenCalledWith({ type: "reconnect", id: "sc-a-b", end: "to", holeId: "e" });
  });

  it("правая кнопка по линии — меню связи", () => {
    const { plan, tieEdit } = setup();
    const p = point(2.5, 0);
    fireEvent.pointerDown(plan, { ...p, button: 2 });
    fireEvent.pointerUp(plan, { ...p, button: 2 });
    expect(tieEdit.onTieContextMenu).toHaveBeenCalledTimes(1);
    expect((tieEdit.onTieContextMenu as ReturnType<typeof vi.fn>).mock.calls[0][0].id).toBe("sc-a-b");
  });

  it("«Стартер» (S) и «В скважине» (H) — клик по скважине", () => {
    const { plan, tieEdit } = setup();
    fireEvent.keyDown(plan, { key: "s" });
    click(plan, at("c"));
    expect(tieEdit.onEdit).toHaveBeenCalledWith({ type: "starter", holeId: "c" });
    fireEvent.keyDown(plan, { key: "h" });
    click(plan, at("d"));
    expect(tieEdit.onEdit).toHaveBeenCalledWith({ type: "downhole", holeIds: ["d"] });
  });

  it("цифра — номинал палитры", () => {
    const { plan, tieEdit } = setup();
    fireEvent.keyDown(plan, { key: "3" });
    expect(tieEdit.onActiveMsChange).toHaveBeenCalledWith(42);
  });

  it("без сигнала — красное кольцо, стартер — значок, связь — цвет ступени", () => {
    const { view } = setup({ unsignaled: ["c", "d"] });
    expect(view.container.querySelectorAll(".unsignaled-ring")).toHaveLength(2);
    expect(view.container.querySelectorAll(".starter-glyph")).toHaveLength(1);
    expect((view.container.querySelector(".tie-link") as HTMLElement).style.color).toBeTruthy();
  });

  it("быстрая протяжка: скважины между редкими событиями указателя не пропускаются", () => {
    const { plan, tieEdit } = setup();
    fireEvent.pointerDown(plan, { ...at("a"), button: 0 });
    fireEvent.pointerMove(plan, at("d"));
    fireEvent.pointerUp(plan, at("d"));
    expect(tieEdit.onEdit).toHaveBeenCalledWith({ type: "add", path: ["a", "b", "c", "d"] });
  });

  it("сеть сменилась не с плана — выделение связей снято; своя правка его не снимает", () => {
    // Как на странице: правка с плана меняет сеть в том же событии.
    let replaceNetwork: (network: InitiationNetwork) => void = () => {};
    function Harness() {
      const [network, setNetwork] = useState(NETWORK);
      replaceNetwork = setNetwork;
      const tieEdit: TieEditProps = {
        catalog: TEST_TIE_CATALOG.systems.nonel,
        activeMs: 25,
        onActiveMsChange: noop,
        downholeMs: 500,
        onDownholeMsChange: noop,
        onEdit: () => setNetwork({ ...network, surface_connectors: [{ ...network.surface_connectors[0], delay_ms: 25 }] }),
      };
      return (
        <PlanCanvas
          contour={contour} holes={HOLES} mode="tie" selected={new Set()} onSelectedChange={noop}
          onContourChange={noop} onToggleFreeFace={noop} onMoveHoles={noop} onAddHole={noop}
          onDeleteHoles={noop} onSetHolesEnabled={noop} camera={CAMERA} onCameraChange={noop}
          pendingFit={false} onFitApplied={noop} spacingHint={{ a: 5, b: 4 }} network={network}
          tieEdit={tieEdit} tieNominals={TEST_TIE_CATALOG.systems.nonel.surface_ms}
        />
      );
    }
    const view = render(<Harness />);
    const plan = screen.getByRole("application");
    fireEvent.keyDown(plan, { key: "d" });
    click(plan, point(2.5, 0));
    expect(view.container.querySelector(".tie-link.selected")).not.toBeNull();
    expect(view.container.querySelector(".connector-label")?.textContent).toBe("25");
    // Сеть сменилась сама (отмена, построение схемы) — выделения нет.
    act(() => replaceNetwork({ ...NETWORK }));
    expect(view.container.querySelector(".tie-link.selected")).toBeNull();
  });

  it("A в коммутации не включает скрытый инструмент «Скважина»", () => {
    const { plan } = setup();
    fireEvent.keyDown(plan, { key: "a" });
    expect(screen.getByRole("button", { name: /Связь T/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("двойной клик по скважине открывает карточку", () => {
    const onHoleInspect = vi.fn();
    const { plan } = setup({ onHoleInspect });
    fireEvent.doubleClick(plan, at("c"));
    expect(onHoleInspect).toHaveBeenCalledWith("c");
  });

  it("тачскрин: «Стартер» правит сеть только при отпускании пальца, щипок — не правит", () => {
    const { plan, tieEdit } = setup();
    fireEvent.keyDown(plan, { key: "s" });
    fireEvent.pointerDown(plan, { ...at("c"), button: 0, pointerId: 1, pointerType: "touch" });
    expect(tieEdit.onEdit).not.toHaveBeenCalled();
    fireEvent.pointerUp(plan, { ...at("c"), pointerId: 1, pointerType: "touch" });
    expect(tieEdit.onEdit).toHaveBeenCalledWith({ type: "starter", holeId: "c" });
    (tieEdit.onEdit as ReturnType<typeof vi.fn>).mockClear();
    fireEvent.pointerDown(plan, { ...at("d"), button: 0, pointerId: 2, pointerType: "touch" });
    fireEvent.pointerDown(plan, { ...point(12, 3), button: 0, pointerId: 3, pointerType: "touch" });
    fireEvent.pointerUp(plan, { ...at("d"), pointerId: 2, pointerType: "touch" });
    fireEvent.pointerUp(plan, { ...point(12, 3), pointerId: 3, pointerType: "touch" });
    expect(tieEdit.onEdit).not.toHaveBeenCalled();
  });
});

