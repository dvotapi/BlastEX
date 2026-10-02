// Пересчёт скважин по кровле и подошве (TASK-013, PR 3): ответ сервера
// применяется вне истории отмены — отмена правки сама вызывает пересчёт.
import { describe, expect, it } from "vitest";
import { emptyDesign, emptyHoleGeology, type Hole } from "../../types/design";
import { designReducer, initDesignState } from "./designReducer";

function hole(id: string, z: number, length: number, extra: Partial<Hole> = {}): Hole {
  return {
    id,
    row: 0,
    col: 0,
    collar: { x: 10, y: 5, z },
    toe: { x: 10, y: 5, z: z - length },
    diameter_mm: 152,
    subdrill_m: 1,
    kind: "production",
    source: "generated",
    enabled: true,
    ...emptyHoleGeology(),
    ...extra,
  };
}

const INTERVAL = { from_m: 0, to_m: 5, domain_id: "d", domain_name: "Порода", role: "designed", notes: "" } as unknown as Hole["intervals"][number];

describe("RECOMPUTE_HOLES", () => {
  it("ставит новые устья и забои без шага истории", () => {
    const start = initDesignState({ ...emptyDesign(), holes: [hole("a", 420, 12, { intervals: [INTERVAL] }), hole("b", 420, 12)] });

    const next = designReducer(start, { type: "RECOMPUTE_HOLES", holes: [hole("a", 420.1, 11.1), hole("b", 420, 12)] });

    expect(next.past).toHaveLength(0);
    expect(next.present.holes[0].collar.z).toBe(420.1);
    expect(next.present.holes[0].toe.z).toBeCloseTo(409);
    // Геология посчитана для старой оси — сбрасывается, как при сдвиге скважины.
    expect(next.present.holes[0].intervals).toEqual([]);
    expect(next.present.holes[1]).toBe(start.present.holes[1]);
  });

  it("ничего не сменилось — тот же документ", () => {
    const start = initDesignState({ ...emptyDesign(), holes: [hole("a", 420, 12)] });

    expect(designReducer(start, { type: "RECOMPUTE_HOLES", holes: [hole("a", 420, 12)] })).toBe(start);
  });

  it("правит только геометрию: прочие поля скважины и скважины не из ответа остаются", () => {
    const start = initDesignState({ ...emptyDesign(), holes: [hole("a", 420, 12, { diameter_mm: 165 }), hole("c", 420, 12)] });

    const next = designReducer(start, { type: "RECOMPUTE_HOLES", holes: [hole("a", 421, 12)] });

    expect(next.present.holes[0].diameter_mm).toBe(165);
    expect(next.present.holes[1]).toBe(start.present.holes[1]);
  });

  it("отмена после пересчёта возвращает состояние до правки", () => {
    let state = initDesignState({ ...emptyDesign(), holes: [hole("a", 420, 12)] });
    state = designReducer(state, { type: "SET_BENCH", bench: { toe_z_m: 409 } });
    state = designReducer(state, { type: "RECOMPUTE_HOLES", holes: [hole("a", 420, 13)] });

    const undone = designReducer(state, { type: "UNDO" });

    expect(undone.present.holes[0].toe.z).toBe(408);
    expect(undone.present.contour.bench.toe_z_m).toBe(-10);
  });
});

describe("MOVE_HOLES и ручная отметка устья", () => {
  it("сдвиг скважины с ручной Z устья её не затирает", () => {
    const roof = {
      kind: "top" as const,
      name: "Кровля",
      source_format: "cad",
      source_name: "",
      created_at: "",
      coordinate_system: emptyDesign().coordinate_system,
      points: [],
      polylines: [],
      tin: {
        vertices: [{ x: 0, y: 0, z: 420 }, { x: 100, y: 0, z: 420 }, { x: 100, y: 100, z: 420 }, { x: 0, y: 100, z: 420 }],
        triangles: [[0, 1, 2], [0, 2, 3]],
      },
    };
    const base = emptyDesign();
    const start = initDesignState({
      ...base,
      surfaces: { ...base.surfaces, top: roof },
      holes: [hole("a", 425, 12, { manual: ["collar_z"] }), hole("b", 425, 12)],
    });

    const moved = designReducer(start, { type: "MOVE_HOLES", ids: ["a", "b"], dx: 1, dy: 0 });

    // Без ручной пометки устье ложится на кровлю — проверка, что кровля работает.
    expect(moved.present.holes[1].collar.z).toBeCloseTo(420, 9);

    expect(moved.present.holes[0].collar).toEqual({ x: 11, y: 5, z: 425 });
    expect(moved.present.holes[0].toe.z).toBe(413);
  });
});
