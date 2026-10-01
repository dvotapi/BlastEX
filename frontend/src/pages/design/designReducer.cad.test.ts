// Контур из чертежа в паспорте (TASK-013, PR 2): одно построение — один шаг
// отмены; ручная правка вершин в плане помечает контур «правился».
import { describe, expect, it } from "vitest";
import { emptyDesign, type BlastDesign, type CadContourInfo, type Hole } from "../../types/design";
import { designReducer, initDesignState } from "./designReducer";

const CAD: CadContourInfo = {
  source_id: "src-1",
  file_name: "блок 66.dwg",
  method: "ready",
  items: [{ kind: "part", handle: "769", start_m: 0, end_m: 341.08, points: [], flip: false, label: "" }],
  top: [
    [0, 0],
    [40, 0],
    [40, 20],
  ],
  bottom: [
    [0, 0],
    [44, 0],
    [44, 20],
  ],
  area_top_m2: 800,
  area_bottom_m2: 880,
  area_mean_m2: 840,
  map_area_m2: null,
  built_at: "2026-10-01T10:00:00Z",
  edited: false,
};

const VERTICES = [
  { x: 0, y: 0, z: 420 },
  { x: 40, y: 0, z: 420 },
  { x: 40, y: 20, z: 420 },
];

function withHole(): BlastDesign {
  const design = emptyDesign();
  return { ...design, holes: [{ id: "h1" } as Hole] };
}

describe("APPLY_CAD_CONTOUR", () => {
  it("ставит контур, откосы, отметки уступа и данные чертежа, очищает скважины — одним шагом", () => {
    const start = initDesignState(withHole());
    const built = designReducer(start, {
      type: "APPLY_CAD_CONTOUR",
      vertices: VERTICES,
      free_faces: [[1, 2]],
      bench: { crest_z_m: 420, toe_z_m: 410 },
      cad: CAD,
    });

    expect(built.present.contour.vertices).toEqual(VERTICES);
    expect(built.present.contour.free_faces).toEqual([[1, 2]]);
    expect(built.present.contour.bench).toMatchObject({ crest_z_m: 420, toe_z_m: 410 });
    expect(built.present.contour.cad).toEqual(CAD);
    expect(built.present.holes).toEqual([]);

    const undone = designReducer(built, { type: "UNDO" });
    expect(undone.present.holes).toHaveLength(1);
    expect(undone.present.contour.cad ?? null).toBeNull();
  });
});

describe("ручная правка контура из чертежа", () => {
  const built = designReducer(initDesignState(emptyDesign()), {
    type: "APPLY_CAD_CONTOUR",
    vertices: VERTICES,
    free_faces: [],
    bench: {},
    cad: CAD,
  });

  it("сдвиг вершины в плане помечает контур «правился»", () => {
    const moved = designReducer(built, {
      type: "SET_CONTOUR_VERTICES",
      vertices: [VERTICES[0], { x: 41, y: 0, z: 420 }, VERTICES[2]],
    });
    expect(moved.present.contour.cad?.edited).toBe(true);
  });

  it("смена одних отметок (драпировка по поверхности) — нет", () => {
    const draped = designReducer(built, {
      type: "SET_CONTOUR_VERTICES",
      vertices: VERTICES.map((vertex) => ({ ...vertex, z: 421 })),
    });
    expect(draped.present.contour.cad?.edited).toBe(false);
  });
});

it("старый паспорт без данных чертежа загружается с cad = null", () => {
  const loaded = designReducer(initDesignState(emptyDesign()), { type: "LOAD", design: emptyDesign() });
  expect(loaded.present.contour.cad).toBeNull();
});
