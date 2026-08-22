// Скважинный боевик: промежуточный детонатор (шашка) на своей глубине и
// волновод НСИ от него вверх до устья с выходом на поверхность.

import { barrelSegmentPath, type HoleAxis, type Vec2 } from "./geometry";

const PRIMER_LENGTH_PX = 13;

export function Primer({
  axis,
  depthM,
  label,
  delayLabel,
  nsiOffsetPx = 0,
  nsiExitPx = 0,
  variant = "primary",
}: {
  axis: HoleAxis;
  /** Глубина боевика от устья, м. */
  depthM: number;
  /** Подпись у шашки, например «Д1». */
  label?: string;
  /** Подпись замедления внутрискважинного детонатора, например «500 мс». */
  delayLabel?: string;
  /** Сдвиг волновода поперёк ствола, чтобы два НСИ не сливались. */
  nsiOffsetPx?: number;
  /** На сколько волновод выходит выше устья. 0 — не рисовать выход. */
  nsiExitPx?: number;
  variant?: "primary" | "secondary";
}) {
  const center = axis.at(Math.max(0, Math.min(depthM, axis.lengthM)));
  const n = axis.normal;
  const d = axis.dir;
  const half = PRIMER_LENGTH_PX / 2;
  const top: Vec2 = { x: center.x - d.x * half, y: center.y - d.y * half };
  const bottom: Vec2 = { x: center.x + d.x * half, y: center.y + d.y * half };
  const shaftWidth = Math.max(6, axis.widthPx - 5);

  const wavePoints: Vec2[] = [];
  const anchor: Vec2 = { x: top.x + n.x * nsiOffsetPx, y: top.y + n.y * nsiOffsetPx };
  wavePoints.push(anchor);
  const collar: Vec2 = { x: axis.collar.x + n.x * nsiOffsetPx, y: axis.collar.y + n.y * nsiOffsetPx };
  wavePoints.push(collar);
  if (nsiExitPx > 0) {
    wavePoints.push({ x: collar.x - d.x * nsiExitPx, y: collar.y - d.y * nsiExitPx });
    wavePoints.push({ x: collar.x - d.x * nsiExitPx + n.x * 12, y: collar.y - d.y * nsiExitPx + n.y * 12 });
  }
  const waveguide = wavePoints.map((p) => `${p.x},${p.y}`).join(" ");
  const tail = wavePoints[wavePoints.length - 1];

  return (
    <g className={`hole-primer variant-${variant}`}>
      <polyline className="hole-primer-nsi" points={waveguide} />
      {nsiExitPx > 0 && <circle className="hole-primer-nsi-end" cx={tail.x} cy={tail.y} r={2.6} />}

      <path className="hole-primer-body" d={barrelSegmentPath(top, bottom, shaftWidth)} />
      <line
        className="hole-primer-cap"
        x1={top.x - n.x * shaftWidth * 0.5}
        y1={top.y - n.y * shaftWidth * 0.5}
        x2={top.x + n.x * shaftWidth * 0.5}
        y2={top.y + n.y * shaftWidth * 0.5}
      />

      {/* Номер боевика выносится вбок: внутри шашки (13 px) текст нечитаем. */}
      {label && (
        <text
          className="hole-primer-label"
          x={center.x + n.x * (axis.widthPx / 2 + 5)}
          y={center.y + n.y * (axis.widthPx / 2 + 5)}
          textAnchor="start"
          dominantBaseline="middle"
        >
          {label}
        </text>
      )}
      {/* Задержка — слева и выше шашки, номер боевика — справа: подписи не сходятся. */}
      {delayLabel && (
        <text
          className="hole-primer-delay"
          x={center.x - n.x * (axis.widthPx / 2 + 9) - d.x * 10}
          y={center.y - n.y * (axis.widthPx / 2 + 9) - d.y * 10}
          textAnchor="end"
          dominantBaseline="middle"
        >
          {delayLabel}
        </text>
      )}
    </g>
  );
}
