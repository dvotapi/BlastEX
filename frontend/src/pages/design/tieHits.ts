// Попадания по связям на плане (TASK-017, PR 4): всё в экранных пикселях.
import { distance, projectOnSegment, rectContains, type Vec2 } from "../../lib/geometry2d";

export type TieSegment = { id: string; a: Vec2; b: Vec2 };
type Rect = { minX: number; minY: number; maxX: number; maxY: number };

/** Радиус попадания по линии связи, px. */
export const TIE_HIT_RADIUS_PX = 6;

/** Ближайшая связь не дальше `radius` от точки; нет — null. */
export function hitTie(point: Vec2, segments: TieSegment[], radius = TIE_HIT_RADIUS_PX): string | null {
  let best: string | null = null;
  let bestDistance = Infinity;
  for (const segment of segments) {
    const d = projectOnSegment(point, segment.a, segment.b).distance;
    if (d <= radius && d < bestDistance) {
      best = segment.id;
      bestDistance = d;
    }
  }
  return best;
}

function cross(o: Vec2, a: Vec2, b: Vec2): number {
  return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
}

function segmentsCross(p1: Vec2, p2: Vec2, q1: Vec2, q2: Vec2): boolean {
  const d1 = cross(q1, q2, p1);
  const d2 = cross(q1, q2, p2);
  const d3 = cross(p1, p2, q1);
  const d4 = cross(p1, p2, q2);
  return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0));
}

function intersectsRect(segment: TieSegment, rect: Rect): boolean {
  if (rectContains(rect, segment.a) || rectContains(rect, segment.b)) return true;
  const corners = [
    { x: rect.minX, y: rect.minY },
    { x: rect.maxX, y: rect.minY },
    { x: rect.maxX, y: rect.maxY },
    { x: rect.minX, y: rect.maxY },
  ];
  return corners.some((corner, i) => segmentsCross(segment.a, segment.b, corner, corners[(i + 1) % 4]));
}

/** Связи, отрезок которых пересекает рамку или лежит в ней. */
export function tiesInRect(rect: Rect, segments: TieSegment[]): string[] {
  return segments.filter((segment) => intersectsRect(segment, rect)).map((segment) => segment.id);
}

/** Конец связи под точкой: начало, конец или ни один (ближний из двух). */
export function tieEndAt(point: Vec2, segment: TieSegment, radius: number): "from" | "to" | null {
  const toA = distance(point, segment.a);
  const toB = distance(point, segment.b);
  if (Math.min(toA, toB) > radius) return null;
  return toA <= toB ? "from" : "to";
}
