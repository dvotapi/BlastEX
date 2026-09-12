import type { BlastVariant } from "../../types";

/** Размеры графика: `full` — отдельная панель, `compact` — 142 × 118 рядом с таблицей вариантов. */
const LAYOUTS = {
  full: { width: 620, height: 190, pad: { left: 42, right: 20, top: 20, bottom: 35 }, ticks: 4, radius: 5 },
  compact: { width: 142, height: 118, pad: { left: 34, right: 10, top: 10, bottom: 22 }, ticks: 4, radius: 3.5 },
} as const;

/** Зависимость удельного расхода q от диаметра коронки по рассчитанным вариантам. */
export function ResultsChart({ variants, size = "full" }: { variants: BlastVariant[]; size?: keyof typeof LAYOUTS }) {
  const compact = size === "compact";
  if (!variants.length) {
    return (
      <div className={`chart-empty${compact ? " compact" : ""}`}>
        {compact ? "Нет расчёта" : "После расчёта здесь появится сравнение вариантов."}
      </div>
    );
  }
  const { width, height, pad, ticks: tickCount, radius } = LAYOUTS[size];
  const qValues = variants.map((item) => item.specific_q_kg_m3);
  const minQ = Math.min(...qValues) - 0.04;
  const maxQ = Math.max(...qValues) + 0.04;
  const x = (index: number) => pad.left + index * ((width - pad.left - pad.right) / Math.max(1, variants.length - 1));
  const y = (value: number) => pad.top + ((maxQ - value) / (maxQ - minQ)) * (height - pad.top - pad.bottom);
  const points = variants.map((item, index) => `${x(index)},${y(item.specific_q_kg_m3)}`).join(" ");
  const ticks = Array.from({ length: tickCount + 1 }, (_, i) => minQ + ((maxQ - minQ) * i) / tickCount);
  // На узком графике подписываем каждый второй диаметр, если их больше пяти.
  const labelEvery = compact && variants.length > 5 ? 2 : 1;
  return (
    <svg
      className={`result-chart${compact ? " compact" : ""}`}
      viewBox={`0 0 ${width} ${height}`}
      width={compact ? width : undefined}
      height={compact ? height : undefined}
      role="img"
      aria-label="Зависимость удельного расхода от диаметра коронки"
    >
      {ticks.map((value) => (
        <line key={value} className="grid-line" x1={pad.left} x2={width - pad.right} y1={y(value)} y2={y(value)} />
      ))}
      <line className="axis-line" x1={pad.left} x2={pad.left} y1={pad.top} y2={height - pad.bottom} />
      {ticks.map((value) => (
        <g key={value}>
          <line className="axis-tick" x1={pad.left - 4} x2={pad.left} y1={y(value)} y2={y(value)} />
          <text className="axis-label" x={pad.left - (compact ? 6 : 8)} y={y(value)} textAnchor="end" dominantBaseline="middle">{value.toFixed(2)}</text>
        </g>
      ))}
      <polyline points={points} />
      {variants.map((item, index) => (
        <g key={item.crown_mm}>
          <circle cx={x(index)} cy={y(item.specific_q_kg_m3)} r={radius} />
          {index % labelEvery === 0 && <text x={x(index)} y={height - (compact ? 6 : 10)} textAnchor="middle">{item.crown_mm}</text>}
        </g>
      ))}
    </svg>
  );
}
