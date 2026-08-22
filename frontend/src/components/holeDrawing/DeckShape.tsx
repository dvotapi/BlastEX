// Одна дека внутри ствола: заливка по типу (заряд / забойка / воздух),
// зернистость ВВ и обводка. Дека рисуется чуть уже ствола, чтобы стенки
// скважины оставались видимыми.

import { barrelSegmentPath, type HoleAxis } from "./geometry";
import { drawIds } from "./defs";
import { DRAW, darken, explosiveColor } from "./palette";

export type DeckLike = {
  kind: string;
  from_m: number;
  to_m: number;
  explosive_key?: string;
  mass_kg?: number;
};

export function DeckShape({
  axis,
  prefix,
  deck,
  title,
  dimmed = false,
  onHover,
}: {
  axis: HoleAxis;
  prefix: string;
  deck: DeckLike;
  title?: string;
  dimmed?: boolean;
  onHover?: (hovered: boolean) => void;
}) {
  const id = drawIds(prefix);
  const from = axis.at(Math.max(0, deck.from_m));
  const to = axis.at(Math.min(axis.lengthM, deck.to_m));
  const width = axis.widthPx - 2.4;
  if (width <= 0 || deck.to_m - deck.from_m <= 1e-6) return null;
  const path = barrelSegmentPath(from, to, width);

  const charge = deck.kind === "charge";
  const fill = charge
    ? explosiveColor(deck.explosive_key)
    : deck.kind === "stemming"
      ? `url(#${id.stemming})`
      : `url(#${id.air})`;
  const stroke = charge ? darken(explosiveColor(deck.explosive_key), 0.4) : DRAW.barrelWall;

  return (
    <g
      className={`hole-deck deck-${deck.kind}${dimmed ? " dimmed" : ""}`}
      onMouseEnter={onHover ? () => onHover(true) : undefined}
      onMouseLeave={onHover ? () => onHover(false) : undefined}
    >
      <path d={path} fill={fill} stroke={stroke} strokeWidth={0.8}>
        {title && <title>{title}</title>}
      </path>
      {charge && <path d={path} fill={`url(#${id.grain})`} stroke="none" pointerEvents="none" />}
    </g>
  );
}
