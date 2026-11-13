// Живая проверка сдвига скважин на плане (TASK-017, PR 1) — на клиенте, без
// запроса к серверу. Правила — те же, что у `validate` (`design/analysis.py`)
// и `design/toe_line.py::floor_checks`; после отпускания действует серверная
// проверка, как прежде. Ограничения клиента: ЛСП меряется до линии подошвы с
// плана (`toe_line` пересчёта скважин), без правила развала у съёмки и без
// подошвы по углу для скважины, у которой высота уступа отличается от высоты
// блока (`_angle_points`), и без признака «за подошвой».
import { projectOnSegment, type Vec2 } from "../../lib/geometry2d";
import { ruNumber } from "../../lib/format";
import type { BlockContour, Hole, PatternParams, ToeLine } from "../../types/design";
import { facePairPartnerId, gridSteps, isSquareGrid } from "./holeMove";

type Params = Partial<PatternParams> | Record<string, unknown> | null | undefined;

// Допуск ЛСП сверху — W + 3 % (`TOE_BURDEN_TOLERANCE`).
export const TOE_BURDEN_TOLERANCE = 0.03;
// Коридор «закрыт соседом» (`shadow_limits`, `SHADOW_ADVANCE_TOLERANCE_M`).
const SHADOW_ADVANCE_RATIO = 0.4;
const SHADOW_REACH_RATIO = 1.05;
const SHADOW_ADVANCE_TOLERANCE_M = 1e-6;
// Отступ устья от кромки без ключа (`MIN_CREST_OFFSET_DEFAULT_M`).
export const MIN_CREST_OFFSET_DEFAULT_M = 0.2;
// Сосед ближе этой доли меньшего шага сетки — нарушение.
export const NEIGHBOUR_MIN_RATIO = 0.5;
// Ряды: ниже этого номера — ряды впереди первого; −1000 — ручные (`FRONT_ROW_BASE`).
const FRONT_ROW_BASE = -1000;
const OWN_ROW_FAMILY_KINDS = new Set(["contour", "presplit", "trim", "buffer"]);

function positive(value: unknown): number | null {
  const number = typeof value === "number" ? value : typeof value === "string" && value !== "" ? Number(value) : NaN;
  return Number.isFinite(number) && number > 0 ? number : null;
}

/** Проектная W — порт `design_burden_m`; null — не задана. */
export function designBurdenM(params: Params): number | null {
  const p = (params ?? {}) as Record<string, unknown>;
  const keys = isSquareGrid(p) ? ["spacing_a_m", "burden_b_m"] : ["burden_b_m"];
  if (!keys.some((key) => positive(p[key]) !== null)) return null;
  return gridSteps(p).b;
}

/** Допустимая ЛСП сверху: W · (1 + 3 %); null — W не задана. */
export function allowedFloorBurdenM(params: Params): number | null {
  const w = designBurdenM(params);
  return w === null ? null : w * (1 + TOE_BURDEN_TOLERANCE);
}

/** Минимальный отступ устья от кромки — порт `min_crest_offset_m`. */
export function minCrestOffsetM(params: Params): number {
  const raw = (params as Record<string, unknown> | null | undefined)?.min_crest_offset_m;
  if (raw === undefined || raw === null || raw === "") return MIN_CREST_OFFSET_DEFAULT_M;
  const value = Number(raw);
  return Number.isFinite(value) ? Math.max(0, value) : MIN_CREST_OFFSET_DEFAULT_M;
}

function mainGridKind(params: Params): string {
  const raw = (params as Record<string, unknown> | null | undefined)?.default_kind;
  const kind = String(raw ?? "").trim().toLowerCase();
  return kind || "production";
}

function rowFamily(kind: string): string {
  return OWN_ROW_FAMILY_KINDS.has(kind) ? kind : "grid";
}

function isLatticeHole(hole: Hole): boolean {
  return hole.source !== "manual" && hole.kind !== "face_toe" && (hole.row >= 0 || hole.row < FRONT_ROW_BASE);
}

/** Член основной сетки для проверок у подошвы и кромки — `models.in_main_grid`. */
export function inMainGrid(hole: Hole): boolean {
  return rowFamily(hole.kind) === "grid" || isLatticeHole(hole);
}

function measured(hole: Hole, mainKind: string): boolean {
  if (hole.kind === "production" || hole.kind === mainKind) return true;
  return rowFamily(hole.kind) !== "grid" && isLatticeHole(hole);
}

