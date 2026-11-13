// Живая проверка сдвига скважин на плане (TASK-017, PR 1): клиентская ЛСП
// совпадает с серверной (`floor_burdens`) на общей фикстуре
// (`tests/test_live_lsp_fixture.py`), нарушения — по порогам `validate`.
import { describe, expect, it } from "vitest";
import type { BlockContour, Hole, PatternParams, ToeLine } from "../../types/design";
import { liveCheck, liveFloorBurdens } from "./liveChecks";
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

describe("liveCheck — нарушения сдвига", () => {
  const plain = byName("plain");
  const pair = byName("pair");
  const params = plain.pattern_params;
  const hole = (holes: Hole[], id: string) => holes.find((h) => h.id === id)!;

  it("скважина первого ряда, отодвинутая вглубь, — ЛСП больше W", () => {
    const moved = byName("plain_moved");
    const result = liveCheck({
      holes: moved.holes,
      base: plain.holes,
      moved: new Set(["5-01"]),
      contour,
      toeLine: plain.toe_line,
      params,
    });
    expect(result.byHole["5-01"].map((v) => v.code)).toContain("floor_burden_excess");
    expect(result.burdens["5-01"].excess).toBe(true);
    expect(result.byHole["5-01"][0].text).toBe("ЛСП 4,68 м больше допустимого 4,12 м (W + 3 %)");
  });

  it("на месте — нарушений нет, расстояние до соседа — шаг", () => {
    const result = liveCheck({ holes: plain.holes, base: plain.holes, moved: new Set(["5-02"]), contour, toeLine: plain.toe_line, params });
    expect(result.byHole).toEqual({});
    expect(result.nearestM).toBeCloseTo(4, 2);
  });

  it("сосед ближе 0,5·min(a, b)", () => {
    const a = hole(plain.holes, "5-02");
    const b = hole(plain.holes, "5-03");
    const holes = shifted(plain.holes, "5-02", (b.collar.x - a.collar.x) * 0.6, (b.collar.y - a.collar.y) * 0.6);
    const result = liveCheck({ holes, base: plain.holes, moved: new Set(["5-02"]), contour, toeLine: plain.toe_line, params });
    expect(result.byHole["5-02"].map((v) => v.code)).toEqual(["neighbour_too_close"]);
    expect(result.nearestM).toBeCloseTo(1.6, 2);
  });

  it("пара у откоса своей вертикальной соседом не считается", () => {
    const result = liveCheck({
      holes: pair.holes,
      base: pair.holes,
      moved: new Set(["4-01", "4-01T"]),
      contour,
      toeLine: pair.toe_line,
      params: pair.pattern_params,
    });
    expect(result.byHole["4-01"] ?? []).toEqual([]);
    expect(result.nearestM).toBeGreaterThan(2);
  });

  it("устье ближе min_crest_offset_m к кромке и вне контура", () => {
    const first = hole(plain.holes, "5-01");
    // Кромка — сторона v0→v1 по азимуту 30°; «к откосу» — (−cos 30°, sin 30°).
    const toFace = { x: -Math.cos(Math.PI / 6), y: Math.sin(Math.PI / 6) };
    const crestOffset = 1.0; // offset_from_face_m фикстуры
    const near = shifted(plain.holes, "5-01", toFace.x * (crestOffset - 0.1), toFace.y * (crestOffset - 0.1));
    const nearResult = liveCheck({ holes: near, base: plain.holes, moved: new Set(["5-01"]), contour, toeLine: plain.toe_line, params });
    expect(nearResult.byHole["5-01"].map((v) => v.code)).toEqual(["collar_too_close_to_crest"]);
    expect(nearResult.byHole["5-01"][0].text).toBe("Устье ближе 0,3 м к кромке уступа");

    const out = shifted(plain.holes, "5-01", toFace.x * (crestOffset + 0.5), toFace.y * (crestOffset + 0.5));
    const outResult = liveCheck({ holes: out, base: plain.holes, moved: new Set(["5-01"]), contour, toeLine: plain.toe_line, params });
    expect(outResult.byHole["5-01"].map((v) => v.code)).toContain("hole_outside_contour");
    expect(first.enabled).toBe(true);
  });

  it("у остальных подсвечивается только превышение ЛСП, появившееся от сдвига", () => {
    // До сдвига превышение было только у 1-01; после — и у 5-01T.
    const after = byName("pair_moved");
    const result = liveCheck({
      holes: after.holes,
      base: pair.holes,
      moved: new Set(["3-02"]),
      contour,
      toeLine: pair.toe_line,
      params: pair.pattern_params,
    });
    expect(result.byHole["5-01T"].map((v) => v.code)).toEqual(["floor_burden_excess"]);
    expect(result.byHole["1-01"]).toBeUndefined();
  });
});
