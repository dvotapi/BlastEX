import { describe, expect, it } from "vitest";
import { DIFF_BLOCK_LABELS, DIFF_HOLE_LABELS, splitComparison, type Row } from "./comparisonLayout";

/** Строки скважины в порядке `cost/geometry.py::hole_geometry_table_rows`. */
function holeRows(overrides: Record<string, string> = {}, nsi2 = false): Row[] {
  const rows: Row[] = [
    ["Сетка a×b, м", "4.84 × 4.84"],
    ["Глубина, м", "11.0"],
    ["Перебур, м", "1.0"],
    ["Недозаряд, м", "2.7"],
    ["Длина заряда, м", "8.3"],
    ["Диаметр заряда, мм", "157"],
    ["Вместимость, кг/п.м.", "16.36"],
    ["Выход, м³", "234.26"],
    ["Заряд, кг", "136"],
    ["Удельный, кг/м³", "0.580"],
    ["Пром. детонаторы, шт/скв", "1"],
    ["Скважинное НСИ, шт/скв", nsi2 ? "2 (дублирование)" : "1"],
    ["Поверхностное НСИ, шт/скв", "1"],
    ["Длина скважинного НСИ-1, м", "12"],
  ];
  if (nsi2) rows.push(["Длина скважинного НСИ-2, м", "6"]);
  rows.push(["Замедление, мс", "500"]);
  return rows.map(([label, value]) => [label, overrides[label] ?? value]);
}

/** Строки блока в порядке `cost/geometry.py::block_geometry_table_rows`. */
function blockRows(overrides: Record<string, string> = {}): Row[] {
  const rows: Row[] = [
    ["Объём блока, м³", "22 000"],
    ["Скважин, шт.", "94"],
    ["Доп. скважины, %", "3"],
    ["Доп. скважины, шт.", "3"],
    ["Всего скважин, шт.", "97"],
    ["Кол-во п.м., п.м.", "1 067"],
    ["Масса ВВ на блок, кг", "13 174"],
    ["Удельный с доп., кг/м³", "0.599"],
    ["Пром. детонаторы, шт", "97"],
    ["НСИ скважинное, шт", "97"],
    ["Боевики на НСИ, шт", "97"],
    ["НСИ поверхностное, шт", "97"],
    ["НСИ стартовое, шт", "1"],
    ["Длина скважинного НСИ на блок, м", "1 164"],
  ];
  return rows.map(([label, value]) => [label, overrides[label] ?? value]);
}

const labels = (rows: { label: string }[]) => rows.map((row) => row.label);

