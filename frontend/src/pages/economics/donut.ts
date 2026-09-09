/**
 * Геометрия кольцевой диаграммы структуры себестоимости.
 *
 * Строит SVG-путь сегмента кольца по разделам `estimateModel.ts` — без
 * зависимости от React и без библиотек: диаграмма рисуется как обычный
 * `<path>` с готовой строкой `d`.
 */
import type { EstimateGroup, EstimateGroupCode } from "./estimateModel";

export type DonutSegment = {
  code: EstimateGroupCode;
  label: string;
  value: number;
  /** Доля сегмента в общем круге, 0..1. */
  share: number;
  perM3: number | null;
  /** Готовая строка `d` для `<path>`. */
  path: string;
  color: string;
};

/** Палитра концепта — семь цветов по числу разделов, порядок как в `ESTIMATE_GROUPS`. */
export const GROUP_COLORS: Record<EstimateGroupCode, string> = {
  EXPLOSIVES: "#1f7a5c",
  DRILLING: "#3b82f6",
  LABOR: "#f2a93b",
  EQUIPMENT: "#f28c5f",
  FUEL: "#8b7cf6",
  SERVICES: "#5cc4d8",
  FIXED: "#9aa5b1",
};

/** Порог доли, при котором сегмент считается «единственным» — полное кольцо. */
const FULL_CIRCLE_SHARE = 0.9999;

/** Точка на окружности радиуса `radius`, отсчёт от −90° (12 часов) по часовой стрелке. */
function pointAt(radius: number, angleDeg: number): { x: number; y: number } {
  const angleRad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: radius * Math.cos(angleRad), y: radius * Math.sin(angleRad) };
}

/** Путь одного кольцевого полукольца-дуги: внешняя дуга, ребро, внутренняя дуга обратно, замыкание. */
function ringArcPath(outer: number, inner: number, startDeg: number, endDeg: number): string {
  const largeArc = endDeg - startDeg > 180 ? 1 : 0;
  const outerStart = pointAt(outer, startDeg);
  const outerEnd = pointAt(outer, endDeg);
  const innerEnd = pointAt(inner, endDeg);
  const innerStart = pointAt(inner, startDeg);
  return [
    `M ${outerStart.x} ${outerStart.y}`,
    `A ${outer} ${outer} 0 ${largeArc} 1 ${outerEnd.x} ${outerEnd.y}`,
    `L ${innerEnd.x} ${innerEnd.y}`,
    `A ${inner} ${inner} 0 ${largeArc} 0 ${innerStart.x} ${innerStart.y}`,
    "Z",
  ].join(" ");
}

/**
 * Путь сегмента кольца. 360°-дуга (единственный ненулевой раздел) —
 * вырожденный случай: дуга «в саму себя» не рисуется ни в одном SVG-движке
 * и даёт пустой контур, поэтому полный круг делится на два полукольца.
 */
function ringSegmentPath(outer: number, inner: number, startDeg: number, endDeg: number): string {
  if (endDeg - startDeg >= 360 * FULL_CIRCLE_SHARE) {
    const midDeg = startDeg + 180;
    return `${ringArcPath(outer, inner, startDeg, midDeg)} ${ringArcPath(outer, inner, midDeg, endDeg)}`;
  }
  return ringArcPath(outer, inner, startDeg, endDeg);
}

/**
 * Сегменты кольца по разделам сметы: нулевые разделы пропускаются (доля 0 —
 * дуга нулевой длины, которую незачем рисовать), непустые идут по кругу
 * друг за другом в порядке `ESTIMATE_GROUPS`, начиная с 12 часов.
 */
export function donutSegments(groups: EstimateGroup[], radius: number, thickness: number): DonutSegment[] {
  const inner = radius - thickness;
  let angle = 0;
  const segments: DonutSegment[] = [];
  for (const group of groups) {
    if (group.share <= 0) continue;
    const sweep = group.share * 360;
    segments.push({
      code: group.code,
      label: group.label,
      value: group.total,
      share: group.share,
      perM3: group.perM3,
      path: ringSegmentPath(radius, inner, angle, angle + sweep),
      color: GROUP_COLORS[group.code],
    });
    angle += sweep;
  }
  return segments;
}
