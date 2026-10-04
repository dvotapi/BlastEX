// Попадание курсора на холсте импорта (TASK-013, PR 4). Базовый слой чертежа
// рисуется одним `<canvas>` (на чертеже карьера — десятки тысяч линий), поэтому
// линию под курсором ищет сетка отрезков (`SnapIndex`), а точку отметки —
// сетка точек. Как раньше у SVG-зон: точки — поверх линий, из совпадающих
// линий выигрывает нарисованная сверху (контур над бровкой); линия возвращает
// себя, точка — свой слой целиком.
import type { CadEntity } from "../../../types/cad";
import type { CanvasTarget } from "./CadCanvas";
import { inDrawOrder } from "./cadRoles";
import { PointCells, SnapIndex, type XY } from "./contourGeometry";

export class CanvasHitIndex {
  private readonly lines: SnapIndex;
  private readonly layers = new Map<string, string>();
  // Место линии в порядке рисования: больше — выше на экране.
  private readonly rank = new Map<string, number>();
  private readonly points = new PointCells<{ point: XY; layer: string }>();

  constructor(entities: CadEntity[]) {
    const lines: CadEntity[] = [];
    for (const entity of entities) {
      if (entity.geometry_type === "line") {
        lines.push(entity);
        this.layers.set(entity.handle, entity.layer);
      } else if (entity.geometry_type === "point" && entity.points.length) {
        this.points.add({ point: [entity.points[0][0], entity.points[0][1]], layer: entity.layer });
      }
    }
    inDrawOrder(lines).forEach((entity, index) => this.rank.set(entity.handle, index));
    this.lines = new SnapIndex(lines, []);
  }

  /**
   * Точка отметки не дальше `pointRadius` — её слой; иначе линия не дальше
   * `radius`: из почти равноудалённых (разница до `tie`) — верхняя на экране.
   */
  hit(world: XY, radius: number, pointRadius = radius, tie = radius * 0.05): CanvasTarget | null {
    const point = this.points.nearest(world, pointRadius);
    if (point) return { layer: point.layer, handle: null };
    const near = this.lines.linesNear(world, radius);
    if (!near.size) return null;
    const best = Math.min(...near.values());
    let chosen: string | null = null;
    for (const [handle, distance] of near) {
      if (distance > best + tie) continue;
      if (chosen === null || (this.rank.get(handle) ?? -1) > (this.rank.get(chosen) ?? -1)) chosen = handle;
    }
    const layer = chosen !== null ? this.layers.get(chosen) : undefined;
    return chosen !== null && layer !== undefined ? { layer, handle: chosen } : null;
  }
}
