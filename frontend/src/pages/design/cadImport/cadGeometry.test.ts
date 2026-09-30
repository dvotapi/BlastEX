import { describe, expect, it } from "vitest";
import type { CadEntity } from "../../../types/cad";
import { drawingBounds, entitiesByLayer, fragmentsLabel, linePath, pointsPath } from "./cadGeometry";

function entity(handle: string, layer: string, points: CadEntity["points"], extra: Partial<CadEntity> = {}): CadEntity {
  return {
    handle,
    layer,
    kind: "POLYLINE3D",
    geometry_type: "line",
    points,
    closed: false,
    closed_by_gap: false,
    vertex_count: points.length,
    length_m: 0,
    area_m2: 0,
    z_kind: "variable",
    z_min: Math.min(...points.map((p) => p[2])),
    z_max: Math.max(...points.map((p) => p[2])),
    z_from_label: false,
    text: "",
    color: null,
    role: "situation",
    role_origin: "auto",
    ...extra,
  };
}

const CAMERA = { x: 2_345_880, y: 711_770, scale: 2 };
const VIEWPORT = { width: 200, height: 100 };

describe("cadGeometry", () => {
  it("габариты чертежа по всем точкам, подписи не в счёт", () => {
    const bounds = drawingBounds([
      entity("a", "L", [[2_345_836.5, 711_678.3, 410], [2_345_921, 711_865.1, 411]]),
      entity("t", "L", [[0, 0, 0]], { geometry_type: "text", kind: "TEXT" }),
    ]);
    expect(bounds).toEqual({ minX: 2_345_836.5, minY: 711_678.3, maxX: 2_345_921, maxY: 711_865.1 });
    expect(drawingBounds([])).toBeNull();
  });

  it("путь линии в экранных координатах, замкнутая — с Z", () => {
    const open = linePath([[2_345_880, 711_770, 0], [2_345_890, 711_775, 0]], false, CAMERA, VIEWPORT);
    expect(open).toBe("M100.0 50.0L120.0 40.0");
    const closed = linePath([[2_345_880, 711_770, 0], [2_345_890, 711_770, 0], [2_345_890, 711_780, 0]], true, CAMERA, VIEWPORT);
    expect(closed.endsWith("Z")).toBe(true);
  });

  it("точки слоя — одним путём из кружков", () => {
    const path = pointsPath([[2_345_880, 711_770, 410], [2_345_885, 711_770, 411]], CAMERA, VIEWPORT, 2);
    expect(path.match(/M/g)).toHaveLength(2);
    expect(path.startsWith("M98.0 50.0a2 2 0 1 0 4 0")).toBe(true);
  });

  it("сущности раскладываются по слоям в порядке слоёв", () => {
    const grouped = entitiesByLayer([entity("a", "B", [[0, 0, 0], [1, 1, 1]]), entity("b", "A", [[0, 0, 0], [1, 1, 1]]), entity("c", "B", [[0, 0, 0], [1, 1, 1]])]);
    expect([...grouped.keys()]).toEqual(["B", "A"]);
    expect(grouped.get("B")?.map((item) => item.handle)).toEqual(["a", "c"]);
  });

  it("фрагменты со склонением", () => {
    expect(fragmentsLabel(1)).toBe("1 линия");
    expect(fragmentsLabel(23)).toBe("23 фрагмента");
    expect(fragmentsLabel(25)).toBe("25 фрагментов");
  });
});
