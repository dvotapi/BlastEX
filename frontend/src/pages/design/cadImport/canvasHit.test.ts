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

  it("точка отметки — слой целиком, как прежде на SVG", () => {
    expect(index.hit([110.1, 190.1], 0.5)).toEqual({ layer: "Отметка", handle: null });
  });

  it("пусто и подписи не ловятся", () => {
    expect(index.hit([60, 60], 0.5)).toBeNull();
    // Подпись 61A лежит в (110,2; 190,3), но точка 51C рядом — подальше от неё подписи не видно.
    expect(new CanvasHitIndex(ENTITIES.filter((entity) => entity.geometry_type === "text")).hit([110.2, 190.3], 1)).toBeNull();
  });
});
