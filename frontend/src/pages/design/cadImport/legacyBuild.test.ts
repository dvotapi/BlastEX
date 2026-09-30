import { describe, expect, it } from "vitest";
import type { CadEntity } from "../../../types/cad";
import { benchCandidates, defaultBenchPair, withLineChains } from "./legacyBuild";

function line(handle: string, zs: number[], length: number, role: CadEntity["role"] = "situation"): CadEntity {
  return {
    handle,
    layer: "L",
    kind: "POLYLINE3D",
    geometry_type: "line",
    points: zs.map((z, index) => [index, 0, z]),
    closed: false,
    closed_by_gap: false,
    vertex_count: zs.length,
    length_m: length,
    area_m2: 0,
    z_kind: zs.every((z) => z === 0) ? "zero" : new Set(zs).size === 1 ? "const" : "variable",
    z_min: Math.min(...zs),
    z_max: Math.max(...zs),
    z_from_label: false,
    text: "",
    color: null,
    role,
    role_origin: "auto",
    role_override: false,
  };
}

describe("defaultBenchPair: пара линий для построения по-старому", () => {
  it("берёт самые длинные верхнюю и нижнюю бровки по ролям", () => {
    const pair = defaultBenchPair([
      line("t1", [420, 421], 30, "crest_top"),
      line("t2", [420, 421], 130, "crest_top"),
      line("b1", [410, 411], 100, "crest_bottom"),
      line("b2", [410, 411], 40, "crest_bottom"),
    ]);
    expect(pair).toEqual({ crest: "t2", toe: "b1" });
  });

  it("без ролей бровок — верх по средней Z, низ — самая длинная ниже", () => {
    expect(
      defaultBenchPair([line("a", [0, 0], 500), line("h", [420, 421], 100), line("l", [410, 411], 90), line("m", [415, 415], 20)]),
    ).toEqual({ crest: "h", toe: "l" });
  });

  it("служебные линии на Z = 0 не участвуют, одна линия — только верх", () => {
    expect(defaultBenchPair([line("a", [0, 0], 500), line("h", [420, 421], 100)])).toEqual({ crest: "h", toe: "" });
    expect(defaultBenchPair([])).toEqual({ crest: "", toe: "" });
  });
});

describe("benchCandidates: линии в списках «Верх» и «Низ»", () => {
  it("бровки по ролям, выбранные и сотня самых длинных — не все линии чертежа", () => {
    const lines = Array.from({ length: 300 }, (_, index) => line(`L${index}`, [400, 401], index));
    lines.push(line("crest", [420, 421], 0.5, "crest_top"));

    const candidates = benchCandidates(lines, ["L3"]).map((item) => item.handle);

    expect(candidates).toHaveLength(102);
    expect(candidates[0]).toBe("L299");
    expect(candidates).toContain("crest");
    expect(candidates).toContain("L3");
  });
});

function segment(handle: string, layer: string, a: [number, number, number], b: [number, number, number], role: CadEntity["role"]): CadEntity {
  return {
    ...line(handle, [a[2], b[2]], Math.hypot(b[0] - a[0], b[1] - a[1]), role),
    layer,
    kind: "LINE",
    points: [a, b],
  };
}

