// Выносная размерная линия со стрелками — как на инженерном чертеже:
// две выносные полки от размеряемых точек и стрелка между ними с подписью.

import { drawIds } from "./defs";

export function VerticalDimension({
  prefix,
  x,
  y1,
  y2,
  label,
  /** Куда уходят выносные полки от объекта к размерной линии. */
  tickFromX,
  labelSide = "left",
}: {
  prefix: string;
  x: number;
  y1: number;
  y2: number;
  label: string;
  tickFromX?: number;
  labelSide?: "left" | "right";
}) {
  const id = drawIds(prefix);
  if (Math.abs(y2 - y1) < 1) return null;
  const short = Math.abs(y2 - y1) < 26;
  const mid = (y1 + y2) / 2;
  const textX = labelSide === "left" ? x - 5 : x + 5;
  return (
    <g className="hole-dimension">
      {tickFromX !== undefined && (
        <>
          <line className="hole-dimension-ext" x1={tickFromX} y1={y1} x2={x} y2={y1} />
          <line className="hole-dimension-ext" x1={tickFromX} y1={y2} x2={x} y2={y2} />
        </>
      )}
      {short ? (
        <>
          <line className="hole-dimension-line" x1={x} y1={y1 - 8} x2={x} y2={y1} markerEnd={`url(#${id.arrowEnd})`} />
          <line className="hole-dimension-line" x1={x} y1={y2 + 8} x2={x} y2={y2} markerEnd={`url(#${id.arrowEnd})`} />
        </>
      ) : (
        <line
          className="hole-dimension-line"
          x1={x}
          y1={y1}
          x2={x}
          y2={y2}
          markerStart={`url(#${id.arrowStart})`}
          markerEnd={`url(#${id.arrowEnd})`}
        />
      )}
      <text
        className="hole-dimension-text"
        x={textX}
        y={mid}
        textAnchor={labelSide === "left" ? "end" : "start"}
        dominantBaseline="middle"
      >
        {label}
      </text>
    </g>
  );
}

export function HorizontalDimension({
  prefix,
  y,
  x1,
  x2,
  label,
  tickFromY,
}: {
  prefix: string;
  y: number;
  x1: number;
  x2: number;
  label: string;
  tickFromY?: number;
}) {
  const id = drawIds(prefix);
  if (Math.abs(x2 - x1) < 1) return null;
  return (
    <g className="hole-dimension">
      {tickFromY !== undefined && (
        <>
          <line className="hole-dimension-ext" x1={x1} y1={tickFromY} x2={x1} y2={y} />
          <line className="hole-dimension-ext" x1={x2} y1={tickFromY} x2={x2} y2={y} />
        </>
      )}
      <line
        className="hole-dimension-line"
        x1={x1}
        y1={y}
        x2={x2}
        y2={y}
        markerStart={`url(#${id.arrowStart})`}
        markerEnd={`url(#${id.arrowEnd})`}
      />
      <text className="hole-dimension-text" x={(x1 + x2) / 2} y={y - 4} textAnchor="middle">
        {label}
      </text>
    </g>
  );
}
