// Вертикальная шкала слева от чертежа: ось, деления с адаптивным шагом и
// подписи. Работает и в глубинах от устья, и в абсолютных отметках.

import { ruNumber } from "../../lib/format";
import { depthTickStep, depthTicks } from "./geometry";

export function DepthScale({
  x,
  yTop,
  yBottom,
  fromValue,
  toValue,
  toY,
  unit = "м",
  digits,
  title,
}: {
  x: number;
  yTop: number;
  yBottom: number;
  /** Значение шкалы у верхней границы (глубина 0 или верхняя отметка). */
  fromValue: number;
  /** Значение шкалы у нижней границы. */
  toValue: number;
  /** Перевод значения шкалы в координату Y чертежа. */
  toY: (value: number) => number;
  unit?: string;
  digits?: number;
  title?: string;
}) {
  const span = Math.abs(toValue - fromValue);
  const pxPerUnit = span > 0 ? Math.abs(yBottom - yTop) / span : 0;
  const step = depthTickStep(span, pxPerUnit);
  const lo = Math.min(fromValue, toValue);
  const hi = Math.max(fromValue, toValue);
  const ticks = depthTicks(lo, hi, step);
  const labelDigits = digits ?? (step < 1 ? 1 : 0);

  return (
    <g className="depth-scale">
      <line className="depth-scale-axis" x1={x} y1={yTop} x2={x} y2={yBottom} />
      {ticks.map((value) => {
        const y = toY(value);
        const major = Math.abs(value / (step * 2) - Math.round(value / (step * 2))) < 1e-9;
        return (
          <g key={value}>
            <line
              className={`depth-scale-tick${major ? " major" : ""}`}
              x1={x - (major ? 6 : 3.5)}
              y1={y}
              x2={x}
              y2={y}
            />
            {major && (
              <text className="depth-scale-label" x={x - 9} y={y} textAnchor="end" dominantBaseline="middle">
                {ruNumber(value, labelDigits)}
              </text>
            )}
          </g>
        );
      })}
      {title && (
        <text
          className="depth-scale-title"
          transform={`translate(${x - 34} ${(yTop + yBottom) / 2}) rotate(-90)`}
          textAnchor="middle"
        >
          {title}, {unit}
        </text>
      )}
    </g>
  );
}
