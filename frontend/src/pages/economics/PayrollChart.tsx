import type { BlockPayroll } from "../../types/blockEconomics";
import { amount } from "./format";
import { chartGeometry, type Marker } from "./payrollModel";

const SIZE = { width: 560, height: 260, padding: 44 };

/**
 * Шкала сдельной премии основной должности: цена единицы от темпа и премия за
 * смену. Вторая линия нарисована в собственном масштабе (абсолютной оси у неё
 * нет), поэтому в подписи названа относительной.
 */
export function PayrollChart({ payroll }: { payroll: BlockPayroll }) {
  const { scale, series } = payroll;
  if (!scale) return null;
  const geometry = chartGeometry(series, scale, payroll.pace.m_plan, SIZE);
  if (!geometry) return null;
  const { width, height, padding } = SIZE;
  const position = payroll.positions.find((item) => item.position_code === payroll.main_position_code);
  const name = position ? position.position_name || position.position_code : "основная должность";
  const { norm, ceiling, pace } = geometry.markers;

  const marker = (kind: string, label: string, point: Marker | null) =>
    point && (
      <g className={`payroll-chart-marker payroll-chart-marker-${kind}`}>
        <line x1={point.x} x2={point.x} y1={padding} y2={height - padding} />
        <circle cx={point.x} cy={point.y} r={3.5} />
        <text x={point.x} y={padding - 6} textAnchor="middle">{label} {amount(point.value)}</text>
      </g>
    );

  return (
    <figure className="payroll-chart">
      <figcaption className="payroll-chart-title">Шкала сдельной премии: {name}</figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="График шкалы сдельной премии">
        {geometry.yAxis.map((tick) => (
          <g key={`y${tick.value}`} className="payroll-chart-tick">
            <line className="payroll-chart-grid" x1={padding} x2={width - padding} y1={tick.pos} y2={tick.pos} />
            <text x={padding - 6} y={tick.pos + 3} textAnchor="end">{tick.label}</text>
          </g>
        ))}
        {geometry.xAxis.map((tick) => (
          <text key={`x${tick.value}`} className="payroll-chart-tick" x={tick.pos} y={height - padding + 14} textAnchor="middle">
            {tick.label}
          </text>
        ))}
        <line className="payroll-chart-axis" x1={padding} x2={width - padding} y1={height - padding} y2={height - padding} />
        <line className="payroll-chart-axis" x1={padding} x2={padding} y1={padding} y2={height - padding} />
        <path className="payroll-chart-line payroll-chart-line-shift" d={geometry.perShiftPath} />
        <path className="payroll-chart-line payroll-chart-line-rate" d={geometry.ratePath} />
        {marker("norm", "норма", norm)}
        {marker("ceiling", "потолок", ceiling)}
        {marker("pace", "плановый темп", pace)}
        <text className="payroll-chart-axis-label" x={width / 2} y={height - 6} textAnchor="middle">темп, м за смену</text>
        <text className="payroll-chart-axis-label" x={12} y={height / 2} textAnchor="middle" transform={`rotate(-90 12 ${height / 2})`}>
          цена единицы, ₽ за приведённый метр
        </text>
      </svg>
      <ul className="payroll-chart-legend">
        <li><i className="payroll-chart-swatch payroll-chart-swatch-rate" />цена единицы (левая ось)</li>
        <li><i className="payroll-chart-swatch payroll-chart-swatch-shift" />премия за смену (в относительном масштабе)</li>
      </ul>
    </figure>
  );
}
