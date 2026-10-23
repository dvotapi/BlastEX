// @vitest-environment jsdom
// Предпросмотр варианта подбора раскладки: устья и связи поверх плана,
// полупрозрачно, без выбора и подсказок.
import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { emptyContour, emptyHoleGeology, emptyNetwork, type Hole, type InitiationNetwork } from "../../types/design";
import { PlanCanvas } from "./PlanCanvas";

afterEach(cleanup);

beforeAll(() => {
  // jsdom без ResizeObserver: холсту достаточно заглушки.
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
});

const noop = () => {};

function hole(id: string, x: number): Hole {
  return {
    id,
    row: 0,
    col: 0,
    collar: { x, y: 0, z: 0 },
    toe: { x, y: 0, z: -10 },
    diameter_mm: 152,
    subdrill_m: 1,
    kind: "production",
    source: "generated",
    enabled: true,
    ...emptyHoleGeology(),
  };
}

const PREVIEW_NETWORK: InitiationNetwork = {
  ...emptyNetwork(),
  connectors: [{ id: "c1", from_hole: "p1", to_hole: "p2", delay_ms: 42, kind: "surface" } as InitiationNetwork["connectors"][number]],
};

function renderPlan(preview: { holes: Hole[]; network: InitiationNetwork } | null) {
  return render(
    <PlanCanvas
      contour={emptyContour()}
      holes={[hole("a", 0)]}
      mode="holes"
      selected={new Set()}
      onSelectedChange={noop}
      onContourChange={noop}
      onToggleFreeFace={noop}
      onMoveHoles={noop}
      onAddHole={noop}
      onDeleteHoles={noop}
      onSetHolesEnabled={noop}
      camera={{ x: 0, y: 0, scale: 6 }}
      onCameraChange={noop}
      pendingFit={false}
      onFitApplied={noop}
      spacingHint={{ a: 4, b: 3 }}
      preview={preview}
    />,
  );
}

describe("PlanCanvas: предпросмотр варианта", () => {
  it("рисует устья и связи варианта отдельным слоем поверх плана", () => {
    const { container } = renderPlan({ holes: [hole("p1", 5), hole("p2", 10)], network: PREVIEW_NETWORK });
    const layer = container.querySelector("g.layout-preview");
    expect(layer).not.toBeNull();
    expect(layer!.querySelectorAll("circle")).toHaveLength(2);
    expect(layer!.querySelectorAll("line")).toHaveLength(1);
    // Слой не перехватывает мышь: выбор и подсказки — только у скважин паспорта.
    expect(layer!.getAttribute("pointer-events")).toBe("none");
    expect(layer!.querySelector("title")).toBeNull();
    // Скважины паспорта остаются как были.
    expect(container.querySelectorAll("g.hole-marker")).toHaveLength(1);
  });

  it("без предпросмотра слоя нет", () => {
    const { container } = renderPlan(null);
    expect(container.querySelector("g.layout-preview")).toBeNull();
  });
});
