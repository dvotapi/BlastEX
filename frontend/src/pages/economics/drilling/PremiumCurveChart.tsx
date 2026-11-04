/**
 * График шкалы сдельной премии машиниста на панели цены метра: цена
 * приведённого метра r(m) от темпа. Сплошная линия — шкала с пробными
 * значениями, пунктир — шкала справочника (видна, пока ручки премии сдвинуты);
 * отметки — норма, потолок и плановый темп блока. Оси общие для обеих линий,
 * чтобы сдвиг ручки был виден как сдвиг кривой, а не перерисовка осей.
 */
import type { DrillingPremiumCurve, PayrollSeriesPoint } from "../../../types/blockEconomics";
import { amount } from "../format";
import { labelLevels, niceTicks } from "../payrollModel";

const SIZE = { width: 520, height: 230, padding: 34 };
/** Справа места больше: подписи правой оси. */
const RIGHT_PAD = 46;
const LABEL_GAP = 70;

type Axis = {
  x: (value: number) => number;
  y: (value: number) => number;
  /** Правая ось — премия за смену, ₽. */
  y2: (value: number) => number;
  xTicks: number[];
  yTicks: number[];
  y2Ticks: number[];
};

function sorted(series: PayrollSeriesPoint[]): PayrollSeriesPoint[] {
  return [...series].sort((a, b) => a.pace - b.pace);
}

/** Общие оси двух кривых: максимум по обоим рядам, узлам шкал и темпу. */
export function curveAxes(current: DrillingPremiumCurve, base: DrillingPremiumCurve | null): Axis {
  const curves = base ? [current, base] : [current];
  const xMax = Math.max(
    ...curves.flatMap((c) => [...c.series.map((p) => p.pace), c.scale.norm_per_shift ?? 0, c.scale.ceiling_per_shift ?? 0, c.pace ?? 0]),
  );
  const yMax = Math.max(...curves.flatMap((c) => [...c.series.map((p) => p.rate), c.scale.rate_ceiling ?? 0, c.scale.rate_norm ?? 0]));
  const y2Max = Math.max(...curves.flatMap((c) => c.series.map((p) => p.per_shift)));
  const xTicks = niceTicks(xMax, 4);
  const yTicks = niceTicks(yMax, 4);
  const y2Ticks = niceTicks(y2Max, 4);
  const innerW = SIZE.width - SIZE.padding - RIGHT_PAD;
  const innerH = SIZE.height - 2 * SIZE.padding;
  const xTop = xTicks[xTicks.length - 1] || 1;
  const yTop = yTicks[yTicks.length - 1] || 1;
  const y2Top = y2Ticks[y2Ticks.length - 1] || 1;
  return {
    x: (value) => SIZE.padding + (value / xTop) * innerW,
    y: (value) => SIZE.height - SIZE.padding - (value / yTop) * innerH,
    y2: (value) => SIZE.height - SIZE.padding - (value / y2Top) * innerH,
    xTicks,
    yTicks,
    y2Ticks,
  };
}

/** Путь r(m): у ступеней — скачок на узле, у кривых — ломаная по точкам ряда. */
export function ratePath(curve: DrillingPremiumCurve, axis: Axis): string {
  const points = sorted(curve.series);
  if (points.length === 0) return "";
  const at = (p: PayrollSeriesPoint, rate = p.rate) => `${axis.x(p.pace).toFixed(2)},${axis.y(rate).toFixed(2)}`;
  if (curve.scale.scale_type !== "STEP") return points.map((p, i) => `${i === 0 ? "M" : "L"}${at(p)}`).join(" ");
  const parts = [`M${at(points[0])}`];
  for (let i = 1; i < points.length; i += 1) {
    const [a, b] = [points[i - 1], points[i]];
    if (b.rate !== a.rate) parts.push(`L${at(a, b.rate)}`);
    parts.push(`L${at(b)}`);
  }
  return parts.join(" ");
}

