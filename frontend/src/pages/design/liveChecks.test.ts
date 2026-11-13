// Живая проверка сдвига скважин на плане (TASK-017, PR 1): клиентская ЛСП
// совпадает с серверной (`floor_burdens`) на общей фикстуре
// (`tests/test_live_lsp_fixture.py`), нарушения — по порогам `validate`.
import { describe, expect, it } from "vitest";
import type { BlockContour, Hole, PatternParams, ToeLine } from "../../types/design";
import { floorBase, floorBurdensAfterMove, liveCheck, liveFloorBurdens } from "./liveChecks";
import fixture from "./testing/liveLspFixture.json";

type Case = {
  name: string;
  pattern_params: Partial<PatternParams>;
  holes: Hole[];
  toe_line: ToeLine;
  allowed_m: number;
  expected: Record<string, { value_m: number; excess: boolean }>;
};

const contour = fixture.contour as unknown as BlockContour;
const cases = fixture.cases as unknown as Case[];

function byName(name: string): Case {
  const found = cases.find((item) => item.name === name);
  if (!found) throw new Error(name);
  return found;
}

function shifted(holes: Hole[], id: string, dx: number, dy: number): Hole[] {
  return holes.map((h) =>
    h.id === id
      ? {
          ...h,
          collar: { ...h.collar, x: h.collar.x + dx, y: h.collar.y + dy },
          toe: { ...h.toe, x: h.toe.x + dx, y: h.toe.y + dy },
        }
      : h,
  );
}

describe("liveFloorBurdens — как floor_burdens сервера", () => {
  for (const item of cases) {
    it(`фикстура «${item.name}»`, () => {
      const burdens = liveFloorBurdens(item.holes, item.toe_line, item.pattern_params);
      expect(Object.keys(burdens).sort()).toEqual(Object.keys(item.expected).sort());
      for (const [id, expected] of Object.entries(item.expected)) {
        // Линия подошвы приходит на фронт округлённой до миллиметра.
        expect(Math.abs(burdens[id].valueM - expected.value_m)).toBeLessThan(2e-3);
        expect(burdens[id].excess).toBe(expected.excess);
        expect(burdens[id].allowedM).toBeCloseTo(item.allowed_m, 9);
      }
    });
  }

  it("без линии подошвы или без W — ЛСП не меряется / не превышает", () => {
    const item = byName("plain");
    expect(liveFloorBurdens(item.holes, null, item.pattern_params)).toEqual({});
    const noW = liveFloorBurdens(item.holes, item.toe_line, { pattern: "rectangular" });
    expect(Object.values(noW).every((b) => b.allowedM === null && !b.excess)).toBe(true);
  });
});

describe("ЛСП после сдвига без полного перебора", () => {
  it("совпадает с полным расчётом по сдвинутым скважинам", () => {
    for (const item of [byName("plain"), byName("pair")]) {
      const base = floorBase(item.holes, item.toe_line, item.pattern_params);
      const deltas = [{ x: 1.3, y: -0.7 }, { x: -2.5, y: 1.1 }, { x: 4, y: -6 }, { x: 0.2, y: 0.4 }];
      item.holes.forEach((h, k) => {
        const moved = new Set([h.id, `${h.id}T`]);
        const delta = deltas[k % deltas.length];
        const preview = item.holes.map((x) => (moved.has(x.id) ? shifted([x], x.id, delta.x, delta.y)[0] : x));
        const fast = floorBurdensAfterMove(base, moved, delta);
        const full = liveFloorBurdens(preview, item.toe_line, item.pattern_params);
        expect(Object.keys(fast).sort()).toEqual(Object.keys(full).sort());
        for (const id of Object.keys(full)) expect(fast[id].valueM).toBeCloseTo(full[id].valueM, 9);
      });
    }
  });
});

