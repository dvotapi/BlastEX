// @vitest-environment jsdom
// Строка показателей (TASK-013, PR 3): объём блока из пересчёта и подробности
// по наведению — S верх, S низ, S ср, S ср × H, объём с карты и расхождение.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { CadContourInfo, SurfaceModel } from "../../types/design";
import { SummaryPanel, volumeDetails } from "./SummaryPanel";

afterEach(cleanup);

const CAD: CadContourInfo = {
  source_id: "src-1",
  file_name: "блок 66.dwg",
  method: "ready",
  items: [],
  top: [],
  bottom: [[0, 0], [1, 0], [1, 1]],
  area_top_m2: 2789.93,
  area_bottom_m2: 4120.92,
  area_mean_m2: 3455.42,
  map_area_m2: 2772.49,
  area_basis: "mean",
  area_m2: 3455.42,
  built_at: "",
  edited: false,
  map_volume_m3: 28279.39,
};

const ROOF = { tin: { vertices: [], triangles: [[0, 1, 2]] }, cad: { plane: false } } as unknown as SurfaceModel;

describe("volumeDetails", () => {
  it("площади, S ср × H, объём с карты и расхождение", () => {
    const text = volumeDetails(CAD, 10.51, 36939, ROOF);

    expect(text).toContain("S верх 2789,9 м² · S низ 4120,9 м² · S ср 3455,4 м²");
    expect(text).toContain("S ср × H = 3455,4 × 10,51 = 36316 м³");
    expect(text).toContain("Объём с карты 28279 м³: расхождение +30,6 %");
    expect(text).toContain("в контуре по нижней бровке");
  });

  it("контур правили или кровли нет — объём в контуре паспорта; без чертежа подробностей нет", () => {
    expect(volumeDetails({ ...CAD, edited: true }, 10, 30000, ROOF)).toContain("в контуре паспорта");
    expect(volumeDetails(CAD, 10, 30000, null)).toContain("в контуре паспорта");
    expect(volumeDetails({ ...CAD, bottom: null }, 10, 30000, ROOF)).toContain("нижнего контура нет");
    expect(volumeDetails(null, 10, 30000, ROOF)).toBeNull();
  });

  it("кровля-плоскость — объём S ср × H", () => {
    const plane = { tin: { vertices: [], triangles: [[0, 1, 2]] }, cad: { plane: true } } as unknown as SurfaceModel;

    expect(volumeDetails(CAD, 10, 34554, plane)).toContain("Объём — S ср × H: кровля — плоскость");
  });
});

describe("SummaryPanel", () => {
  it("объём блока с подробностями по наведению", () => {
    render(
      <SummaryPanel holes={[]} blockVolumeM3={36939} holesSource="—" volumeSource="по чертежу" volumeTitle="подробности" />,
    );

    const cell = screen.getByText("36939 м³").closest("div") as HTMLElement;
    expect(cell.title).toBe("подробности");
  });
});

describe("SummaryPanel: пересчёт скважин", () => {
  it("ошибка пересчёта видна в строке показателей", () => {
    render(
      <SummaryPanel holes={[]} blockVolumeM3={null} holesSource="—" volumeSource="—" recomputeError="Нет связи с сервером." />,
    );

    expect(screen.getByRole("alert").textContent).toContain("Устья и длины не пересчитаны: Нет связи с сервером.");
  });

  it("заметка после пересчёта видна", () => {
    render(<SummaryPanel holes={[]} blockVolumeM3={1} holesSource="—" volumeSource="—" recomputeNotice="Пересчитано: 3 скважины." />);

    expect(screen.getByRole("status").textContent).toContain("Пересчитано: 3 скважины.");
  });
});