/** Путь p(m) по правой оси: премия за смену, ломаная по точкам ряда. */
export function perShiftPath(curve: DrillingPremiumCurve, axis: Axis): string {
  return sorted(curve.series)
    .map((p, i) => `${i === 0 ? "M" : "L"}${axis.x(p.pace).toFixed(2)},${axis.y2(p.per_shift).toFixed(2)}`)
    .join(" ");
}

/** Ставка на темпе: у ступеней — ставка ступени, куда попал темп; у кривых — линейно между точками, за краями — крайняя. */
export function rateAt(curve: DrillingPremiumCurve, pace: number): number {
  const points = sorted(curve.series);
  if (points.length === 0) return 0;
  if (pace <= points[0].pace) return points[0].rate;
  if (curve.scale.scale_type === "STEP") return (points.find((p) => pace <= p.pace) ?? points[points.length - 1]).rate;
  for (let i = 1; i < points.length; i += 1) {
    if (pace <= points[i].pace) {
      const [a, b] = [points[i - 1], points[i]];
      return b.pace === a.pace ? b.rate : a.rate + ((b.rate - a.rate) * (pace - a.pace)) / (b.pace - a.pace);
    }
  }
  return points[points.length - 1].rate;
}

/**
 * Шкала сдвинута ручками премии: отличаются узлы шкалы или ставка в одной и той
 * же точке темпа. Ряды целиком не сравниваются: `scale_series` вставляет в ряд
 * плановый темп и по нему растягивает диапазон, так что одна и та же шкала при
 * другой скорости станка даёт другой ряд. У ступеней расценки ступеней в
 * `scale` не входят — их разница видна по ставкам в общих точках.
 */
export function scaleChanged(base: DrillingPremiumCurve, current: DrillingPremiumCurve): boolean {
  if (JSON.stringify(base.scale) !== JSON.stringify(current.scale)) return true;
  const rates = new Map(base.series.map((point) => [point.pace, point.rate]));
  return current.series.some((point) => {
    const rate = rates.get(point.pace);
    return rate !== undefined && Math.abs(rate - point.rate) > 1e-9;
  });
}

export type PremiumCurveChartProps = {
  current: DrillingPremiumCurve;
  /** Шкала справочника; показывается пунктиром, когда отличается от текущей. */
  base?: DrillingPremiumCurve | null;
  positionName: string;
  /** Шкала не действует (ставки): график приглушён. */
  inactive?: boolean;
};

