import { describe, expect, it } from "vitest";
import type { CadEntity } from "../../../types/cad";
import { defaultBenchPair } from "./legacyBuild";

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
