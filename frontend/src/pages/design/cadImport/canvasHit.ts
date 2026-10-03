// Попадание курсора на холсте импорта (TASK-013, PR 4). Базовый слой чертежа
// рисуется одним `<canvas>` (на чертеже карьера — десятки тысяч линий), поэтому
// линию под курсором ищет сетка отрезков (`SnapIndex`), а точку отметки —
// сетка точек. Линия возвращает себя, точка — свой слой целиком, как раньше
// SVG-зоны попадания.
import type { CadEntity } from "../../../types/cad";
import type { CanvasTarget } from "./CadCanvas";
import { PointCells, SnapIndex, type XY } from "./contourGeometry";

export class CanvasHitIndex {
  private readonly lines: SnapIndex;
  private readonly layers = new Map<string, string>();
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
    this.lines = new SnapIndex(lines, []);
  }

  /** Линия не дальше `radius` метров, иначе слой ближайшей точки, иначе `null`. */
  hit(world: XY, radius: number): CanvasTarget | null {
    const snap = this.lines.snap(world, radius);
    const layer = snap?.handle ? this.layers.get(snap.handle) : undefined;
    if (snap?.handle && layer !== undefined) return { layer, handle: snap.handle };
    const point = this.points.nearest(world, radius);
    return point ? { layer: point.layer, handle: null } : null;
  }
}
