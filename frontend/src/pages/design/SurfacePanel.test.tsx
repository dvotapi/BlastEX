// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SurfacePanel } from "./SurfacePanel";

afterEach(cleanup);

const LOCAL = { name: "local", epsg: null, origin_x: 0, origin_y: 0, origin_z: 0, units: "m", confirmed: false };

function renderPanel(holeCount: number, extra: Partial<Parameters<typeof SurfacePanel>[0]> = {}) {
  const props = {
    surfaces: { top: null, floor: null, face: null, post_blast: null },
    bench: { crest_z_m: 420, toe_z_m: 410, face_angle_deg: 75 },
    coordinateSystem: LOCAL,
    holeCount,
    onBenchChange: vi.fn(),
    onCoordinateSystemChange: vi.fn(),
    onImport: vi.fn(),
    onImportBlock: vi.fn(),
    onClear: vi.fn(),
    onOpenSources: vi.fn(),
    busy: false,
    ...extra,
  };
  render(<SurfacePanel {...props} />);
  return props;
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


describe("SurfacePanel: система координат и чертежи объекта (PR 4)", () => {
  it("система высот правится и видна в сводке", () => {
    const props = renderPanel(0, {
      coordinateSystem: { ...LOCAL, name: "МСК-66 зона 1", height_system: "Балтийская 1977", confirmed: true },
    });

    expect(screen.getByText("МСК-66 зона 1 · Балтийская 1977")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Система высот"), { target: { value: "БСВ" } });
    expect(props.onCoordinateSystemChange).toHaveBeenCalledWith({ height_system: "БСВ" });
  });

  it("«Чертежи объекта» открывают список загруженных файлов", () => {
    const props = renderPanel(0);

    fireEvent.click(screen.getByRole("button", { name: "Чертежи объекта" }));
    expect(props.onOpenSources).toHaveBeenCalled();
  });
});
