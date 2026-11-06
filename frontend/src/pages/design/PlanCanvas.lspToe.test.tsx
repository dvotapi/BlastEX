// @vitest-environment jsdom
// Линия подошвы, от которой считается ЛСП: в слое «Нижняя бровка», сплошная
// по съёмке и пунктиром по углу откоса, с подсказкой об источнике.
import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { emptyContour, type ToeLine } from "../../types/design";
import { PlanCanvas } from "./PlanCanvas";
import { lspToeTitle, toeLineWarning } from "./toeLineText";

afterEach(cleanup);

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
});

const noop = () => {};

function renderPlan(toeLine: ToeLine, toe = true) {
  const contour = emptyContour();
  contour.bench = { ...contour.bench, face_angle_deg: 75 };
  return render(
    <PlanCanvas
      contour={contour}
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
      floorToeLine={toeLine}
    />,
  );
}

describe("PlanCanvas: подошва для ЛСП", () => {
  it("по съёмке — сплошная, с подсказкой «нижняя бровка из чертежа»", () => {
    const { container } = renderPlan({ source: "survey", polylines: [[[44, 0], [44, 20]]] });
    const line = container.querySelector("polyline.lsp-toe");
    expect(line).not.toBeNull();
    expect(line?.classList.contains("by-angle")).toBe(false);
    expect(line?.querySelector("title")?.textContent).toBe("Подошва для ЛСП — нижняя бровка из чертежа");
  });

  it("по углу — пунктир, с углом от вертикали и причиной", () => {
    const { container } = renderPlan({ source: "angle", reason: "no_survey", polylines: [[[42.68, 0], [42.68, 20]]] });
    const line = container.querySelector("polyline.lsp-toe");
    expect(line?.classList.contains("by-angle")).toBe(true);
    expect(line?.querySelector("title")?.textContent).toBe(
      "Подошва для ЛСП — по углу откоса 15° от вертикали: нижней бровки в паспорте нет",
    );
  });

  it("откос при импорте не найден — подсказка и предупреждение сводки", () => {
    const line: ToeLine = { source: "angle", reason: "survey_unmatched", polylines: [] };
    expect(lspToeTitle(line, 75)).toBe(
      "Подошва для ЛСП — по углу откоса 15° от вертикали: откос при импорте не найден (нижний контур совпал с верхним) — постройте контур заново",
    );
    expect(toeLineWarning(line)).toContain("постройте контур заново");
    expect(toeLineWarning({ source: "angle", reason: "no_survey", polylines: [] })).toBe("");
    expect(toeLineWarning(null)).toBe("");
  });

  it("угол 90° — подошва совпадает с бровкой", () => {
    expect(lspToeTitle({ source: "angle", reason: "no_survey", polylines: [] }, 90)).toBe(
      "Подошва для ЛСП совпадает с бровкой — угол откоса не задан: нижней бровки в паспорте нет",
    );
  });

  it("скрывается вместе со слоем «Нижняя бровка»", () => {
    const { container } = renderPlan({ source: "survey", polylines: [[[44, 0], [44, 20]]] }, false);
    expect(container.querySelector("polyline.lsp-toe")).toBeNull();
  });
});
