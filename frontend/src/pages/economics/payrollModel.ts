/**
 * Вид разбивки ФОТ по методике: подпись доли в марже и геометрия графика
 * шкалы. Чистые функции без DOM — рисует их компонент.
 */
import type { PayrollMargin, PayrollScale, PayrollSeriesPoint } from "../../types/blockEconomics";
import { amount, percent } from "./format";

export type ShareView = { label: string; value: string; tone: "ok" | "warn" | "muted" };

const NOT_SHOWN: Record<string, string> = {
  NOT_CHECKED: "доля не проверена: нет цены метра",
  NO_MARGIN: "доля не проверена: нет маржи метра",
  NOT_APPLICABLE: "доля не проверена: в экипаже нет сдельщика со шкалой",
};

/** Доля экипажа в марже: на потолке шкалы, а без потолка («Ступени») — при плановом темпе. */
export function shareView(margin: PayrollMargin): ShareView {
  const point = margin.ceiling ?? margin.plan;
  if (margin.status !== "CHECKED" || !point || !Number.isFinite(point.crew_share)) {
    return { label: "Доля в марже", value: NOT_SHOWN[margin.status] ?? "доля не проверена", tone: "muted" };
  }
  return {
    label: margin.ceiling ? "на потолке" : "при плановом темпе",
    value: percent(point.crew_share),
    tone: point.crew_share > margin.threshold ? "warn" : "ok",
  };
}

export type Tick = { value: number; pos: number; label: string };
export type Marker = { x: number; y: number; value: number };
export type ChartGeometry = {
  ratePath: string;
  perShiftPath: string;
  xAxis: Tick[];
  yAxis: Tick[];
  markers: { norm: Marker | null; ceiling: Marker | null; pace: Marker };
};

/** Круглые деления оси от 0 до `max` (последнее не меньше `max`). */
function niceTicks(max: number, count = 5): number[] {
  if (!(max > 0)) return [0, 1];
  const rough = max / count;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = ([1, 2, 5, 10].find((m) => m * magnitude >= rough) ?? 10) * magnitude;
  const ticks: number[] = [];
  for (let value = 0; value < max + step * 0.999; value += step) {
    ticks.push(Number(value.toFixed(10)));
    if (value >= max) break;
  }
  return ticks;
}

export function chartGeometry(
  series: PayrollSeriesPoint[],
  scale: PayrollScale,
  pace: number,
  size: { width: number; height: number; padding: number },
): ChartGeometry | null {
  if (series.length < 2) return null;
  const points = [...series].sort((a, b) => a.pace - b.pace);
  const { norm_per_shift: norm, ceiling_per_shift: ceiling } = scale;

  const xTicks = niceTicks(Math.max(...points.map((p) => p.pace), norm ?? 0, ceiling ?? 0, pace));
  const yTicks = niceTicks(Math.max(...points.map((p) => p.rate), scale.rate_ceiling ?? 0, scale.rate_norm ?? 0));
  const xMax = xTicks[xTicks.length - 1] || 1;
  const yMax = yTicks[yTicks.length - 1] || 1;
  const perShiftMax = Math.max(...points.map((p) => p.per_shift)) || 1;

  const innerW = size.width - 2 * size.padding;
  const innerH = size.height - 2 * size.padding;
  const x = (value: number) => size.padding + (value / xMax) * innerW;
  const y = (value: number) => size.height - size.padding - (value / yMax) * innerH;
  const yShift = (value: number) => size.height - size.padding - (value / perShiftMax) * innerH;
  const path = (project: (p: PayrollSeriesPoint) => number) =>
    points.map((p, i) => `${i === 0 ? "M" : "L"}${x(p.pace).toFixed(2)},${project(p).toFixed(2)}`).join(" ");

  /** Ставка на темпе: линейно между узлами ряда, за краями — крайнее значение. */
  const rateAt = (at: number) => {
    if (at <= points[0].pace) return points[0].rate;
    for (let i = 1; i < points.length; i += 1) {
      if (at <= points[i].pace) {
        const [a, b] = [points[i - 1], points[i]];
        return b.pace === a.pace ? b.rate : a.rate + ((b.rate - a.rate) * (at - a.pace)) / (b.pace - a.pace);
      }
    }
    return points[points.length - 1].rate;
  };
  const marker = (at: number, rate: number): Marker => ({ x: x(at), y: y(rate), value: at });

  return {
    ratePath: path((p) => y(p.rate)),
    perShiftPath: path((p) => yShift(p.per_shift)),
    xAxis: xTicks.map((value) => ({ value, pos: x(value), label: amount(value) })),
    yAxis: yTicks.map((value) => ({ value, pos: y(value), label: amount(value) })),
    markers: {
      norm: norm != null ? marker(norm, scale.rate_norm ?? rateAt(norm)) : null,
      ceiling: ceiling != null ? marker(ceiling, scale.rate_ceiling ?? rateAt(ceiling)) : null,
      pace: marker(pace, rateAt(pace)),
    },
  };
}

/**
 * Ярус подписи над графиком для каждой вертикальной отметки: близкие по x
 * подписи уходят на ярус выше, чтобы не наезжать друг на друга.
 */
export function labelLevels(xs: number[], minGap: number): number[] {
  const levels: number[] = new Array(xs.length).fill(0);
  const lastX: number[] = [];
  xs
    .map((x, index) => ({ x, index }))
    .sort((a, b) => a.x - b.x)
    .forEach(({ x, index }) => {
      let level = 0;
      while (lastX[level] !== undefined && x - lastX[level] < minGap) level += 1;
      lastX[level] = x;
      levels[index] = level;
    });
  return levels;
}
