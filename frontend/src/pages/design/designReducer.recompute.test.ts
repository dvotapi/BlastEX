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
