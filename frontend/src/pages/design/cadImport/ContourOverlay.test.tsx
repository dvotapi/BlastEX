// @vitest-environment jsdom
// Слой контура на холсте: нижний контур виден, когда он отличается от верхнего.
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ContourOverlay } from "./ContourOverlay";
import { contourResult } from "./testing/fixtures";

afterEach(cleanup);

const toScreen = (point: number[]) => ({ x: point[0], y: point[1] });

function bottomPaths(result: ReturnType<typeof contourResult>) {
  const { container } = render(
    <svg>
      <ContourOverlay toScreen={toScreen} result={result} gaps={[]} picks={[]} selectedPath={null} />
    </svg>,
  );
  return container.querySelectorAll(".cad-contour-bottom");
}

describe("ContourOverlay: нижний контур", () => {
  it("виден, когда отличается от верхнего", () => {
    expect(bottomPaths(contourResult())).toHaveLength(1);
  });

  it("виден и при той же площади, если форма другая", () => {
    // Подошва ушла вправо на одной стороне и настолько же внутрь на другой.
    const top = { points: [[0, 0], [10, 0], [10, 10], [0, 10]], area_m2: 100, perimeter_m: 40 };
    const bottom = { points: [[2, 0], [12, 0], [12, 10], [2, 10]], area_m2: 100, perimeter_m: 40 };
    expect(bottomPaths(contourResult({ top, bottom }))).toHaveLength(1);
  });

  it("не рисуется поверх верхнего, когда совпадает с ним", () => {
    const top = { points: [[0, 0], [10, 0], [10, 10], [0, 10]], area_m2: 100, perimeter_m: 40 };
    expect(bottomPaths(contourResult({ top, bottom: { ...top, points: top.points.map((point) => [...point]) } }))).toHaveLength(0);
    cleanup();
    expect(bottomPaths(contourResult({ top, bottom: null }))).toHaveLength(0);
  });
});
