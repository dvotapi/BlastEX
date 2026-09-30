// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SurfacePanel } from "./SurfacePanel";

afterEach(cleanup);

function renderPanel(holeCount: number) {
  render(
    <SurfacePanel
      surfaces={{ top: null, floor: null, face: null, post_blast: null }}
      bench={{ crest_z_m: 420, toe_z_m: 410, face_angle_deg: 75 }}
      coordinateSystem={{ name: "local", epsg: null, origin_x: 0, origin_y: 0, origin_z: 0, units: "m", confirmed: false }}
      holeCount={holeCount}
      onBenchChange={vi.fn()}
      onCoordinateSystemChange={vi.fn()}
      onImport={vi.fn()}
      onImportBlock={vi.fn()}
      onClear={vi.fn()}
      busy={false}
    />,
  );
}

describe("SurfacePanel: импорт чертежа", () => {
  it("предупреждает, что скважины очистит построение, а не загрузка", () => {
    renderPanel(12);

    expect(screen.getByText(/«Построить блок» заменит контур и очистит 12 скв\./)).toBeTruthy();
  });

  it("на пустом паспорте предупреждения нет", () => {
    renderPanel(0);

    expect(screen.queryByText(/заменит контур/)).toBeNull();
  });
});
