import { ruNumber } from "../../lib/format";

/** Зоны темпа отбойки по отклонению от медианы: меньше мс/м — фронт быстрее. */
export type ReliefBand = "much_faster" | "faster" | "even" | "slower" | "much_slower";

/** Границы — отклонения от медианы; `from`/`to` = null — край без предела. */
export const RELIEF_BANDS: { id: ReliefBand; from: number | null; to: number | null; color: string }[] = [
  { id: "much_faster", from: null, to: -0.25, color: "#2f6fb3" },
  { id: "faster", from: -0.25, to: -0.1, color: "#7fb2de" },
  { id: "even", from: -0.1, to: 0.1, color: "#3a9d5d" },
  { id: "slower", from: 0.1, to: 0.25, color: "#f0a43a" },
  { id: "much_slower", from: 0.25, to: null, color: "#c0392b" },
];

/**
 * Зона значения. Границы: нижняя включена, верхняя нет для двух быстрых зон
 * (d < −0,25; −0,25 ≤ d < −0,10); «ровно» — −0,10 ≤ d ≤ 0,10; медленные —
 * 0,10 < d ≤ 0,25 и d > 0,25. При нулевой медиане 0 — «ровно», остальное — «медленнее всех».
 */
export function reliefBand(value: number, median: number): ReliefBand {
  if (median === 0) return value === 0 ? "even" : "much_slower";
  const d = value / median - 1;
  if (d < -0.25) return "much_faster";
  if (d < -0.1) return "faster";
  if (d <= 0.1) return "even";
  if (d <= 0.25) return "slower";
  return "much_slower";
}

/** Легенда в мс/м (одна цифра после запятой) для данной медианы. */
export function reliefLegend(median: number): { band: ReliefBand; color: string; label: string }[] {
  const at = (d: number) => ruNumber(median * (1 + d), 1);
  return RELIEF_BANDS.map(({ id, from, to, color }) => {
    let label: string;
    if (from === null) label = `до ${at(to as number)}`;
    else if (to === null) label = `больше ${at(from)}`;
    else label = `${at(from)}–${at(to)}`;
    return { band: id, color, label };
  });
}

/** Разброс темпа в процентах: «7 %»; нет значения — «—». */
export function formatSpread(spread: number | null): string {
  if (spread == null || Number.isNaN(spread)) return "—";
  return `${Math.round(spread * 100)} %`;
}
