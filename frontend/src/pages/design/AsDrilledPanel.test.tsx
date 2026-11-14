// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AsDrilledCompareResponse, HoleDeviation } from "../../types/design";
import { AsDrilledPanel } from "./AsDrilledPanel";

afterEach(cleanup);

const row: HoleDeviation = {
  design_hole_id: "2-03",
  role: "executed",
  collar_offset_m: 0.2,
  toe_offset_m: 0.2,
  depth_deviation_m: null,
  angle_deviation_deg: 0,
  azimuth_deviation_deg: 0,
  actual_burden_m: null,
  actual_spacing_m: null,
  designed_burden_m: null,
  designed_spacing_m: null,
  actual_depth_m: null,
  designed_depth_m: 12,
  actual_diameter_mm: 0,
  designed_diameter_mm: 0,
};

const result: AsDrilledCompareResponse = {
  role: "executed",
  compared_count: 1,
  designed_count: 1,
  as_drilled_count: 1,
  pattern_basis: "executed",
  deviations: [row],
  warnings: [],
  as_drilled_holes: [],
};

describe("AsDrilledPanel", () => {
  it("глубина не замерена (съёмка без глубины) — «—», а не 0", () => {
    render(
      <AsDrilledPanel
        holes={[]}
        asDrilled={[]}
        selectedHoleId="2-03"
        onSelectedHoleIdChange={vi.fn()}
        onRecord={vi.fn()}
        onDelete={vi.fn()}
        onCompare={vi.fn()}
        onImportMwd={vi.fn()}
        busy={false}
        result={result}
        showOverlay={false}
        onToggleOverlay={vi.fn()}
      />,
    );
    const tableRow = document.querySelector(".as-drilled-row");
    const cells = Array.from(tableRow?.querySelectorAll("b") ?? []).map((cell) => cell.textContent);
    expect(cells).toEqual(["0,20", "0,20", "—"]);
    const depthMetric = screen.getByText("Отклонение глубины").parentElement;
    expect(depthMetric?.querySelector("strong")?.textContent).toBe("—");
  });
});
