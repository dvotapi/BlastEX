import { useState } from "react";
import { ruNumber } from "../../../lib/format";
import type { BlastVariant, KuzRamFactInput } from "../../../types";
import { formatQ, LEGACY_Q_MIN_KG_M3, trimmed } from "./kuzramFormat";

const WIDTH = 640;
const HEIGHT = 240;
const PAD = { left: 46, right: 14, top: 12, bottom: 36 };
const INNER_W = WIDTH - PAD.left - PAD.right;
const INNER_H = HEIGHT - PAD.top - PAD.bottom;

/** Шаг делений оси q: 1, 2, 2,5, 5 или 10 × 10ⁿ — около пяти делений на всю высоту. */
export function niceStep(maxValue: number): number {
  const raw = maxValue / 5;
  const power = 10 ** Math.floor(Math.log10(raw));
  const mantissa = raw / power;
  const nice = mantissa < 1.5 ? 1 : mantissa < 2.5 ? 2 : mantissa < 3.5 ? 2.5 : mantissa < 7.5 ? 5 : 10;
  return Number((nice * power).toPrecision(6));
}

type Point = { x: number; y: number; reached: boolean };

function Series({ className, points }: { className: string; points: Point[] }) {
  return (
    <g className={className}>
      <polyline points={points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ")} />
      {points.map((point, index) => (
        <circle key={index} cx={point.x} cy={point.y} r={4} className={point.reached ? undefined : "open"} />
      ))}
    </g>
  );
}

/**
 * q по диаметрам коронок обеих моделей — самописный SVG, как `ResultsChart`.
 * Полая точка — порог негабарита не достигнут, ромб — фактический взрыв.
 * Наведение показывает подсказку, щелчок выбирает коронку (как строка таблицы).
 */
export function KuzRamChart({
  variants,
  facts,
  selectedIndex,
  onSelect,
}: {
  variants: BlastVariant[];
  facts: KuzRamFactInput[];
  selectedIndex: number;
  onSelect: (index: number) => void;
}) {
  const [hover, setHover] = useState<number | null>(null);
  if (!variants.length) return null;

  const crowns = variants.map((variant) => variant.crown_mm);
  const allCrowns = [...crowns, ...facts.map((fact) => fact.crown_mm)];
  const xPad = Math.max(8, (Math.max(...allCrowns) - Math.min(...allCrowns)) * 0.04);
  const x0 = Math.min(...allCrowns) - xPad;
  const x1 = Math.max(...allCrowns) + xPad;
  const qValues = [
    ...variants.flatMap((variant) => [variant.specific_q_kg_m3, variant.legacy.specific_q_kg_m3]),
    ...facts.map((fact) => fact.q_kg_m3),
  ];
  const qMax = Math.max(...qValues);
  const step = niceStep(qMax);
  const yMax = Math.ceil((qMax * 1.08) / step) * step;
  const x = (mm: number) => PAD.left + ((mm - x0) / (x1 - x0)) * INNER_W;
  const y = (q: number) => PAD.top + INNER_H - (q / yMax) * INNER_H;
  const ticks = Array.from({ length: Math.round(yMax / step) + 1 }, (_, index) => index * step);
  // Подписи коронок без наложения: следующая — не ближе 26 единиц к прошлой.
  let lastLabelX = -Infinity;
  const labelled = crowns.map((mm) => {
    if (x(mm) - lastLabelX < 26) return false;
    lastLabelX = x(mm);
    return true;
  });
  // Зона наведения коронки — до середины между соседними точками.
  const zones = crowns.map((mm, index) => {
    const from = index === 0 ? PAD.left : (x(crowns[index - 1]) + x(mm)) / 2;
    const to = index === crowns.length - 1 ? WIDTH - PAD.right : (x(mm) + x(crowns[index + 1])) / 2;
    return { from, width: Math.max(0, to - from) };
  });
  const selected = variants[selectedIndex];
  const hovered = hover === null ? null : variants[hover] ?? null;
  const tipLeftPct = hovered ? (x(hovered.crown_mm) / WIDTH) * 100 : 0;
  const bottom = HEIGHT - PAD.bottom;

  return (
    <div className="kuzram-chart">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Удельный расход q по диаметрам коронок: Kuz-Ram и «до исправления»">
        {ticks.map((tick) => (
          <g key={tick}>
            <line className="grid-line" x1={PAD.left} x2={WIDTH - PAD.right} y1={y(tick)} y2={y(tick)} />
            <text x={PAD.left - 6} y={y(tick)} textAnchor="end" dominantBaseline="middle">
              {ruNumber(tick, step < 1 ? 2 : 0)}
            </text>
          </g>
        ))}
        <line className="axis-line" x1={PAD.left} x2={WIDTH - PAD.right} y1={bottom} y2={bottom} />
        {crowns.map((mm, index) =>
          labelled[index] ? (
            <text key={mm} x={x(mm)} y={bottom + 15} textAnchor="middle">
              {trimmed(mm)}
            </text>
          ) : null,
        )}
        <text className="axis-title" x={PAD.left + INNER_W / 2} y={HEIGHT - 4} textAnchor="middle">
          Диаметр коронки, мм
        </text>
        <text className="axis-title" x={12} y={PAD.top + INNER_H / 2} textAnchor="middle" transform={`rotate(-90 12 ${PAD.top + INNER_H / 2})`}>
          q, кг/м³
        </text>
        {selected && <line className="kuzram-chart-selected" x1={x(selected.crown_mm)} x2={x(selected.crown_mm)} y1={PAD.top} y2={bottom} />}
        {hovered && <line className="kuzram-chart-hover" x1={x(hovered.crown_mm)} x2={x(hovered.crown_mm)} y1={PAD.top} y2={bottom} />}
        <Series
          className="series-legacy"
          points={variants.map((variant) => ({ x: x(variant.crown_mm), y: y(variant.legacy.specific_q_kg_m3), reached: variant.legacy.reached }))}
        />
        <Series
          className="series-new"
          points={variants.map((variant) => ({ x: x(variant.crown_mm), y: y(variant.specific_q_kg_m3), reached: variant.reached }))}
        />
        {facts.map((fact, index) => {
          const cx = x(fact.crown_mm);
          const cy = y(fact.q_kg_m3);
          return (
            <rect key={index} className="kuzram-chart-fact" x={cx - 4.5} y={cy - 4.5} width={9} height={9} transform={`rotate(45 ${cx} ${cy})`} />
          );
        })}
        {zones.map((zone, index) => (
          <rect
            key={crowns[index]}
            className="kuzram-chart-hit"
            x={zone.from}
            y={PAD.top}
            width={zone.width}
            height={INNER_H}
            onMouseEnter={() => setHover(index)}
            onMouseLeave={() => setHover(null)}
            onClick={() => onSelect(index)}
          />
        ))}
      </svg>
      {hovered && (
        <div className={`kuzram-chart-tip${tipLeftPct > 60 ? " left" : ""}`} role="tooltip" style={{ left: `${tipLeftPct}%` }}>
          <b>Коронка {trimmed(hovered.crown_mm)} мм</b>
          <span>
            <i className="new" aria-hidden="true" />
            Kuz-Ram {formatQ(hovered.specific_q_kg_m3)} кг/м³
          </span>
          <span>
            <i className="legacy" aria-hidden="true" />
            До исправления {formatQ(hovered.legacy.specific_q_kg_m3, ",", LEGACY_Q_MIN_KG_M3)} кг/м³
          </span>
          {facts
            .filter((fact) => fact.crown_mm === hovered.crown_mm)
            .map((fact, index) => (
              <span key={index}>
                <i className="fact" aria-hidden="true" />
                Факт {ruNumber(fact.q_kg_m3, 2)} кг/м³
              </span>
            ))}
          {(!hovered.reached || !hovered.legacy.reached) && (
            <span className="kuzram-chart-tip-flag">
              порог не достигнут: {[!hovered.reached ? "Kuz-Ram" : "", !hovered.legacy.reached ? "до исправления" : ""].filter(Boolean).join(", ")}
            </span>
          )}
        </div>
      )}
      <ul className="kuzram-legend" aria-label="Обозначения графика">
        <li><i className="new" aria-hidden="true" />Kuz-Ram</li>
        <li><i className="legacy" aria-hidden="true" />До исправления</li>
        <li><i className="open" aria-hidden="true" />порог не достигнут</li>
        {facts.length > 0 && <li><i className="fact" aria-hidden="true" />фактический взрыв</li>}
      </ul>
    </div>
  );
}