/** Точка оси на уровне подошвы: забой минус перебор вдоль оси, в плане (`floor_point`). */
export function floorPoint(hole: Hole): Vec2 {
  const dx = hole.toe.x - hole.collar.x;
  const dy = hole.toe.y - hole.collar.y;
  const dz = hole.toe.z - hole.collar.z;
  const length = Math.sqrt(dx * dx + dy * dy + dz * dz);
  if (length <= 0) return { x: hole.toe.x, y: hole.toe.y };
  const k = hole.subdrill_m / length;
  return { x: hole.toe.x - dx * k, y: hole.toe.y - dy * k };
}

type Segment = [Vec2, Vec2];

function nearestOnSegments(p: Vec2, segments: Segment[]): { distance: number; point: Vec2 } | null {
  let best: { distance: number; point: Vec2 } | null = null;
  for (const [a, b] of segments) {
    const projection = projectOnSegment(p, a, b);
    if (!best || projection.distance < best.distance) best = { distance: projection.distance, point: projection.point };
  }
  return best;
}

function toeSegments(toeLine: ToeLine): Segment[] {
  const segments: Segment[] = [];
  for (const line of toeLine.polylines ?? []) {
    for (let i = 0; i + 1 < line.length; i += 1) {
      segments.push([{ x: line[i][0], y: line[i][1] }, { x: line[i + 1][0], y: line[i + 1][1] }]);
    }
  }
  return segments;
}

/** Верхняя бровка — рёбра свободных поверхностей контура (`crest_geometry`). */
function crestSegments(contour: BlockContour): Segment[] {
  const verts = contour.vertices;
  const segments: Segment[] = [];
  for (const edge of contour.free_faces ?? []) {
    for (let k = 0; k + 1 < edge.length; k += 1) {
      const a = verts[edge[k]];
      const b = verts[edge[k + 1]];
      if (a && b) segments.push([a, b]);
    }
  }
  return segments;
}