describe("withLineChains: бровка, начерченная отрезками LINE", () => {
  // Прежний диалог склеивал отрезки слоя в цепочки; построение по-старому берёт
  // одну линию, поэтому без склейки бровка из отрезков давала бы полоску.
  const crest = [
    segment("A", "верх", [0, 0, 420], [10, 0, 420.2], "crest_top"),
    segment("C", "верх", [20, 5, 420.6], [10, 0, 420.2], "crest_top"), // развёрнут
    segment("B", "верх", [20, 5, 420.6], [30, 5, 421], "crest_top"),
  ];
  const toe = [
    segment("D", "низ", [0, -10, 410], [15, -10, 410.4], "crest_bottom"),
    segment("E", "низ", [15, -10, 410.4], [30, -12, 410.8], "crest_bottom"),
  ];
  const stray = segment("F", "низ", [100, 100, 410], [110, 100, 410], "crest_bottom");

  it("склеивает связные отрезки слоя в одну линию с общей длиной и ролью", () => {
    const { entities, members } = withLineChains([...crest, ...toe, stray]);
    const chains = entities.filter((item) => members.has(item.handle));

    expect(chains).toHaveLength(2);
    const top = chains.find((item) => item.layer === "верх");
    expect(top?.points.map((point) => point[0])).toEqual([0, 10, 20, 30]);
    expect(top?.role).toBe("crest_top");
    expect(top?.length_m).toBeCloseTo(10 + Math.hypot(10, 5) + 10, 6);
    expect(members.get(top?.handle ?? "")).toEqual(["A", "C", "B"]);
    // Отрезки, вошедшие в цепочки, для построения заменены цепочками; несвязный остаётся.
    expect(entities.filter((item) => item.kind === "LINE" && !members.has(item.handle)).map((item) => item.handle)).toEqual(["F"]);
  });

  it("построение по-старому по умолчанию берёт цепочки бровок", () => {
    const { entities, members } = withLineChains([...crest, ...toe, stray]);
    const pair = defaultBenchPair(entities);

    expect(members.get(pair.crest)).toEqual(["A", "C", "B"]);
    expect(members.get(pair.toe)).toEqual(["D", "E"]);
    expect(benchCandidates(entities, []).map((item) => item.handle)).toContain(pair.crest);
  });
});

describe("withLineChains: роли и объём", () => {
  it("отрезки с разными ролями в одну цепочку не попадают", () => {
    // Отросток съёмки выключен вручную («Не использовать») — в бровку он не идёт.
    const parts = [
      segment("A", "верх", [0, 0, 420], [10, 0, 420.2], "crest_top"),
      segment("B", "верх", [10, 0, 420.2], [20, 0, 420.4], "crest_top"),
      segment("X", "верх", [20, 0, 420.4], [25, 8, 420.5], "ignore"),
    ];

    const { entities, members } = withLineChains(parts);
    const chains = entities.filter((item) => members.has(item.handle));

    expect(chains).toHaveLength(1);
    expect(members.get(chains[0].handle)).toEqual(["A", "B"]);
    expect(chains[0].role).toBe("crest_top");
  });

  it("тысячи отрезков одного слоя склеиваются быстро", () => {
    const count = 20_000;
    // Отрезки перемешаны: цепочка растёт с обоих концов.
    const parts = Array.from({ length: count }, (_, index) =>
      segment(`S${index}`, "съёмка", [index, 0, 400], [index + 1, 0, 400], "crest_top"),
    ).sort((a, b) => ((a.points[0][0] * 7919) % count) - ((b.points[0][0] * 7919) % count));

    const started = performance.now();
    const { entities, members } = withLineChains(parts);
    const elapsed = performance.now() - started;

    const chains = entities.filter((item) => members.has(item.handle));
    expect(chains).toHaveLength(1);
    expect(chains[0].points).toHaveLength(count + 1);
    expect(chains[0].points[0][0]).toBe(0);
    expect(elapsed).toBeLessThan(1000);
  });
});

describe("кандидаты «Верх/Низ» после склейки", () => {
  it("вместо тысяч фрагментов бровки — одна цепочка", () => {
    const parts = Array.from({ length: 3000 }, (_, index) =>
      segment(`S${index}`, "верх", [index, 0, 420], [index + 1, 0, 420], "crest_top"),
    );

    const { entities, members } = withLineChains(parts);
    const candidates = benchCandidates(entities, []);

    expect(candidates.map((item) => item.handle)).toEqual([...members.keys()]);
  });

  it("несвязных фрагментов бровок — не больше сотни самых длинных", () => {
    const parts = Array.from({ length: 3000 }, (_, index) =>
      segment(`S${index}`, "верх", [index * 10, 0, 420], [index * 10 + 1 + index / 1000, 0, 420], "crest_top"),
    );

    const { entities } = withLineChains(parts);
    const candidates = benchCandidates(entities, ["S5"]);

    expect(candidates.length).toBeLessThanOrEqual(101);
    expect(candidates[0].handle).toBe("S2999");
    expect(candidates.map((item) => item.handle)).toContain("S5");
  });
});
