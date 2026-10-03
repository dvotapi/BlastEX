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

/** Ребро короче — не ребро контура (сервер: `rings.MIN_EDGE_M`). */
const MIN_EDGE_M = 0.05;

/**
 * Точки линии в плане; у замкнутой — с возвратом в начало, если ребро возврата
 * не короче 5 см. Так же, как `contour.line_xy` на сервере: зазор в сантиметры
 * у «замкнутой по разрыву» линии сводит допуск, а не ребро-щель.
 */
export function polylineXY(entity: CadEntity): XY[] {
  const points = entity.points.map(([x, y]) => [x, y] as XY);
  if (entity.closed && points.length > 2) {
    const [first, last] = [points[0], points[points.length - 1]];
    if (Math.hypot(last[0] - first[0], last[1] - first[1]) >= MIN_EDGE_M) points.push(first);
  }
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

/** Точки привязки (концы, вершины, пересечения) по ячейкам: движение мыши над
 * чертежом с сотнями тысяч вершин смотрит только ячейки в пределах апертуры. */
export class PointCells<T extends { point: XY }> {
  cell = 5;
  private readonly items: T[] = [];
  private readonly grid = new Map<string, number[]>();

  add(item: T) {
    const at = this.items.push(item) - 1;
    const key = `${Math.floor(item.point[0] / this.cell)}:${Math.floor(item.point[1] / this.cell)}`;
    const list = this.grid.get(key);
    if (list) list.push(at);
    else this.grid.set(key, [at]);
  }

  /** Ближайшая точка не дальше `radius` или `undefined`. */
  nearest(p: XY, radius: number): T | undefined {
    const x0 = Math.floor((p[0] - radius) / this.cell);
    const x1 = Math.floor((p[0] + radius) / this.cell);
    const y0 = Math.floor((p[1] - radius) / this.cell);
    const y1 = Math.floor((p[1] + radius) / this.cell);
    let best: T | undefined;
    let bestDistance = radius;
    const consider = (item: T) => {
      const d = Math.hypot(item.point[0] - p[0], item.point[1] - p[1]);
      if (d <= bestDistance) {
        best = item;
        bestDistance = d;
      }
    };
    // Очень мелкий масштаб: ячеек больше, чем точек, — проще перебрать все.
    if ((x1 - x0 + 1) * (y1 - y0 + 1) > this.items.length) {
      for (const item of this.items) consider(item);
      return best;
    }
    for (let cx = x0; cx <= x1; cx += 1) {
      for (let cy = y0; cy <= y1; cy += 1) for (const at of this.grid.get(`${cx}:${cy}`) ?? []) consider(this.items[at]);
    }
    return best;
  }
}

/**
 * Привязка курсора: конец линии, пересечение, вершина, ближайшая точка — в
 * таком порядке важности (как объектная привязка САПР). Сегменты разложены по
 * ячейкам, чтобы движение мыши над чертежом с тысячами линий не перебирало все.
 */
// Ячеек сетки на все отрезки — порядка этого числа: ячейка 5 м растёт с общей
// длиной линий. Чертёж в миллиметрах, где масштаб 0,001 ещё не применён,
// иначе дал бы миллионы ячеек, и окно зависло бы.
const MAX_SNAP_CELLS = 200_000;

export class SnapIndex {
  /** Сторона ячейки: не меньше заданной, у длинных линий — больше. */
  readonly cell: number;
  private readonly segments: Segment[] = [];
  private readonly grid = new Map<string, number[]>();
  private readonly ends = new PointCells<{ point: XY; handle: string; m: number }>();
  private readonly vertices = new PointCells<{ point: XY; handle: string; m: number }>();
  private readonly crossings = new PointCells<{ point: XY }>();
  private readonly polylines = new Map<string, XY[]>();

  constructor(lines: CadEntity[], intersections: number[][], cell = 5) {
    for (const entity of lines) {
      if (entity.geometry_type !== "line" || entity.points.length < 2) continue;
      this.polylines.set(entity.handle, polylineXY(entity));
    }
    let total = 0;
    for (const points of this.polylines.values()) {
      for (let index = 1; index < points.length; index += 1) {
        total += Math.hypot(points[index][0] - points[index - 1][0], points[index][1] - points[index - 1][1]);
      }
    }
    this.cell = Math.max(cell, total / MAX_SNAP_CELLS);
    for (const points of [this.ends, this.vertices, this.crossings]) points.cell = this.cell;
    for (const [x, y] of intersections) this.crossings.add({ point: [x, y] });
    for (const entity of lines) {
      const points = this.polylines.get(entity.handle);
      if (!points) continue;
      let walked = 0;
      points.forEach((point, index) => {
        const isEnd = !entity.closed && (index === 0 || index === points.length - 1);
        (isEnd ? this.ends : this.vertices).add({ point, handle: entity.handle, m: walked });
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

  /** Ячейки, которые отрезок действительно пересекает (обход сетки Amanatides–Woo), —
   * а не весь его габарит: диагональ в 5 км иначе дала бы миллион ячеек. */
  private cellsOf(a: XY, b: XY): Array<[number, number]> {
    let cx = Math.floor(a[0] / this.cell);
    let cy = Math.floor(a[1] / this.cell);
    const ex = Math.floor(b[0] / this.cell);
    const ey = Math.floor(b[1] / this.cell);
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const stepX = Math.sign(dx);
    const stepY = Math.sign(dy);
    const tDeltaX = dx ? this.cell / Math.abs(dx) : Infinity;
    const tDeltaY = dy ? this.cell / Math.abs(dy) : Infinity;
    let tMaxX = dx ? ((stepX > 0 ? (cx + 1) * this.cell - a[0] : a[0] - cx * this.cell) / Math.abs(dx)) : Infinity;
    let tMaxY = dy ? ((stepY > 0 ? (cy + 1) * this.cell - a[1] : a[1] - cy * this.cell) / Math.abs(dy)) : Infinity;
    const cells: Array<[number, number]> = [[cx, cy]];
    const limit = Math.abs(ex - cx) + Math.abs(ey - cy);
    for (let step = 0; step < limit && (cx !== ex || cy !== ey); step += 1) {
      if (tMaxX < tMaxY) {
        cx += stepX;
        tMaxX += tDeltaX;
      } else {
        cy += stepY;
        tMaxY += tDeltaY;
      }
      cells.push([cx, cy]);
    }
    return cells;
  }

  private add(segment: Segment) {
    const at = this.segments.push(segment) - 1;
    for (const [cx, cy] of this.cellsOf(segment.a, segment.b)) {
      const key = this.key(cx, cy);
      const list = this.grid.get(key);
      if (list) list.push(at);
      else this.grid.set(key, [at]);
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
    const closest = <T extends { point: XY }>(cells: PointCells<T>): T | undefined => cells.nearest(p, aperture);

    // Ближайшая линия под курсором — и для привязки «ближайшая точка», и как
    // линия пересечения: «Участок» рядом с узлом должен знать, по какой линии щёлкнули.
    let nearest: { segment: Segment; point: XY; distance: number; m: number } | null = null;
    for (const segment of this.nearSegments(p, aperture)) {
      const hit = projectOnPolyline([segment.a, segment.b], p);
      if (hit.distance <= aperture && (!nearest || hit.distance < nearest.distance)) {
        nearest = { segment, point: hit.point, distance: hit.distance, m: segment.startM + hit.m };
      }
    }

    // Привязка уточняет точку, а линию задаёт курсор: в общем узле двух бровок
    // конец «чужой» линии не должен подменять ту, по которой щёлкнули.
    const onLine = (point: XY, kind: SnapKind, fallback?: { handle: string; m: number }): Snap => {
      if (nearest) {
        const handle = nearest.segment.handle;
        return { point, kind, handle, m: projectOnPolyline(this.polylines.get(handle) ?? [nearest.segment.a, nearest.segment.b], point).m };
      }
      return fallback ? { point, kind, ...fallback } : { point, kind };
    };

    const end = closest(this.ends);
    if (end) return onLine(end.point, "end", { handle: end.handle, m: end.m });
    const crossing = closest(this.crossings);
    if (crossing) return onLine(crossing.point, "intersection");
    const vertex = closest(this.vertices);
    if (vertex) return onLine(vertex.point, "vertex", { handle: vertex.handle, m: vertex.m });
    return nearest ? { point: nearest.point, kind: "nearest", handle: nearest.segment.handle, m: nearest.m } : null;
  }
}