function pointInPolygon(p: Vec2, polygon: Vec2[]): boolean {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    const a = polygon[i];
    const b = polygon[j];
    if (a.y > p.y !== b.y > p.y && p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}

export type LiveFloorBurden = { valueM: number; allowedM: number | null; excess: boolean };

/**
 * ЛСП включённых скважин основной сетки и пар у откоса — порт `floor_burdens`
 * по линии подошвы с плана: расстояние в плане от точки оси на подошве до
 * линии; скважину, перед которой в коридоре к подошве стоит другая скважина
 * сетки (продвижение ≥ 0,4·min(a, b) и меньше ЛСП, отступ вбок ≤ 1,05·max(a, b)),
 * закрывает сосед — ЛСП у неё нет. Пара у откоса закрывает только свою вертикальную.
 */
export function liveFloorBurdens(
  holes: Hole[],
  toeLine: ToeLine | null | undefined,
  params: Params,
): Record<string, LiveFloorBurden> {
  const segments = toeLine ? toeSegments(toeLine) : [];
  if (!segments.length) return {};
  const grid = holes.filter((h) => h.enabled && inMainGrid(h));
  if (!grid.length) return {};
  const mainKind = mainGridKind(params);
  const allowed = allowedFloorBurdenM(params);
  const { a, b } = gridSteps(params);
  const minAdvance = SHADOW_ADVANCE_RATIO * Math.min(a, b);
  const reach = SHADOW_REACH_RATIO * Math.max(a, b);
  const points = grid.map(floorPoint);
  const paired = new Set<string>();
  for (const h of grid) {
    const partner = facePairPartnerId(h);
    if (partner !== null) paired.add(partner);
  }
  const result: Record<string, LiveFloorBurden> = {};
  grid.forEach((hole, i) => {
    if (!(measured(hole, mainKind) || hole.kind === "face_toe") || paired.has(hole.id)) return;
    const nearest = nearestOnSegments(points[i], segments);
    if (!nearest) return;
    const value = nearest.distance;
    if (value > 0) {
      const p = points[i];
      const dx = (nearest.point.x - p.x) / value;
      const dy = (nearest.point.y - p.y) / value;
      const blocked = grid.some((other, j) => {
        if (j === i || other.kind === "face_toe") return false;
        const vx = points[j].x - p.x;
        const vy = points[j].y - p.y;
        const advance = vx * dx + vy * dy;
        const lateral = Math.abs(vx * dy - vy * dx);
        return advance >= minAdvance - SHADOW_ADVANCE_TOLERANCE_M && advance < value && lateral <= reach;
      });
      if (blocked) return;
    }
    // Допуск 1 мкм — как у сервера (ошибка округления не даёт превышения).
    result[hole.id] = { valueM: value, allowedM: allowed, excess: allowed !== null && value > allowed + 1e-6 };
  });
  return result;
}

export type LiveViolationCode =
  | "floor_burden_excess"
  | "neighbour_too_close"
  | "collar_too_close_to_crest"
  | "hole_outside_contour";

export type LiveViolation = { code: LiveViolationCode; text: string };

export type LiveCheckResult = {
  /** Нарушения по скважинам; скважин без нарушений в словаре нет. */
  byHole: Record<string, LiveViolation[]>;
  /** Расстояние от сдвигаемых до ближайшей другой скважины (пара своей вертикальной — не сосед), м. */
  nearestM: number | null;
  /** ЛСП после сдвига. */
  burdens: Record<string, LiveFloorBurden>;
};

function metres(value: number, digits = 2): string {
  return ruNumber(value, digits);
}

function offsetLabel(value: number): string {
  // Как у сервера: «0,2», «0,25», «1» — без хвостовых нулей.
  return value.toFixed(2).replace(/\.?0+$/, "").replace(".", ",");
}

/**
 * Нарушения при сдвиге скважин `moved`: ЛСП > W + 3 %, сосед ближе
 * 0,5·min(a, b), устье ближе `min_crest_offset_m` к кромке (у членов сетки,
 * всегда — как в переборе раскладки), устье вне контура. У остальных скважин —
 * только превышение ЛСП, которого не было до сдвига (`base`). Ничего не
 * запрещает: результат только подсвечивается.
 */
export function liveCheck(input: {
  holes: Hole[];
  base: Hole[];
  moved: Set<string>;
  contour: BlockContour;
  toeLine: ToeLine | null | undefined;
  params: Params;
  baseBurdens?: Record<string, LiveFloorBurden>;
}): LiveCheckResult {
  const { holes, moved, contour, toeLine, params } = input;
  const burdens = liveFloorBurdens(holes, toeLine, params);
  const before = input.baseBurdens ?? liveFloorBurdens(input.base, toeLine, params);
  const { a, b } = gridSteps(params);
  const neighbourMin = NEIGHBOUR_MIN_RATIO * Math.min(a, b);
  const crestMin = minCrestOffsetM(params);
  const crest = crestSegments(contour);
  const polygon = contour.vertices.length >= 3 ? contour.vertices : null;
  const byHole: Record<string, LiveViolation[]> = {};
  const add = (id: string, violation: LiveViolation) => {
    (byHole[id] ??= []).push(violation);
  };
  const excessText = (item: LiveFloorBurden) =>
    `ЛСП ${metres(item.valueM)} м больше допустимого ${metres(item.allowedM ?? 0)} м (W + 3 %)`;

  const enabled = holes.filter((h) => h.enabled);
  const pairOf = (h: Hole) => facePairPartnerId(h);
  let nearestM: number | null = null;
  for (const hole of enabled) {
    if (!moved.has(hole.id)) {
      const item = burdens[hole.id];
      if (item?.excess && !before[hole.id]?.excess) add(hole.id, { code: "floor_burden_excess", text: excessText(item) });
      continue;
    }
    const item = burdens[hole.id];
    if (item?.excess) add(hole.id, { code: "floor_burden_excess", text: excessText(item) });

    let nearest = Infinity;
    for (const other of enabled) {
      if (other.id === hole.id || pairOf(other) === hole.id || pairOf(hole) === other.id) continue;
      nearest = Math.min(nearest, Math.hypot(other.collar.x - hole.collar.x, other.collar.y - hole.collar.y));
    }
    if (Number.isFinite(nearest)) {
      nearestM = nearestM === null ? nearest : Math.min(nearestM, nearest);
      if (nearest < neighbourMin) {
        add(hole.id, {
          code: "neighbour_too_close",
          text: `До соседа ${metres(nearest)} м — меньше 0,5·min(a, b) = ${metres(neighbourMin)} м`,
        });
      }
    }

    if (crest.length && inMainGrid(hole)) {
      const toCrest = nearestOnSegments(hole.collar, crest);
      if (toCrest && toCrest.distance < crestMin - 1e-6) {
        add(hole.id, { code: "collar_too_close_to_crest", text: `Устье ближе ${offsetLabel(crestMin)} м к кромке уступа` });
      }
    }

    if (polygon && !pointInPolygon(hole.collar, polygon)) {
      add(hole.id, { code: "hole_outside_contour", text: "Устье вне контура блока" });
    }
  }
  return { byHole, nearestM, burdens };
}
