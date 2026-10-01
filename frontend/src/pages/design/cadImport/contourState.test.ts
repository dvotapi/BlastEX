// Состояние шага «Контур»: способ по умолчанию, запрос предпросмотра,
// щелчки инструментов сборки и блока по бровке (TASK-013, PR 2).
import { describe, expect, it } from "vitest";
import type { CadContourLines, CadContourResult, CadEntity } from "../../../types/cad";
import {
  applyPick,
  asAssembly,
  contourRequest,
  flipItem,
  initialContour,
  readyCandidates,
  removeItem,
  undoItem,
  type ContourState,
} from "./contourState";
import { cadEntity, cadSource } from "./testing/fixtures";

const SOURCE = cadSource();
const ENTITIES = new Map(SOURCE.entities.map((entity) => [entity.handle, entity]));
const LINES: CadContourLines = {
  splits: { "6C3": [10] },
  intersections: [],
  crests_top: [{ points: [[100, 200, 420], [130, 205, 421]], parts: [{ handle: "6C3", reversed: false, length_m: 30.4, chain_start_m: 0 }], length_m: 30.4 }],
  crests_bottom: [],
  gaps: [],
};
const CTX = { entities: ENTITIES, lines: LINES };

function state(patch: Partial<ContourState> = {}): ContourState {
  return { ...initialContour(SOURCE), ...patch };
}

describe("способ по умолчанию", () => {
  it("готовый контур блока, если он есть в чертеже", () => {
    expect(initialContour(SOURCE)).toMatchObject({ method: "ready", handle: "769" });
  });

  it("без контура блока — сборка", () => {
    const source = cadSource({ entities: SOURCE.entities.filter((entity) => entity.role !== "block_contour") });
    expect(initialContour(source)).toMatchObject({ method: "assembly", handle: "" });
  });

  it("в списке готовых — и линия с разрывом концов в пределах допуска", () => {
    const gap = cadEntity("GAP", "Проект", { points: [[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0], [0, 0.8, 0]] });
    expect(readyCandidates([gap], 0.5).map((entity) => entity.handle)).toEqual([]);
    expect(readyCandidates([gap], 1).map((entity) => entity.handle)).toEqual(["GAP"]);
  });

  it("в списке готовых сначала контуры блока, затем по площади", () => {
    const triangle: CadEntity["points"] = [[0, 0, 0], [10, 0, 0], [10, 10, 0]];
    const big = cadEntity("BIG", "Ситуация", { closed: true, area_m2: 9000, points: triangle });
    const contour = cadEntity("C", "блок", { closed: true, area_m2: 100, role: "block_contour", points: triangle });
    expect(readyCandidates([big, contour, cadEntity("OPEN", "x")]).map((entity) => entity.handle)).toEqual(["C", "BIG"]);
  });
});

describe("запрос предпросмотра", () => {
  it("готовый — по handle с допуском", () => {
    expect(contourRequest(state(), 4)).toEqual({ method: "ready", handle: "769", tolerance_m: 0.5 });
  });

  it("щелчок внутри — только после щелчка, с ролями и мостом", () => {
    expect(contourRequest(state({ method: "click" }), 4)).toBeNull();
    expect(contourRequest(state({ method: "click", point: [5, 6], bridge: "3,5" }), 4)).toEqual({
      method: "click",
      point: [5, 6],
      roles: ["block_contour", "design_line", "crest_top"],
      tolerance_m: 0.5,
      bridge_m: 3.5,
    });
  });

  it("блок по бровке — ширина рядами × W", () => {
    const crest = state({ method: "crest", crestStart: [0, 0], crestEnd: [40, 0], widthMode: "rows", rows: "5" });
    expect(contourRequest(crest, 4)).toMatchObject({ crest: { start: [0, 0], end: [40, 0], width_m: 20, side: "auto" } });
    expect(contourRequest({ ...crest, crestEnd: null }, 4)).toBeNull();
    expect(contourRequest({ ...crest, widthMode: "meters", width: "" }, 4)).toBeNull();
  });

  it("пустая сборка не запрашивается", () => {
    expect(contourRequest(state({ method: "assembly", items: [] }), 4)).toBeNull();
  });
});

describe("щелчки сборки", () => {
  const assembly = state({ method: "assembly", items: [] });

  it("«Участок» берёт кусок линии между разрезами", () => {
    const next = applyPick(assembly, { world: [120, 203], snap: null, handle: "6C3" }, CTX);
    expect(next.items).toHaveLength(1);
    expect(next.items[0]).toMatchObject({ kind: "part", handle: "6C3", start_m: 10 });
    expect(next.items[0].end_m).toBeCloseTo(Math.hypot(30, 5));
    expect(next.selected).toBe(0);
  });

  it("«По точкам» — два щелчка на одной линии", () => {
    const first = applyPick({ ...assembly, tool: "points" }, { world: [100, 200], snap: null, handle: "6C3" }, CTX);
    expect(first.items).toHaveLength(0);
    expect(first.pending).toMatchObject({ handle: "6C3" });
    const second = applyPick(first, { world: [115, 202.5], snap: null, handle: "6C3" }, CTX);
    expect(second.items[0]).toMatchObject({ kind: "part", handle: "6C3", start_m: 0 });
    expect(second.items[0].end_m).toBeCloseTo(Math.hypot(15, 2.5));
    expect(second.pending).toBeNull();
  });

  it("«Отрезок» — две точки с привязкой", () => {
    const first = applyPick({ ...assembly, tool: "segment" }, { world: [1, 1], snap: { point: [0, 0], kind: "end" }, handle: null }, CTX);
    const second = applyPick(first, { world: [9, 1], snap: null, handle: null }, CTX);
    expect(second.items).toEqual([{ kind: "segment", handle: "", start_m: 0, end_m: 0, points: [[0, 0], [9, 1]], flip: false, label: "" }]);
  });

  it("отмена, разворот и удаление участка", () => {
    const two = applyPick(applyPick(assembly, { world: [120, 203], snap: null, handle: "6C3" }, CTX), { world: [110, 181], snap: null, handle: "733" }, CTX);
    expect(two.items.map((item) => item.handle)).toEqual(["6C3", "733"]);
    expect(flipItem(two, 0).items[0].flip).toBe(true);
    expect(removeItem(two, 0).items.map((item) => item.handle)).toEqual(["733"]);
    expect(undoItem(two).items.map((item) => item.handle)).toEqual(["6C3"]);
  });
});

describe("блок по бровке и прочие способы", () => {
  it("две точки ложатся на сшитую верхнюю бровку", () => {
    const crest = state({ method: "crest" });
    const first = applyPick(crest, { world: [110, 210], snap: null, handle: null }, CTX);
    expect(first.crestStart?.[0]).toBeCloseTo(111.35, 1);
    const second = applyPick(first, { world: [125, 200], snap: null, handle: null }, CTX);
    expect(second.crestEnd).not.toBeNull();
    const third = applyPick(second, { world: [101, 200], snap: null, handle: null }, CTX);
    expect(third.crestEnd).toBeNull();
  });

  it("щелчок внутри запоминает точку", () => {
    expect(applyPick(state({ method: "click" }), { world: [3, 4], snap: null, handle: null }, CTX).point).toEqual([3, 4]);
  });

  it("результат любого способа правится как сборка", () => {
    const result = { items: [{ kind: "part", handle: "769", start_m: 0, end_m: 10, points: [], flip: false, label: "" }] } as unknown as CadContourResult;
    expect(asAssembly(state(), result)).toMatchObject({ method: "assembly", items: result.items, selected: null });
  });
});
