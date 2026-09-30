// Геометрия холста импорта чертежа: габариты и SVG-пути в экранных
// координатах. Координаты МСК (миллионы метров) переводятся в экранные до
// записи в путь — так SVG не теряет точности на больших числах.
import { worldToScreen, type Bounds, type Camera, type Viewport } from "../../../lib/geometry2d";
import { plural } from "../../../lib/plural";
import type { CadEntity, CadPoint } from "../../../types/cad";

export function drawingBounds(entities: CadEntity[]): Bounds | null {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const entity of entities) {
    if (entity.geometry_type === "text") continue;
    for (const [x, y] of entity.points) {
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (x > maxX) maxX = x;
      if (y > maxY) maxY = y;
    }
  }
  return Number.isFinite(minX) ? { minX, minY, maxX, maxY } : null;
}

function screen(point: CadPoint, camera: Camera, viewport: Viewport) {
  return worldToScreen(camera, viewport, { x: point[0], y: point[1] });
}

export function linePath(points: CadPoint[], closed: boolean, camera: Camera, viewport: Viewport): string {
  const parts = points.map((point, index) => {
    const p = screen(point, camera, viewport);
    return `${index ? "L" : "M"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`;
  });
  return parts.join("") + (closed && points.length > 2 ? "Z" : "");
}

/** Кружки радиусом `radius` пикселей одним путём — сотни точек без сотен узлов DOM. */
export function pointsPath(points: CadPoint[], camera: Camera, viewport: Viewport, radius: number): string {
  return points
    .map((point) => {
      const p = screen(point, camera, viewport);
      return `M${(p.x - radius).toFixed(1)} ${p.y.toFixed(1)}a${radius} ${radius} 0 1 0 ${radius * 2} 0a${radius} ${radius} 0 1 0 ${-radius * 2} 0`;
    })
    .join("");
}

/** Сущности по слоям в порядке первого появления слоя. */
export function entitiesByLayer(entities: CadEntity[]): Map<string, CadEntity[]> {
  const grouped = new Map<string, CadEntity[]>();
  for (const entity of entities) {
    const list = grouped.get(entity.layer);
    if (list) list.push(entity);
    else grouped.set(entity.layer, [entity]);
  }
  return grouped;
}

/** «1 линия», «23 фрагмента» — сколько линий слоя свёрнуто в строку. */
export function fragmentsLabel(count: number): string {
  if (count === 1) return "1 линия";
  return `${count} ${plural(count, ["фрагмент", "фрагмента", "фрагментов"])}`;
}
