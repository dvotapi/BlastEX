// «Применить» вариант подбора раскладки (часть 4в): скважины, сеть и
// параметры сетки меняются одной правкой — один шаг «Отменить».
import { describe, expect, it } from "vitest";
import { emptyDesign, emptyHoleGeology, emptyNetwork, type Hole, type InitiationNetwork } from "../../types/design";
import { designReducer, initDesignState } from "./designReducer";

function hole(id: string, source: Hole["source"] = "generated"): Hole {
  return {
    id,
    row: 0,
    col: 0,
    collar: { x: 10, y: 5, z: 420 },
    toe: { x: 10, y: 5, z: 408 },
    diameter_mm: 152,
    subdrill_m: 1,
    kind: "production",
    source,
    enabled: true,
    ...emptyHoleGeology(),
  };
}

const VARIANT_NETWORK: InitiationNetwork = {
  ...emptyNetwork(),
  starters: ["n1"],
  connectors: [{ id: "c1", from_hole: "n1", to_hole: "n2", delay_ms: 42, kind: "surface" } as InitiationNetwork["connectors"][number]],
};

const VARIANT_PARAMS = { pattern: "square", spacing_a_m: 4.4, burden_b_m: 4.4, row_azimuth_deg: 30, front_rows_mode: "pair" };

describe("APPLY_LAYOUT", () => {
  it("заменяет скважины, сеть и параметры; один UNDO возвращает всё", () => {
    const before = {
      ...emptyDesign(),
      holes: [hole("a"), hole("m", "manual")],
      network: { ...emptyNetwork(), starters: ["a"] },
      pattern_params: { pattern: "square", spacing_a_m: 4, burden_b_m: 4, front_rows_tilt_count: 1 },
    };
    const start = initDesignState(before);

    const applied = designReducer(start, {
      type: "APPLY_LAYOUT",
      holes: [hole("n1"), hole("n2")],
      network: VARIANT_NETWORK,
      pattern_params: VARIANT_PARAMS,
    });

    expect(applied.present.holes.map((h) => h.id)).toEqual(["n1", "n2"]);
    expect(applied.present.network.starters).toEqual(["n1"]);
    expect(applied.present.network.connectors).toHaveLength(1);
    // Параметры заменяются целиком: ключа прежней схемы первого ряда нет.
    expect(applied.present.pattern_params).toEqual(VARIANT_PARAMS);
    expect(applied.past).toHaveLength(1);

    const undone = designReducer(applied, { type: "UNDO" });
    expect(undone.present).toBe(before);
    expect(undone.past).toHaveLength(0);
  });

  it("отмена возвращает параметры документа, а не формы", () => {
    // Скважины построены по параметрам документа: отмена возвращает именно их.
    const docParams = { spacing_a_m: 4 };
    const start = initDesignState({ ...emptyDesign(), pattern_params: docParams });

    const applied = designReducer(start, {
      type: "APPLY_LAYOUT",
      holes: [hole("n1")],
      network: emptyNetwork(),
      pattern_params: VARIANT_PARAMS,
    });
    // Сами объекты, а не копии: страница узнаёт по ним, что форму надо обновить.
    expect(applied.present.pattern_params).toBe(VARIANT_PARAMS);

    const undone = designReducer(applied, { type: "UNDO" });
    expect(undone.present.pattern_params).toBe(docParams);
    expect(undone.present.holes).toEqual([]);
    expect(designReducer(undone, { type: "REDO" }).present.pattern_params).toBe(VARIANT_PARAMS);
  });

  it("заряды и исполнение прежней раскладки сбрасываются", () => {
    const start = initDesignState({
      ...emptyDesign(),
      holes: [hole("a")],
      loads: [{ hole_id: "a" } as never],
    });

    const applied = designReducer(start, {
      type: "APPLY_LAYOUT",
      holes: [hole("n1")],
      network: emptyNetwork(),
      pattern_params: VARIANT_PARAMS,
    });

    expect(applied.present.loads).toEqual([]);
    expect(applied.present.as_drilled_holes).toEqual([]);
  });
});
