// Геометрия шага «Контур» (TASK-013, PR 2): только то, что нужно для
// взаимодействия на холсте, — проекция курсора на линию, участок линии по
// щелчку и привязка. Кольцо, проверки, площади и свободную поверхность
// считает сервер (`/design/cad/sources/{id}/contour`). Длина по линии — в
// плане, как в `design/spatial/cad/contour.py`: участок, выбранный здесь,
// сервер вырежет из той же линии в тех же метрах.
import type { CadEntity } from "../../../types/cad";

export type XY = [number, number];

export type SnapKind = "end" | "intersection" | "vertex" | "nearest";

export type Snap = {
  point: XY;
  kind: SnapKind;
  /** Линия, к которой привязалась точка (у пересечения — нет). */
  handle?: string;
  /** Расстояние по линии от её начала — для привязки к линии. */
  m?: number;
};

/** Точки линии в плане; у замкнутой — с возвратом в начало. */
export function polylineXY(entity: CadEntity): XY[] {
  const points = entity.points.map(([x, y]) => [x, y] as XY);
  if (entity.closed && points.length > 2) points.push(points[0]);
  return points;
}

export function polylineLength(points: XY[]): number {
  let total = 0;
  for (let index = 1; index < points.length; index += 1) {
    total += Math.hypot(points[index][0] - points[index - 1][0], points[index][1] - points[index - 1][1]);
  }
  return total;
}

/** Ближайшая точка полилинии: длина по линии, сама точка и расстояние до неё. */
export function projectOnPolyline(points: XY[], p: XY): { m: number; point: XY; distance: number } {
  let best = { m: 0, point: points[0], distance: Math.hypot(p[0] - points[0][0], p[1] - points[0][1]) };
  let walked = 0;
  for (let index = 1; index < points.length; index += 1) {
    const [ax, ay] = points[index - 1];
    const [bx, by] = points[index];
    const dx = bx - ax;
    const dy = by - ay;
    const length2 = dx * dx + dy * dy;
    const t = length2 ? Math.max(0, Math.min(1, ((p[0] - ax) * dx + (p[1] - ay) * dy) / length2)) : 0;
    const foot: XY = [ax + dx * t, ay + dy * t];
    const distance = Math.hypot(p[0] - foot[0], p[1] - foot[1]);
    const length = Math.sqrt(length2);
    if (distance < best.distance) best = { m: walked + t * length, point: foot, distance };
    walked += length;
  }
  return best;
}

/** Кусок полилинии между расстояниями `from` и `to` от её начала. */
export function subPolyline(points: XY[], from: number, to: number): XY[] {
  const total = polylineLength(points);
  const start = Math.min(Math.max(Math.min(from, to), 0), total);
  const end = Math.min(Math.max(Math.max(from, to), 0), total);
  const result: XY[] = [];
  let walked = 0;
  for (let index = 1; index < points.length; index += 1) {
    const a = points[index - 1];
    const b = points[index];
    const length = Math.hypot(b[0] - a[0], b[1] - a[1]);
    const segStart = walked;
    walked += length;
    if (walked < start) continue;
    const at = (m: number): XY =>
      length ? [a[0] + ((b[0] - a[0]) * (m - segStart)) / length, a[1] + ((b[1] - a[1]) * (m - segStart)) / length] : a;
    if (!result.length) result.push(at(start));
    if (walked >= end) {
      result.push(at(end));
      break;
    }
    result.push(b);
  }
  return result.filter((point, index) => index === 0 || Math.hypot(point[0] - result[index - 1][0], point[1] - result[index - 1][1]) > 1e-9);
}

/** Участок линии между соседними разрезами (пересечениями) вокруг точки `m`. */
export function pieceAt(entity: CadEntity, m: number, splits: number[] | undefined): { start_m: number; end_m: number } {
  const total = polylineLength(polylineXY(entity));
  let start = 0;
  let end = total;
  for (const cut of splits ?? []) {
    if (cut <= m && cut > start) start = cut;
    if (cut > m && cut < end) end = cut;
  }
  return { start_m: start, end_m: end };
}

type Segment = { handle: string; a: XY; b: XY; startM: number };

/**
 * Привязка курсора: конец линии, пересечение, вершина, ближайшая точка — в
 * таком порядке важности (как объектная привязка САПР). Сегменты разложены по
 * ячейкам, чтобы движение мыши над чертежом с тысячами линий не перебирало все.
 */
