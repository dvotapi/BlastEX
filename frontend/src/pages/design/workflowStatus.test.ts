// Подпись источника объёма в строке показателей.
import { describe, expect, it } from "vitest";
import { emptyCoordinateSystem, emptySurfaces, type SurfaceModel } from "../../types/design";
import { volumeSourceLabel } from "./workflowStatus";

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
