// Геометрия шага «Контур»: проекция на линию, участок по щелчку, привязка курсора.
import { describe, expect, it } from "vitest";
import type { CadEntity } from "../../../types/cad";
import { pieceAt, polylineXY, projectOnPolyline, SnapIndex, subPolyline } from "./contourGeometry";

function line(handle: string, points: Array<[number, number]>, closed = false): CadEntity {
  return {
    handle,
    layer: "Проект",
    kind: "LWPOLYLINE",
    geometry_type: "line",
    points: points.map(([x, y]) => [x, y, 0]),
    closed,
    closed_by_gap: false,
    vertex_count: points.length,
    length_m: 0,
    area_m2: 0,
    z_kind: "zero",
    z_min: 0,
    z_max: 0,
    z_from_label: false,
    text: "",
    color: null,
    role: "design_line",
    role_origin: "auto",
    role_override: false,
  };
}

const ZIGZAG: Array<[number, number]> = [
  [0, 0],
  [10, 0],
  [10, 10],
  [20, 10],
];

describe("projectOnPolyline и subPolyline", () => {
  it("длина по линии в плане — как на сервере", () => {
    expect(projectOnPolyline(ZIGZAG, [10, 5])).toMatchObject({ m: 15, distance: 0 });
    const off = projectOnPolyline(ZIGZAG, [5, 2]);
    expect(off.m).toBeCloseTo(5);
    expect(off.distance).toBeCloseTo(2);
    expect(off.point).toEqual([5, 0]);
  });

  it("кусок линии между двумя расстояниями", () => {
    expect(subPolyline(ZIGZAG, 5, 15)).toEqual([
      [5, 0],
      [10, 0],
      [10, 5],
    ]);
    expect(subPolyline(ZIGZAG, 15, 5)).toEqual([
      [5, 0],
      [10, 0],
      [10, 5],
    ]);
  });

  it("у замкнутой линии есть ребро возврата в начало", () => {
    expect(polylineXY(line("C", [[0, 0], [10, 0], [10, 10]], true))).toHaveLength(4);
  });

  it("зазор концов короче 5 см — не ребро возврата (как на сервере)", () => {
    expect(polylineXY(line("G", [[0, 0], [10, 0], [10, 10], [0.02, 0.02]], true))).toHaveLength(4);
  });
});

describe("pieceAt: участок между соседними разрезами", () => {
  const entity = line("Z", ZIGZAG);
  it("между двумя пересечениями", () => {
    expect(pieceAt(entity, 12, [8, 18])).toEqual({ start_m: 8, end_m: 18 });
  });
  it("от начала линии до первого разреза и от последнего до конца", () => {
    expect(pieceAt(entity, 3, [8, 18])).toEqual({ start_m: 0, end_m: 8 });
    expect(pieceAt(entity, 25, [8, 18])).toEqual({ start_m: 18, end_m: 30 });
  });
  it("без разрезов — вся линия", () => {
    expect(pieceAt(entity, 25, undefined)).toEqual({ start_m: 0, end_m: 30 });
  });
});

describe("SnapIndex: привязка курсора", () => {
  const a = line("A", [
    [0, 0],
    [10, 0],
  ]);
  const b = line("B", [
    [5, -5],
    [5, 5],
    [8, 5],
  ]);
  const index = new SnapIndex([a, b], [[5, 0]]);

  it("конец линии важнее ближайшей точки", () => {
    expect(index.snap([0.5, 0.2], 1)).toMatchObject({ kind: "end", point: [0, 0], handle: "A" });
  });

  it("пересечение важнее вершины и ближайшей точки", () => {
    expect(index.snap([5.3, 0.4], 1)).toMatchObject({ kind: "intersection", point: [5, 0] });
  });

  it("у пересечения есть ближайшая линия — щелчок «Участок» рядом с узлом не теряется", () => {
    const snap = index.snap([5.6, 0.1], 1);
    expect(snap).toMatchObject({ kind: "intersection", handle: "A" });
    expect(snap?.m).toBeCloseTo(5);
  });

  it("вершина в середине линии", () => {
    expect(index.snap([5.4, 5.3], 1)).toMatchObject({ kind: "vertex", point: [5, 5], handle: "B" });
  });

  it("ближайшая точка на линии с длиной по ней", () => {
    const snap = index.snap([2.5, 0.3], 1);
    expect(snap).toMatchObject({ kind: "nearest", handle: "A" });
    expect(snap?.point[0]).toBeCloseTo(2.5);
    expect(snap?.m).toBeCloseTo(2.5);
  });

  it("в общем узле двух линий привязка относится к линии под курсором", () => {
    const left = line("L", [
      [0, 0],
      [10, 0],
    ]);
    const up = line("U", [
      [10, 0],
      [10, 10],
    ]);
    const shared = new SnapIndex([up, left], []);
    // Курсор у узла (10; 0), но ближе к телу вертикальной линии.
    const snap = shared.snap([10.1, 0.6], 1);
    expect(snap).toMatchObject({ kind: "end", point: [10, 0], handle: "U", m: 0 });
  });

  it("вне апертуры — привязки нет", () => {
    expect(index.snap([2.5, 3], 1)).toBeNull();
  });
});

describe("SnapIndex: длинные линии карьера", () => {
  it("диагональ в километры не раздувает индекс и привязывается посередине", () => {
    const diagonals = Array.from({ length: 10 }, (_, k) =>
      line(`D${k}`, [
        [0, k * 100],
        [5000, 5000 + k * 100],
      ]),
    );
    const started = performance.now();
    const index = new SnapIndex(diagonals, []);
    const elapsed = performance.now() - started;

    expect(elapsed).toBeLessThan(300);
    const snap = index.snap([2500.3, 2499.6], 2);
    expect(snap).toMatchObject({ kind: "nearest", handle: "D0" });
  });
});

describe("SnapIndex: тысячи вершин", () => {
  it("движение мыши не перебирает все вершины чертежа", () => {
    // 2000 полилиний по 100 вершин — 200 тысяч вершин и концов.
    const lines = Array.from({ length: 2000 }, (_, k) =>
      line(
        `P${k}`,
        Array.from({ length: 100 }, (__, i) => [i * 2, k * 3] as [number, number]),
      ),
    );
    const index = new SnapIndex(lines, Array.from({ length: 5000 }, (_, k) => [k, -10]));
    const started = performance.now();
    for (let move = 0; move < 500; move += 1) index.snap([50 + (move % 7), 300 + (move % 11)], 1);
    const elapsed = performance.now() - started;

    expect(elapsed).toBeLessThan(150);
    expect(index.snap([50.2, 300.3], 1)).toMatchObject({ kind: "vertex", point: [50, 300] });
  });
});
