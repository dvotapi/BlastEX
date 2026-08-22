// Чистая математика чертежей скважины: шкала глубин, ширина ствола, тултипы.

import { ruNumber } from "../../lib/format";

export type Vec2 = { x: number; y: number };

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** Шаг делений шкалы глубин: не мельче ~26 px между рисками. */
export function depthTickStep(rangeM: number, pxPerM: number): number {
  const candidates = [0.25, 0.5, 1, 2, 2.5, 5, 10, 20, 25, 50];
  const minPx = 26;
  for (const step of candidates) {
    if (step * pxPerM >= minPx) return step;
  }
  return candidates[candidates.length - 1] ?? Math.max(1, rangeM / 10);
}

/** Деления шкалы от `fromM` до `toM` включительно, выровненные по шагу. */
export function depthTicks(fromM: number, toM: number, stepM: number): number[] {
  if (stepM <= 0) return [];
  const ticks: number[] = [];
  const start = Math.ceil(fromM / stepM - 1e-9) * stepM;
  for (let v = start; v <= toM + 1e-9; v += stepM) {
    ticks.push(Math.round(v * 1e6) / 1e6);
  }
  return ticks;
}

/** «Круглая» длина масштабной линейки, ближайшая к целевой длине в пикселях. */
export function niceScaleBarM(pxPerM: number, targetPx = 110): number {
  const raw = targetPx / pxPerM;
  const magnitude = Math.pow(10, Math.floor(Math.log10(Math.max(1e-6, raw))));
  for (const step of [1, 2, 2.5, 5, 10]) {
    if (step * magnitude >= raw) return step * magnitude;
  }
  return 10 * magnitude;
}

/**
 * Во сколько раз диаметр скважины на чертеже крупнее натурального.
 * Диаметр 0,15 м при масштабе всего уступа не виден вовсе, поэтому его
 * преувеличивают — но коэффициент должен быть один на весь чертёж и указан
 * на нём, иначе чертёж вводит в заблуждение.
 */
export function exaggerationFactor(
  maxDiameterM: number,
  pxPerM: number,
  targetPx: number,
  /** Предел ширины ствола, чтобы соседние скважины не сливались в сплошную стену. */
  maxWidthPx = Number.POSITIVE_INFINITY,
): number {
  if (maxDiameterM <= 0 || pxPerM <= 0) return 1;
  const natural = maxDiameterM * pxPerM;
  const capped = Math.min(targetPx, maxWidthPx);
  return Math.max(1, Math.round(capped / natural));
}

/**
 * Уровень детализации подписей по плотности скважин на экране: при тесной
 * расстановке подписи сливаются в кашу, поэтому часть из них скрывается,
 * а номера прореживаются.
 */
export function labelDetail(spacingPx: number): {
  showId: boolean;
  showMeta: boolean;
  showMass: boolean;
  showPrimerLabels: boolean;
  idEvery: number;
} {
  return {
    showId: spacingPx >= 16,
    showMeta: spacingPx >= 62,
    showMass: spacingPx >= 46,
    showPrimerLabels: spacingPx >= 54,
    idEvery: spacingPx >= 30 ? 1 : Math.max(1, Math.ceil(30 / Math.max(1, spacingPx))),
  };
}

/**
 * Ширина ствола на чертеже. Диаметр скважины (0,1–0,3 м) на фоне уступа в 10 м
 * в масштабе не виден, поэтому ширина преувеличена, но остаётся пропорциональной
 * диаметру — скважины разных диаметров различимы между собой.
 */
export function barrelWidthPx(diameterMm: number, opts?: { min?: number; max?: number; base?: number }): number {
  const min = opts?.min ?? 7;
  const max = opts?.max ?? 22;
  const base = opts?.base ?? 152;
  const ratio = diameterMm > 0 ? diameterMm / base : 1;
  return clamp(min + (max - min) * clamp((ratio - 0.5) / 1.5, 0, 1), min, max);
}

/** Единичный вектор вдоль оси скважины на экране (сверху вниз). */
export function axisDir(collar: Vec2, toe: Vec2): Vec2 {
  const dx = toe.x - collar.x;
  const dy = toe.y - collar.y;
  const len = Math.hypot(dx, dy) || 1;
  return { x: dx / len, y: dy / len };
}

/** Нормаль к оси скважины (вправо от направления бурения). */
export function axisNormal(dir: Vec2): Vec2 {
  return { x: -dir.y, y: dir.x };
}

/** Четырёхугольник участка ствола между двумя точками оси заданной ширины. */
export function barrelSegmentPath(a: Vec2, b: Vec2, widthPx: number): string {
  const dir = axisDir(a, b);
  const n = axisNormal(dir);
  const h = widthPx / 2;
  const p1 = { x: a.x + n.x * h, y: a.y + n.y * h };
  const p2 = { x: b.x + n.x * h, y: b.y + n.y * h };
  const p3 = { x: b.x - n.x * h, y: b.y - n.y * h };
  const p4 = { x: a.x - n.x * h, y: a.y - n.y * h };
  return `M${p1.x} ${p1.y} L${p2.x} ${p2.y} L${p3.x} ${p3.y} L${p4.x} ${p4.y} Z`;
}

/** Ось скважины на экране: перевод «метры от устья» → точка чертежа. */
export type HoleAxis = {
  collar: Vec2;
  toe: Vec2;
  lengthM: number;
  widthPx: number;
  dir: Vec2;
  normal: Vec2;
  at: (depthM: number) => Vec2;
};

export function makeAxis(collar: Vec2, toe: Vec2, lengthM: number, widthPx: number): HoleAxis {
  const dir = axisDir(collar, toe);
  const normal = axisNormal(dir);
  const pxPerM = lengthM > 0 ? Math.hypot(toe.x - collar.x, toe.y - collar.y) / lengthM : 0;
  return {
    collar,
    toe,
    lengthM,
    widthPx,
    dir,
    normal,
    at: (depthM: number) => ({
      x: collar.x + dir.x * depthM * pxPerM,
      y: collar.y + dir.y * depthM * pxPerM,
    }),
  };
}

export const DECK_TITLE: Record<string, string> = {
  charge: "Заряд",
  stemming: "Забойка",
  air: "Возд. промежуток",
};

/** Текст подсказки по деке: «Заряд 3,0–11,0 м · 8,0 м · 160 кг · ЭВЕРСИН Э-100». */
export function deckTooltip(deck: {
  kind: string;
  from_m: number;
  to_m: number;
  mass_kg: number;
  explosive_key: string;
}): string {
  const parts = [
    `${DECK_TITLE[deck.kind] ?? deck.kind} ${ruNumber(deck.from_m, 1)}–${ruNumber(deck.to_m, 1)} м`,
    `${ruNumber(Math.abs(deck.to_m - deck.from_m), 1)} м`,
  ];
  if (deck.mass_kg > 0) parts.push(`${ruNumber(deck.mass_kg, 0)} кг`);
  if (deck.explosive_key) parts.push(deck.explosive_key);
  return parts.join(" · ");
}
