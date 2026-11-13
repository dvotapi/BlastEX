// Сдвиг скважин на плане в осях раскладки (TASK-017, PR 1): оси «вдоль ряда»
// и «к откосу», привязка к долям шага сетки, стрелки, пара у откоса.
// Только интерактивная геометрия — раскладку по-прежнему строит сервер.
import { localBasis, type Vec2 } from "../../lib/geometry2d";
import type { BlockContour, Hole, PatternParams } from "../../types/design";
import { isSquarePattern } from "./designParams";

/** Шаг привязки по одной оси: выкл, 0,1 м, четверть шага a или b. */
export type AxisSnap = "off" | "0.1" | "a4" | "b4";

export const AXIS_SNAP_OPTIONS: { value: AxisSnap; label: string }[] = [
  { value: "off", label: "выкл" },
  { value: "0.1", label: "0,1 м" },
  { value: "a4", label: "a/4" },
  { value: "b4", label: "b/4" },
];

/** Шаг, на который двигает Alt+стрелка (и стрелка при выключенной привязке), м. */
export const FINE_STEP_M = 0.1;

// Шаг a квадратной сетки без `spacing_a_m` — как `DEFAULT_SQUARE_SPACING_M` сервера.
const DEFAULT_SQUARE_SPACING_M = 5;
type GridParams = Partial<PatternParams> | Record<string, unknown> | null | undefined;

/** Положительное конечное число (как `_positive` сервера); иначе null. */
export function positive(value: unknown): number | null {
  const number = typeof value === "number" ? value : typeof value === "string" && value !== "" ? Number(value) : NaN;
  return Number.isFinite(number) && number > 0 ? number : null;
}

/** Квадратная ли сетка — как `_is_square` сервера (нет ключа или неизвестный вид — квадратная). */
export function isSquareGrid(params: GridParams): boolean {
  return isSquarePattern((params as Record<string, unknown> | null | undefined)?.pattern);
}

/** Шаги сетки (a, b) — порт `design/toe_line.py::grid_steps_m`. */
export function gridSteps(params: GridParams): { a: number; b: number } {
  const p = (params ?? {}) as Record<string, unknown>;
  const a = positive(p.spacing_a_m) ?? DEFAULT_SQUARE_SPACING_M;
  const b = isSquareGrid(p) ? a : positive(p.burden_b_m) ?? a;
  return { a, b };
}

/** Шаг привязки оси, м; 0 — привязки нет. */
export function snapStepM(snap: AxisSnap, steps: { a: number; b: number }): number {
  if (snap === "0.1") return FINE_STEP_M;
  if (snap === "a4") return steps.a / 4;
  if (snap === "b4") return steps.b / 4;
  return 0;
}

export type LayoutAxes = {
  /** Единичный вектор вдоль ряда (азимут рядов, 0° — +Y, по часовой). */
  along: Vec2;
  /** Единичный вектор поперёк ряда; при свободной поверхности — к откосу. */
  across: Vec2;
  /** Есть свободная поверхность и `across` смотрит к откосу. */
  towardFace: boolean;
};

function centroid(points: Vec2[]): Vec2 {
  // Центр масс многоугольника, как `polygon_centroid` сервера.
  let area = 0;
  let cx = 0;
  let cy = 0;
  for (let i = 0; i < points.length; i += 1) {
    const p = points[i];
    const q = points[(i + 1) % points.length];
    const cross = p.x * q.y - q.x * p.y;
    area += cross;
    cx += (p.x + q.x) * cross;
    cy += (p.y + q.y) * cross;
  }
  area /= 2;
  if (points.length < 3 || area === 0) {
    const n = Math.max(1, points.length);
    return { x: points.reduce((s, p) => s + p.x, 0) / n, y: points.reduce((s, p) => s + p.y, 0) / n };
  }
  return { x: cx / (6 * area), y: cy / (6 * area) };
}

/**
 * Оси раскладки. Продвижение рядов «вглубь» — как `design/geometry.py::pattern_origin`:
 * от средней точки вершин свободных поверхностей к центру масс контура; ось
 * «поперёк» — обратная ему, к откосу. Без свободных поверхностей знак — как у
 * `localBasis`, подпись — просто «поперёк».
 */
export function layoutAxes(rowAzimuthDeg: number, contour: BlockContour): LayoutAxes {
  const { rowDir, advanceDir } = localBasis(Number.isFinite(rowAzimuthDeg) ? rowAzimuthDeg : 0);
  const verts = contour.vertices;
  const facePoints: Vec2[] = [];
  for (const edge of contour.free_faces ?? []) {
    for (const index of edge) {
      if (index >= 0 && index < verts.length) facePoints.push(verts[index]);
    }
  }
  if (!facePoints.length) return { along: rowDir, across: advanceDir, towardFace: false };
  const faceRef = {
    x: facePoints.reduce((s, p) => s + p.x, 0) / facePoints.length,
    y: facePoints.reduce((s, p) => s + p.y, 0) / facePoints.length,
  };
  const center = centroid(verts);
  const dot = (center.x - faceRef.x) * advanceDir.x + (center.y - faceRef.y) * advanceDir.y;
  const deep = dot < 0 ? { x: -advanceDir.x, y: -advanceDir.y } : advanceDir;
  return { along: rowDir, across: { x: -deep.x, y: -deep.y }, towardFace: true };
}

