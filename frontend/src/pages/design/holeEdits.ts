// Правки скважины руками из карточки и таблицы (TASK-013, PR 3): своя длина
// и своя отметка устья помечаются «вручную» — автопересчёт по кровле их не
// затирает. Угол и азимут пересчёт сохраняет сам, пометки не нужно.
import { angleAzimuth, holeFromCollar, holeLength } from "../../lib/geometry2d";
import type { Hole, HoleManualFlag } from "../../types/design";

/** Ручные пометки скважины с новой. */
export function withManual(hole: Hole, flag: HoleManualFlag): HoleManualFlag[] {
  const current = hole.manual ?? [];
  return current.includes(flag) ? current : [...current, flag];
}

/** Правка оси: глубина — ручная длина, угол и азимут — без пометки. */
export function axisPatch(hole: Hole, next: { depth?: number; angle?: number; azimuth?: number }): Partial<Hole> {
  const current = angleAzimuth(hole.collar, hole.toe);
  const depth = next.depth ?? holeLength(hole.collar, hole.toe);
  const angle = next.angle ?? current.angleDeg;
  const azimuth = next.azimuth ?? current.azimuthDeg;
  const manual = next.depth !== undefined ? { manual: withManual(hole, "length") } : {};
  return { toe: holeFromCollar(hole.collar, depth, angle, azimuth), ...manual };
}

/** Правка координаты забоя — ручная длина. */
export function toePatch(hole: Hole, axis: "x" | "y" | "z", value: number): Partial<Hole> {
  return { toe: { ...hole.toe, [axis]: value }, manual: withManual(hole, "length") };
}

/** Отметка устья руками: скважина сдвигается по вертикали целиком, ось та же. */
export function collarZPatch(hole: Hole, z: number): Partial<Hole> {
  const dz = z - hole.collar.z;
  return {
    collar: { ...hole.collar, z },
    toe: { ...hole.toe, z: hole.toe.z + dz },
    manual: withManual(hole, "collar_z"),
  };
}
