// @vitest-environment jsdom
// Подошва по углу там, где съёмка нижней бровки — развал: пунктир в слое
// «Нижняя бровка» с подсказкой.
import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { emptyContour } from "../../types/design";
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

function renderPlan(toe: boolean) {
  return render(
    <PlanCanvas
      contour={emptyContour()}
      holes={[]}
      mode="contour"
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
      layers={{ fill: true, crest: true, toe, face: true, holes: true }}
      angleToePolylines={[[[0, -2.68], [10, -2.68]]]}
    />,
  );
}

describe("PlanCanvas: подошва по углу", () => {
  it("рисуется пунктиром с подсказкой в слое нижней бровки", () => {
    const { container } = renderPlan(true);
    const line = container.querySelector("polyline.angle-toe");
    expect(line).not.toBeNull();
    expect(line?.querySelector("title")?.textContent).toBe("Подошва по углу (съёмка здесь — развал)");
  });

  it("скрывается вместе со слоем «Нижняя бровка»", () => {
    const { container } = renderPlan(false);
    expect(container.querySelector("polyline.angle-toe")).toBeNull();
  });
});