describe("liveCheck — нарушения сдвига", () => {
  const plain = byName("plain");
  const pair = byName("pair");
  const params = plain.pattern_params;
  const hole = (holes: Hole[], id: string) => holes.find((h) => h.id === id)!;
  const check = (item: Case, moved: string[], delta: { x: number; y: number }) =>
    liveCheck({ base: item.holes, moved: new Set(moved), delta, contour, toeLine: item.toe_line, params: item.pattern_params });
  const deltaTo = (from: Case, to: Case, id: string) => {
    const a = hole(from.holes, id).collar;
    const b = hole(to.holes, id).collar;
    return { x: b.x - a.x, y: b.y - a.y };
  };

  it("скважина первого ряда, отодвинутая вглубь, — ЛСП больше W", () => {
    const result = check(plain, ["5-01"], deltaTo(plain, byName("plain_moved"), "5-01"));
    expect(result.byHole["5-01"].map((v) => v.code)).toContain("floor_burden_excess");
    expect(result.burdens["5-01"].excess).toBe(true);
    expect(result.byHole["5-01"][0].text).toBe("ЛСП 4,68 м больше допустимого 4,12 м (W + 3 %)");
  });

  it("на месте — нарушений нет, расстояние до соседа — шаг", () => {
    const result = check(plain, ["5-02"], { x: 0, y: 0 });
    expect(result.byHole).toEqual({});
    expect(result.nearestM).toBeCloseTo(4, 2);
  });

  it("сосед ближе 0,5·min(a, b)", () => {
    const a = hole(plain.holes, "5-02");
    const b = hole(plain.holes, "5-03");
    const result = check(plain, ["5-02"], { x: (b.collar.x - a.collar.x) * 0.6, y: (b.collar.y - a.collar.y) * 0.6 });
    expect(result.byHole["5-02"].map((v) => v.code)).toEqual(["neighbour_too_close"]);
    expect(result.nearestM).toBeCloseTo(1.6, 2);
  });

  it("пара у откоса своей вертикальной соседом не считается", () => {
    const result = check(pair, ["4-01", "4-01T"], { x: 0, y: 0 });
    expect(result.byHole["4-01"] ?? []).toEqual([]);
    expect(result.nearestM).toBeGreaterThan(2);
  });

  it("устье ближе min_crest_offset_m к кромке и вне контура", () => {
    // Кромка — сторона v0→v1 по азимуту 30°; «к откосу» — (−cos 30°, sin 30°).
    const toFace = { x: -Math.cos(Math.PI / 6), y: Math.sin(Math.PI / 6) };
    const crestOffset = 1.0; // offset_from_face_m фикстуры
    const near = check(plain, ["5-01"], { x: toFace.x * (crestOffset - 0.1), y: toFace.y * (crestOffset - 0.1) });
    expect(near.byHole["5-01"].map((v) => v.code)).toEqual(["collar_too_close_to_crest"]);
    expect(near.byHole["5-01"][0].text).toBe("Устье ближе 0,3 м к кромке уступа");

    const out = check(plain, ["5-01"], { x: toFace.x * (crestOffset + 0.5), y: toFace.y * (crestOffset + 0.5) });
    expect(out.byHole["5-01"].map((v) => v.code)).toContain("hole_outside_contour");
  });

  it("у остальных подсвечивается только превышение ЛСП, появившееся от сдвига", () => {
    // 2-01 уводим вглубь — соседку 1-01 (до сдвига её закрывала 2-01) больше
    // никто не закрывает, и у неё появляется ЛСП больше W.
    const deep = { x: Math.cos(Math.PI / 6) * 10, y: -Math.sin(Math.PI / 6) * 10 };
    const result = check(plain, ["2-01"], deep);
    expect(byName("plain").expected["1-01"]).toBeUndefined();
    expect(result.byHole["1-01"].map((v) => v.code)).toEqual(["floor_burden_excess"]);
    // У несдвинутых без нового превышения подсветки нет.
    expect(result.byHole["3-01"]).toBeUndefined();
  });
});