export class SnapIndex {
  private readonly cell: number;
  private readonly segments: Segment[] = [];
  private readonly grid = new Map<string, number[]>();
  private readonly ends: Array<{ point: XY; handle: string; m: number }> = [];
  private readonly vertices: Array<{ point: XY; handle: string; m: number }> = [];
  private readonly crossings: XY[];

  constructor(lines: CadEntity[], intersections: number[][], cell = 5) {
    this.cell = cell;
    this.crossings = intersections.map(([x, y]) => [x, y] as XY);
    for (const entity of lines) {
      if (entity.geometry_type !== "line" || entity.points.length < 2) continue;
      const points = polylineXY(entity);
      let walked = 0;
      points.forEach((point, index) => {
        const isEnd = !entity.closed && (index === 0 || index === points.length - 1);
        (isEnd ? this.ends : this.vertices).push({ point, handle: entity.handle, m: walked });
        if (index === points.length - 1) return;
        const next = points[index + 1];
        this.add({ handle: entity.handle, a: point, b: next, startM: walked });
        walked += Math.hypot(next[0] - point[0], next[1] - point[1]);
      });
    }
  }

  private key(cx: number, cy: number): string {
    return `${cx}:${cy}`;
  }

  private add(segment: Segment) {
    const at = this.segments.push(segment) - 1;
    const [x0, x1] = [Math.min(segment.a[0], segment.b[0]), Math.max(segment.a[0], segment.b[0])];
    const [y0, y1] = [Math.min(segment.a[1], segment.b[1]), Math.max(segment.a[1], segment.b[1])];
    for (let cx = Math.floor(x0 / this.cell); cx <= Math.floor(x1 / this.cell); cx += 1) {
      for (let cy = Math.floor(y0 / this.cell); cy <= Math.floor(y1 / this.cell); cy += 1) {
        const key = this.key(cx, cy);
        const list = this.grid.get(key);
        if (list) list.push(at);
        else this.grid.set(key, [at]);
      }
    }
  }

  private nearSegments(p: XY, radius: number): Segment[] {
    const x0 = Math.floor((p[0] - radius) / this.cell);
    const x1 = Math.floor((p[0] + radius) / this.cell);
    const y0 = Math.floor((p[1] - radius) / this.cell);
    const y1 = Math.floor((p[1] + radius) / this.cell);
    // Очень мелкий масштаб: ячеек больше, чем сегментов, — проще перебрать все.
    if ((x1 - x0 + 1) * (y1 - y0 + 1) > this.segments.length) return this.segments;
    const found = new Set<number>();
    for (let cx = x0; cx <= x1; cx += 1) {
      for (let cy = y0; cy <= y1; cy += 1) for (const at of this.grid.get(this.key(cx, cy)) ?? []) found.add(at);
    }
    return [...found].map((at) => this.segments[at]);
  }

  /** Точка привязки не дальше `aperture` метров от курсора или `null`. */
  snap(p: XY, aperture: number): Snap | null {
    const distance = (q: XY) => Math.hypot(q[0] - p[0], q[1] - p[1]);
    const closest = <T extends { point: XY }>(items: T[]): T | undefined => {
      let best: T | undefined;
      let bestDistance = aperture;
      for (const item of items) {
        const d = distance(item.point);
        if (d <= bestDistance) {
          best = item;
          bestDistance = d;
        }
      }
      return best;
    };

    const end = closest(this.ends);
    if (end) return { point: end.point, kind: "end", handle: end.handle, m: end.m };
    const crossing = closest(this.crossings.map((point) => ({ point })));
    if (crossing) return { point: crossing.point, kind: "intersection" };
    const vertex = closest(this.vertices);
    if (vertex) return { point: vertex.point, kind: "vertex", handle: vertex.handle, m: vertex.m };

    let best: Snap | null = null;
    let bestDistance = aperture;
    for (const segment of this.nearSegments(p, aperture)) {
      const hit = projectOnPolyline([segment.a, segment.b], p);
      if (hit.distance <= bestDistance) {
        bestDistance = hit.distance;
        best = { point: hit.point, kind: "nearest", handle: segment.handle, m: segment.startM + hit.m };
      }
    }
    return best;
  }
}
