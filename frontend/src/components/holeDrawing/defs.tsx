// Штриховки и маркеры чертежей скважины. Идентификаторы префиксуются, чтобы
// два чертежа на одной странице не перебивали <defs> друг друга.

import { DRAW } from "./palette";

export function drawIds(prefix: string) {
  return {
    rock: `${prefix}-rock`,
    stemming: `${prefix}-stemming`,
    air: `${prefix}-air`,
    inert: `${prefix}-inert`,
    water: `${prefix}-water`,
    subdrill: `${prefix}-subdrill`,
    grain: `${prefix}-grain`,
    arrowStart: `${prefix}-arrow-start`,
    arrowEnd: `${prefix}-arrow-end`,
  };
}

export function HoleDrawingDefs({ prefix }: { prefix: string }) {
  const id = drawIds(prefix);
  return (
    <defs>
      {/* Массив породы — редкая диагональная штриховка. */}
      <pattern id={id.rock} width="9" height="9" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <rect width="9" height="9" fill={DRAW.rock} />
        <line x1="0" y1="0" x2="0" y2="9" stroke={DRAW.rockLine} strokeWidth="1" />
      </pattern>

      {/* Забойка — щебень: точки-крошка на песочном фоне. */}
      <pattern id={id.stemming} width="7" height="7" patternUnits="userSpaceOnUse">
        <rect width="7" height="7" fill={DRAW.stemming} />
        <circle cx="1.8" cy="2" r="1.15" fill={DRAW.stemmingDark} />
        <circle cx="5.2" cy="5" r="0.95" fill={DRAW.stemmingDark} />
        <circle cx="5.6" cy="1.4" r="0.6" fill={DRAW.stemmingDark} />
        <circle cx="2.2" cy="5.6" r="0.55" fill={DRAW.stemmingDark} />
      </pattern>

      {/* Воздушный промежуток — пустота с редкой косой сеткой. */}
      <pattern id={id.air} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <rect width="6" height="6" fill="#ffffff" />
        <line x1="0" y1="0" x2="0" y2="6" stroke={DRAW.air} strokeWidth="1.1" />
      </pattern>

      <pattern id={id.inert} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <rect width="6" height="6" fill="#d7d2c8" />
        <line x1="0" y1="0" x2="0" y2="6" stroke="#9a9284" strokeWidth="1.1" />
      </pattern>

      <pattern id={id.water} width="7" height="7" patternUnits="userSpaceOnUse">
        <rect width="7" height="7" fill="#c5dff0" />
        <path d="M0 3.5 Q1.8 2 3.5 3.5 T7 3.5" fill="none" stroke="#5a8fb3" strokeWidth="0.9" />
      </pattern>

      {/* Перебур — пустой ствол ниже проектной подошвы. */}
      <pattern id={id.subdrill} width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">
        <rect width="5" height="5" fill={DRAW.barrelVoid} />
        <line x1="0" y1="0" x2="0" y2="5" stroke={DRAW.subdrill} strokeWidth="1.4" />
      </pattern>

      {/* Зернистость ВВ поверх заливки колонны заряда. */}
      <pattern id={id.grain} width="5" height="5" patternUnits="userSpaceOnUse">
        <circle cx="1.4" cy="1.4" r="0.7" fill="#000" opacity="0.16" />
        <circle cx="3.9" cy="3.6" r="0.55" fill="#fff" opacity="0.22" />
      </pattern>

      <marker id={id.arrowEnd} markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
        <path d="M0,0 L7,3.5 L0,7 z" fill={DRAW.dimension} />
      </marker>
      <marker id={id.arrowStart} markerWidth="7" markerHeight="7" refX="1" refY="3.5" orient="auto">
        <path d="M7,0 L0,3.5 L7,7 z" fill={DRAW.dimension} />
      </marker>
    </defs>
  );
}
