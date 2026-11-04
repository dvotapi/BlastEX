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

const SIZE = { width: 360, height: 200, padding: 36 };
const LABEL_GAP = 70;

type Axis = { x: (value: number) => number; y: (value: number) => number; xTicks: number[]; yTicks: number[] };

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
  const xTicks = niceTicks(xMax, 4);
  const yTicks = niceTicks(yMax, 4);
  const innerW = SIZE.width - 2 * SIZE.padding;
  const innerH = SIZE.height - 2 * SIZE.padding;
  const xTop = xTicks[xTicks.length - 1] || 1;
  const yTop = yTicks[yTicks.length - 1] || 1;
  return {
    x: (value) => SIZE.padding + (value / xTop) * innerW,
    y: (value) => SIZE.height - SIZE.padding - (value / yTop) * innerH,
    xTicks,
    yTicks,
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

/** Ставка на темпе: у ступеней — ставка ступени, куда попал темп; у кривых — линейно между точками, за краями — крайняя. */
function rateAt(curve: DrillingPremiumCurve, pace: number): number {
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
  const changed = base !== null && base !== undefined && JSON.stringify(base.scale) !== JSON.stringify(current.scale);
  const axis = curveAxes(current, changed ? base : null);
  const { width, height, padding } = SIZE;
  const markers = [
    current.scale.norm_per_shift != null && { kind: "norm", label: "норма", at: current.scale.norm_per_shift, rate: current.scale.rate_norm ?? rateAt(current, current.scale.norm_per_shift) },
    current.scale.ceiling_per_shift != null && { kind: "ceiling", label: "потолок", at: current.scale.ceiling_per_shift, rate: current.scale.rate_ceiling ?? rateAt(current, current.scale.ceiling_per_shift) },
    current.pace != null && { kind: "pace", label: "темп", at: current.pace, rate: rateAt(current, current.pace) },
  ].filter((item): item is { kind: string; label: string; at: number; rate: number } => Boolean(item));
  const levels = labelLevels(markers.map((m) => axis.x(m.at)), LABEL_GAP);

  return (
    <figure className={`premium-curve${inactive ? " is-inactive" : ""}`}>
      <figcaption className="premium-curve-title">Цена приведённого метра: {positionName}</figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="График шкалы премии машиниста">
        <title>График шкалы премии машиниста</title>
        {axis.yTicks.map((value) => (
          <g key={`y${value}`} className="payroll-chart-tick">
            <line className="payroll-chart-grid" x1={padding} x2={width - padding} y1={axis.y(value)} y2={axis.y(value)} />
            <text x={padding - 5} y={axis.y(value) + 3} textAnchor="end">{amount(value)}</text>
          </g>
        ))}
        {axis.xTicks.map((value) => (
          <text key={`x${value}`} className="payroll-chart-tick" x={axis.x(value)} y={height - padding + 12} textAnchor="middle">
            {amount(value)}
          </text>
        ))}
        <line className="payroll-chart-axis" x1={padding} x2={width - padding} y1={height - padding} y2={height - padding} />
        <line className="payroll-chart-axis" x1={padding} x2={padding} y1={padding} y2={height - padding} />
        {changed && base && <path className="payroll-chart-line premium-curve-base" d={ratePath(base, axis)} data-testid="premium-curve-base" />}
        <path className="payroll-chart-line payroll-chart-line-rate" d={ratePath(current, axis)} data-testid="premium-curve-current" />
        {markers.map((m, i) => (
          <g key={m.kind} className={`payroll-chart-marker payroll-chart-marker-${m.kind}`}>
            <line x1={axis.x(m.at)} x2={axis.x(m.at)} y1={padding} y2={height - padding} />
            <circle cx={axis.x(m.at)} cy={axis.y(m.rate)} r={3} />
            <text x={axis.x(m.at)} y={padding - 5 - levels[i] * 11} textAnchor="middle">
              {m.label} {amount(m.at)} · {amount(m.rate, 1)} ₽
            </text>
          </g>
        ))}
        <text className="payroll-chart-axis-label" x={width / 2} y={height - 4} textAnchor="middle">темп, прив. м за смену</text>
        <text className="payroll-chart-axis-label" x={10} y={height / 2} textAnchor="middle" transform={`rotate(-90 10 ${height / 2})`}>
          ₽ за прив. метр
        </text>
      </svg>
      {changed && (
        <ul className="payroll-chart-legend premium-curve-legend">
          <li><i className="payroll-chart-swatch payroll-chart-swatch-rate" />пробная шкала</li>
          <li><i className="payroll-chart-swatch premium-curve-swatch-base" />справочник</li>
        </ul>
      )}
    </figure>
  );
}