describe("splitComparison", () => {
  it("фиксированный состав отличий показывается всегда, даже при равных значениях", () => {
    const result = splitComparison(holeRows(), holeRows({ "Заряд, кг": "179" }), blockRows(), blockRows());
    // Порядок — как в ответе API (замедление там последнее), состав — фиксированный.
    const inApiOrder = (rows: Row[], fixed: readonly string[]) => rows.map(([label]) => label).filter((label) => fixed.includes(label));
    expect(labels(result.diffHole)).toEqual(inApiOrder(holeRows(), DIFF_HOLE_LABELS));
    expect(labels(result.diffBlock)).toEqual(inApiOrder(blockRows(), DIFF_BLOCK_LABELS));
    expect(labels(result.diffHole)).toHaveLength(DIFF_HOLE_LABELS.length - 1);
    expect(result.diffHole.find((row) => row.label === "Заряд, кг")).toEqual({ label: "Заряд, кг", a: "136", b: "179", flag: false });
    expect(result.diffHole.every((row) => !row.flag)).toBe(true);
  });

  it("остальные строки при равенстве идут в общее, скважина раньше блока, порядок как в API", () => {
    const result = splitComparison(holeRows(), holeRows(), blockRows(), blockRows());
    expect(labels(result.shared)).toEqual([
      "Сетка a×b, м",
      "Глубина, м",
      "Перебур, м",
      "Диаметр заряда, мм",
      "Выход, м³",
      "Поверхностное НСИ, шт/скв",
      "Объём блока, м³",
      "Скважин, шт.",
      "Доп. скважины, %",
      "Доп. скважины, шт.",
      "Всего скважин, шт.",
      "Кол-во п.м., п.м.",
      "НСИ поверхностное, шт",
      "НСИ стартовое, шт",
    ]);
    expect(result.shared[0]).toEqual({ label: "Сетка a×b, м", value: "4.84 × 4.84" });
  });

  it("«общая» строка, которая неожиданно различается, уходит в отличия с флагом", () => {
    const result = splitComparison(holeRows(), holeRows({ "Диаметр заряда, мм": "160" }), blockRows(), blockRows());
    expect(labels(result.shared)).not.toContain("Диаметр заряда, мм");
    expect(result.diffHole).toContainEqual({ label: "Диаметр заряда, мм", a: "157", b: "160", flag: true });
    // Своё место по порядку API: сразу после «Длина заряда, м».
    expect(labels(result.diffHole).slice(0, 3)).toEqual(["Недозаряд, м", "Длина заряда, м", "Диаметр заряда, мм"]);
  });

  it("НСИ-2 появляется, когда он есть хотя бы у одного варианта, на своём месте", () => {
    const result = splitComparison(holeRows({}, true), holeRows(), blockRows(), blockRows());
    const nsi2 = result.diffHole.find((row) => row.label === "Длина скважинного НСИ-2, м");
    expect(nsi2).toEqual({ label: "Длина скважинного НСИ-2, м", a: "6", b: null, flag: false });
    const order = labels(result.diffHole);
    expect(order.indexOf("Длина скважинного НСИ-2, м")).toBe(order.indexOf("Длина скважинного НСИ-1, м") + 1);
    expect(order.indexOf("Замедление, мс")).toBeGreaterThan(order.indexOf("Длина скважинного НСИ-2, м"));
  });

  it("без НСИ-2 у обоих вариантов строки НСИ-2 нет", () => {
    const result = splitComparison(holeRows(), holeRows(), blockRows(), blockRows());
    expect(labels(result.diffHole)).not.toContain("Длина скважинного НСИ-2, м");
  });

  it("строка, которой у второго варианта нет вовсе, не теряется", () => {
    const holeB = holeRows().filter(([label]) => label !== "Выход, м³");
    const result = splitComparison(holeRows(), holeB, blockRows(), blockRows());
    expect(result.diffHole).toContainEqual({ label: "Выход, м³", a: "234.26", b: null, flag: true });
  });

  it("ни одна строка ответа не теряется и значения не меняются", () => {
    const holeA = holeRows({}, true);
    const holeB = holeRows({ "Глубина, м": "12.0", "Замедление, мс": "700" });
    const blockA = blockRows();
    const blockB = blockRows({ "Масса ВВ на блок, кг": "17 359", "Скважин, шт.": "95" });
    const result = splitComparison(holeA, holeB, blockA, blockB);

    const outHole = new Map<string, { a: string | null; b: string | null }>();
    for (const row of result.diffHole) outHole.set(row.label, { a: row.a, b: row.b });
    const outBlock = new Map<string, { a: string | null; b: string | null }>();
    for (const row of result.diffBlock) outBlock.set(row.label, { a: row.a, b: row.b });
    const holeLabels = new Set(holeA.map(([l]) => l));
    for (const row of result.shared) {
      const target = holeLabels.has(row.label) ? outHole : outBlock;
      target.set(row.label, { a: row.value, b: row.value });
    }

    const expectSection = (a: Row[], b: Row[], out: Map<string, { a: string | null; b: string | null }>) => {
      const union = new Set([...a.map(([l]) => l), ...b.map(([l]) => l)]);
      expect(new Set(out.keys())).toEqual(union);
      for (const label of union) {
        expect(out.get(label)).toEqual({
          a: a.find(([l]) => l === label)?.[1] ?? null,
          b: b.find(([l]) => l === label)?.[1] ?? null,
        });
      }
    };
    expectSection(holeA, holeB, outHole);
    expectSection(blockA, blockB, outBlock);
  });
});