export function toAxes(delta: Vec2, axes: LayoutAxes): { along: number; across: number } {
  return {
    along: delta.x * axes.along.x + delta.y * axes.along.y,
    across: delta.x * axes.across.x + delta.y * axes.across.y,
  };
}

export function fromAxes(along: number, across: number, axes: LayoutAxes): Vec2 {
  return {
    x: along * axes.along.x + across * axes.across.x,
    y: along * axes.along.y + across * axes.across.y,
  };
}

function round3(v: number): number {
  const r = Math.round(v * 1000) / 1000;
  return Object.is(r, -0) ? 0 : r;
}

function snapTo(value: number, step: number): number {
  return step > 0 ? Math.round(value / step) * step : value;
}

/** Мировой сдвиг, округлённый до миллиметра. */
export function roundDelta(delta: Vec2): Vec2 {
  return { x: round3(delta.x), y: round3(delta.y) };
}

/**
 * Сдвиг перетаскивания в осях раскладки: Shift (`lockAxis`) оставляет только
 * преобладающую ось, каждая ось привязывается к своему шагу (0 — без привязки).
 * Отсчёт — от положения скважины в начале жеста.
 */
export function dragDelta(
  raw: Vec2,
  axes: LayoutAxes,
  opts: { lockAxis: boolean; stepAlong: number; stepAcross: number },
): Vec2 {
  let { along, across } = toAxes(raw, axes);
  if (opts.lockAxis) {
    if (Math.abs(along) >= Math.abs(across)) across = 0;
    else along = 0;
  }
  return roundDelta(fromAxes(snapTo(along, opts.stepAlong), snapTo(across, opts.stepAcross), axes));
}

export type ArrowKey = "ArrowLeft" | "ArrowRight" | "ArrowUp" | "ArrowDown";

// Направление стрелки в мире: план — север вверх, восток вправо.
const ARROW_WORLD: Record<ArrowKey, Vec2> = {
  ArrowUp: { x: 0, y: 1 },
  ArrowDown: { x: 0, y: -1 },
  ArrowRight: { x: 1, y: 0 },
  ArrowLeft: { x: -1, y: 0 },
};

/**
 * Сдвиг стрелкой: по той оси раскладки (±вдоль, ±поперёк), чьё направление на
 * плане ближе к стрелке, на шаг этой оси. При равенстве — вдоль ряда.
 */
export function arrowDelta(key: ArrowKey, axes: LayoutAxes, steps: { along: number; across: number }): Vec2 {
  const dir = ARROW_WORLD[key];
  const alongDot = dir.x * axes.along.x + dir.y * axes.along.y;
  const acrossDot = dir.x * axes.across.x + dir.y * axes.across.y;
  if (Math.abs(alongDot) + 1e-9 >= Math.abs(acrossDot)) {
    return roundDelta(fromAxes(Math.sign(alongDot) * steps.along, 0, axes));
  }
  return roundDelta(fromAxes(0, Math.sign(acrossDot) * steps.across, axes));
}

/** Суффикс номера пары у откоса (`design/models.py::FACE_PAIR_ID_SUFFIX`). */
export const FACE_PAIR_SUFFIX = "T";

/** Номер вертикальной скважины пары у откоса; null — не пара. */
export function facePairPartnerId(hole: Pick<Hole, "id" | "kind">): string | null {
  if (hole.kind !== "face_toe" || !hole.id.endsWith(FACE_PAIR_SUFFIX)) return null;
  return hole.id.slice(0, -FACE_PAIR_SUFFIX.length) || null;
}

/**
 * Скважины сдвига: к каждой вертикальной добавляется её пара у откоса
 * (`<id>T`, вид «Наклонная у откоса»). Пара, выбранная одна, едет одна.
 */
export function withFacePairs(ids: string[], holes: Hole[]): string[] {
  const pairs = new Map<string, string>();
  for (const h of holes) {
    const partner = facePairPartnerId(h);
    if (partner !== null) pairs.set(partner, h.id);
  }
  const result: string[] = [];
  const seen = new Set<string>();
  const push = (id: string) => {
    if (seen.has(id)) return;
    seen.add(id);
    result.push(id);
  };
  for (const id of ids) {
    push(id);
    const pair = pairs.get(id);
    if (pair !== undefined) push(pair);
  }
  return result;
}
