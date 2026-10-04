// Попадание курсора на холсте импорта (TASK-013, PR 4): базовый слой — один
// `<canvas>`, поэтому линию и слой под курсором ищет сетка, а не SVG-зоны.
import { describe, expect, it } from "vitest";
import { CanvasHitIndex } from "./canvasHit";
import { cadEntity, cadSource } from "./testing/fixtures";

const ENTITIES = cadSource().entities;

describe("CanvasHitIndex", () => {
  const index = new CanvasHitIndex(ENTITIES);

  it("линия под курсором — её слой и handle", () => {
    // Нижнее ребро контура 769: (90; 170) → (140; 170).
    expect(index.hit([120, 170.2], 0.5)).toEqual({ layer: "блок 66 вар 2", handle: "769" });
    // Нижняя бровка 733: (100; 180) → (130; 182).
    expect(index.hit([115, 181], 0.5)).toEqual({ layer: "Горизонт +410", handle: "733" });
  });

  it("из двух линий — ближайшая", () => {
    const near = new CanvasHitIndex([
      cadEntity("A", "Слой А", { points: [[0, 0, 0], [10, 0, 0]] }),
      cadEntity("B", "Слой Б", { points: [[0, 0.4, 0], [10, 0.4, 0]] }),
    ]);
    expect(near.hit([5, 0.3], 0.5)?.handle).toBe("B");
    expect(near.hit([5, 0.1], 0.5)?.handle).toBe("A");
  });

  it("замыкающее ребро замкнутой линии без повтора первой вершины ловится, как и нарисовано", () => {
    // Проверка замечания Codex (#108, круг 5): ребро последняя → первая вершина.
    const square = new CanvasHitIndex([
      cadEntity("SQ", "Склад", { closed: true, points: [[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]] }),
    ]);
    expect(square.hit([0.1, 5], 0.5)).toEqual({ layer: "Склад", handle: "SQ" });
    expect(new CanvasHitIndex([cadEntity("PL", "Склад", { points: [[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]] })]).hit([0.1, 5], 0.5)).toBeNull();
  });

  it("точка отметки — слой целиком, как прежде на SVG", () => {
    expect(index.hit([110.1, 190.1], 0.5)).toEqual({ layer: "Отметка", handle: null });
  });

  it("пусто и подписи не ловятся", () => {
    expect(index.hit([60, 60], 0.5)).toBeNull();
    // Подпись 61A лежит в (110,2; 190,3), но точка 51C рядом — подальше от неё подписи не видно.
    expect(new CanvasHitIndex(ENTITIES.filter((entity) => entity.geometry_type === "text")).hit([110.2, 190.3], 1)).toBeNull();
  });
});

describe("CanvasHitIndex: что сверху на экране", () => {
  const LINE: [number, number, number][] = [
    [0, 0, 420],
    [20, 0, 420],
  ];

  it("совпадающие линии — выигрывает нарисованная сверху (контур над бровкой), а не порядок в файле", () => {
    const contour = cadEntity("C", "блок", { role: "block_contour", points: LINE });
    const crest = cadEntity("T", "Горизонт +410", { role: "crest_top", points: LINE });

    expect(new CanvasHitIndex([contour, crest]).hit([10, 0.05], 0.5)?.handle).toBe("C");
    expect(new CanvasHitIndex([crest, contour]).hit([10, 0.05], 0.5)?.handle).toBe("C");
  });

  it("точка отметки рядом с линией наводится, как раньше на SVG (точки поверх линий)", () => {
    const line = cadEntity("L", "Горизонт +410", { role: "crest_top", points: LINE });
    const point = cadEntity("P", "Отметка", {
      kind: "POINT",
      geometry_type: "point",
      role: "spot_heights",
      points: [[10, 0.3, 420]],
    });

    expect(new CanvasHitIndex([line, point]).hit([10, 0.25], 0.5, 0.5)).toEqual({ layer: "Отметка", handle: null });
    // Курсор на линии, далеко от точки — линия.
    expect(new CanvasHitIndex([line, point]).hit([2, 0], 0.5, 0.5)?.handle).toBe("L");
  });
});
