// Подпись источника объёма в строке показателей.
import { describe, expect, it } from "vitest";
import { emptyCoordinateSystem, emptySurfaces, type SurfaceModel } from "../../types/design";
import { isCrsUnconfirmed, volumeSourceLabel } from "./workflowStatus";

function top(source_format: string): SurfaceModel {
  return {
    kind: "top",
    name: "Кровля",
    source_format,
    source_name: "",
    created_at: "",
    coordinate_system: emptyCoordinateSystem(),
    points: [],
    polylines: [],
    tin: { vertices: [], triangles: [] },
  };
}

describe("volumeSourceLabel", () => {
  it("кровля из чертежа маркшейдера — «по чертежу» (TASK-013, PR 3)", () => {
    expect(volumeSourceLabel({ ...emptySurfaces(), top: top("cad") }, true)).toBe("по чертежу");
  });

  it("без поверхностей — проектное, без контура — нет данных", () => {
    expect(volumeSourceLabel(emptySurfaces(), true)).toBe("проектное");
    expect(volumeSourceLabel(emptySurfaces(), false)).toBe("нет данных");
    expect(volumeSourceLabel({ ...emptySurfaces(), top: top("dxf") }, true)).toBe("из DXF");
  });
});


describe("isCrsUnconfirmed (TASK-013, PR 4)", () => {
  const cs = emptyCoordinateSystem();

  it("именованная местная СК без EPSG — полноценная, предупреждения нет", () => {
    expect(isCrsUnconfirmed({ ...cs, name: "МСК-66 зона 1", height_system: "Балтийская 1977" }, true)).toBe(false);
    expect(isCrsUnconfirmed({ ...cs, name: "Карьерная сетка" }, true)).toBe(false);
  });

  it("«local» или пустое имя с геометрией — предупреждение, пока не подтверждено", () => {
    expect(isCrsUnconfirmed(cs, true)).toBe(true);
    expect(isCrsUnconfirmed({ ...cs, name: "  " }, true)).toBe(true);
    expect(isCrsUnconfirmed({ ...cs, confirmed: true }, true)).toBe(false);
    expect(isCrsUnconfirmed({ ...cs, epsg: 32641 }, true)).toBe(false);
  });

  it("без геометрии — никогда", () => {
    expect(isCrsUnconfirmed(cs, false)).toBe(false);
  });
});
