// Масштабная линейка. На экране знаменатель масштаба (1:200) бессмыслен —
// SVG тянется под ширину панели, — поэтому показываем линейку в метрах:
// по ней можно померить чертёж при любом зуме.

import { ruNumber } from "../../lib/format";
import { niceScaleBarM } from "./geometry";

export function ScaleBar({
  x,
  y,
  pxPerM,
  targetPx = 110,
  note,
}: {
  x: number;
  y: number;
  pxPerM: number;
  targetPx?: number;
  /** Дополнительная подпись справа, например коэффициент преувеличения диаметра. */
  note?: string;
}) {
  if (!Number.isFinite(pxPerM) || pxPerM <= 0) return null;
  const lengthM = niceScaleBarM(pxPerM, targetPx);
  const lengthPx = lengthM * pxPerM;
  const half = lengthPx / 2;
  const digits = lengthM < 1 ? 1 : 0;

  return (
    <g className="scale-bar">
      <rect
        className="scale-bar-plate"
        x={x - 7}
        y={y - 20}
        width={lengthPx + (note ? 76 : 14)}
        height={28}
        rx={6}
      />
      {/* Двухцветная шашечная линейка — читается на любом фоне. */}
      <rect className="scale-bar-fill dark" x={x} y={y - 6} width={half} height={5} />
      <rect className="scale-bar-fill light" x={x + half} y={y - 6} width={half} height={5} />
      <rect className="scale-bar-frame" x={x} y={y - 6} width={lengthPx} height={5} />
      <text className="scale-bar-label" x={x} y={y - 10} textAnchor="start">0</text>
      <text className="scale-bar-label" x={x + lengthPx} y={y - 10} textAnchor="middle">
        {ruNumber(lengthM, digits)} м
      </text>
      {note && (
        <text className="scale-bar-note" x={x + lengthPx + 14} y={y - 1} textAnchor="start">
          {note}
        </text>
      )}
    </g>
  );
}
