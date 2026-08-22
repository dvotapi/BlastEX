// Ствол скважины: пустота, стенки, воротник устья и участок перебура.

import { barrelSegmentPath, type HoleAxis } from "./geometry";
import { drawIds } from "./defs";

export function HoleBarrel({
  axis,
  prefix,
  subdrillFromM,
  highlighted = false,
}: {
  axis: HoleAxis;
  prefix: string;
  /** Глубина от устья, ниже которой ствол считается перебуром. */
  subdrillFromM?: number;
  highlighted?: boolean;
}) {
  const id = drawIds(prefix);
  const half = axis.widthPx / 2;
  const n = axis.normal;
  const collar = axis.collar;
  const toe = axis.toe;

  const leftTop = { x: collar.x - n.x * half, y: collar.y - n.y * half };
  const leftBottom = { x: toe.x - n.x * half, y: toe.y - n.y * half };
  const rightTop = { x: collar.x + n.x * half, y: collar.y + n.y * half };
  const rightBottom = { x: toe.x + n.x * half, y: toe.y + n.y * half };

  const hasSubdrill = subdrillFromM !== undefined && subdrillFromM < axis.lengthM - 1e-6;
  const subdrillStart = hasSubdrill ? axis.at(Math.max(0, subdrillFromM!)) : null;

  return (
    <g className={`hole-barrel${highlighted ? " highlighted" : ""}`}>
      <path className="hole-barrel-void" d={barrelSegmentPath(collar, toe, axis.widthPx)} />

      {subdrillStart && (
        <path
          className="hole-barrel-subdrill"
          d={barrelSegmentPath(subdrillStart, toe, axis.widthPx)}
          fill={`url(#${id.subdrill})`}
        />
      )}

      {/* Стенки скважины — две линии, а не одна толстая: чертёж, а не полоска. */}
      <line className="hole-barrel-wall" x1={leftTop.x} y1={leftTop.y} x2={leftBottom.x} y2={leftBottom.y} />
      <line className="hole-barrel-wall" x1={rightTop.x} y1={rightTop.y} x2={rightBottom.x} y2={rightBottom.y} />
      {/* Забой — скруглённое донышко. */}
      <path
        className="hole-barrel-toe"
        d={`M${leftBottom.x} ${leftBottom.y} Q${toe.x + axis.dir.x * half * 0.9} ${toe.y + axis.dir.y * half * 0.9} ${rightBottom.x} ${rightBottom.y}`}
      />
      {/* Воротник устья. */}
      <line
        className="hole-barrel-collar"
        x1={leftTop.x - n.x * 2.5}
        y1={leftTop.y - n.y * 2.5}
        x2={rightTop.x + n.x * 2.5}
        y2={rightTop.y + n.y * 2.5}
      />
    </g>
  );
}