export function PremiumCurveChart({ current, base, positionName, inactive }: PremiumCurveChartProps) {
  if (current.series.length < 2) return null;
  const changed = base !== null && base !== undefined && scaleChanged(base, current);
  // Темп сдвинула ручка скорости (или плановых смен): справочный темп остаётся серой точкой.
  const paceMoved = base != null && base.pace != null && current.pace != null && Math.abs(base.pace - current.pace) >= 0.05;
  const axis = curveAxes(current, changed ? base : paceMoved ? base : null);
  const { width, height, padding } = SIZE;
  const paceLabel = paceMoved && base?.pace != null ? `темп ${amount(base.pace)} → ${amount(current.pace ?? 0)}` : "темп";
  const markers = [
    current.scale.norm_per_shift != null && { kind: "norm", label: "норма", at: current.scale.norm_per_shift, rate: current.scale.rate_norm ?? rateAt(current, current.scale.norm_per_shift) },
    current.scale.ceiling_per_shift != null && { kind: "ceiling", label: "потолок", at: current.scale.ceiling_per_shift, rate: current.scale.rate_ceiling ?? rateAt(current, current.scale.ceiling_per_shift) },
    current.pace != null && { kind: "pace", label: paceLabel, at: current.pace, rate: rateAt(current, current.pace), withAt: !paceMoved },
  ].filter((item): item is { kind: string; label: string; at: number; rate: number; withAt?: boolean } => Boolean(item));
  const levels = labelLevels(markers.map((m) => axis.x(m.at)), LABEL_GAP);

  return (
    <figure className={`premium-curve${inactive ? " is-inactive" : ""}`}>
      <figcaption className="premium-curve-title">Цена приведённого метра: {positionName}</figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="График шкалы премии машиниста">
        <title>График шкалы премии машиниста</title>
        {axis.yTicks.map((value) => (
          <g key={`y${value}`} className="payroll-chart-tick">
            <line className="payroll-chart-grid" x1={padding} x2={width - RIGHT_PAD} y1={axis.y(value)} y2={axis.y(value)} />
            <text x={padding - 5} y={axis.y(value) + 3} textAnchor="end">{amount(value)}</text>
          </g>
        ))}
        {axis.xTicks.map((value) => (
          <text key={`x${value}`} className="payroll-chart-tick" x={axis.x(value)} y={height - padding + 12} textAnchor="middle">
            {amount(value)}
          </text>
        ))}
        {axis.y2Ticks.map((value) => (
          <text key={`y2${value}`} className="payroll-chart-tick premium-curve-tick-shift" x={width - RIGHT_PAD + 5} y={axis.y2(value) + 3} textAnchor="start">
            {amount(value)}
          </text>
        ))}
        <line className="payroll-chart-axis" x1={padding} x2={width - RIGHT_PAD} y1={height - padding} y2={height - padding} />
        <line className="payroll-chart-axis" x1={padding} x2={padding} y1={padding} y2={height - padding} />
        <line className="payroll-chart-axis" x1={width - RIGHT_PAD} x2={width - RIGHT_PAD} y1={padding} y2={height - padding} />
        <path className="payroll-chart-line payroll-chart-line-shift" d={perShiftPath(current, axis)} data-testid="premium-curve-shift" />
        {changed && base && <path className="payroll-chart-line premium-curve-base" d={ratePath(base, axis)} data-testid="premium-curve-base" />}
        <path className="payroll-chart-line payroll-chart-line-rate" d={ratePath(current, axis)} data-testid="premium-curve-current" />
        {paceMoved && base?.pace != null && (
          <g className="payroll-chart-marker premium-curve-pace-base" data-testid="premium-curve-pace-base">
            <line x1={axis.x(base.pace)} x2={axis.x(base.pace)} y1={padding} y2={height - padding} />
            <circle cx={axis.x(base.pace)} cy={axis.y(rateAt(base, base.pace))} r={3} />
          </g>
        )}
        {markers.map((m, i) => (
          <g key={m.kind} className={`payroll-chart-marker payroll-chart-marker-${m.kind}`}>
            <line x1={axis.x(m.at)} x2={axis.x(m.at)} y1={padding} y2={height - padding} />
            <circle cx={axis.x(m.at)} cy={axis.y(m.rate)} r={3} />
            <text x={axis.x(m.at)} y={padding - 5 - levels[i] * 11} textAnchor="middle">
              {m.label}{m.withAt === false ? "" : ` ${amount(m.at)}`} · {amount(m.rate, 1)} ₽
            </text>
          </g>
        ))}
        <text className="payroll-chart-axis-label" x={(padding + width - RIGHT_PAD) / 2} y={height - 4} textAnchor="middle">темп, прив. м за смену</text>
        <text className="payroll-chart-axis-label" x={width - 8} y={height / 2} textAnchor="middle" transform={`rotate(90 ${width - 8} ${height / 2})`}>
          премия за смену, ₽
        </text>
        <text className="payroll-chart-axis-label" x={10} y={height / 2} textAnchor="middle" transform={`rotate(-90 10 ${height / 2})`}>
          ₽ за прив. метр
        </text>
      </svg>
      <ul className="payroll-chart-legend premium-curve-legend">
        <li><i className="payroll-chart-swatch payroll-chart-swatch-rate" />{changed ? "пробная шкала, ₽ за прив. м" : "₽ за прив. м"}</li>
        {changed && <li><i className="payroll-chart-swatch premium-curve-swatch-base" />справочник</li>}
        <li><i className="payroll-chart-swatch payroll-chart-swatch-shift" />премия за смену, ₽</li>
      </ul>
    </figure>
  );
}
