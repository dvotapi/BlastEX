import { DeckShape, type DeckLike } from "../../components/holeDrawing/DeckShape";
import { DepthScale } from "../../components/holeDrawing/DepthScale";
import { VerticalDimension } from "../../components/holeDrawing/DimensionLine";
import { HoleBarrel } from "../../components/holeDrawing/HoleBarrel";
import { HoleDrawingDefs } from "../../components/holeDrawing/defs";
import { Primer } from "../../components/holeDrawing/Primer";
import { barrelWidthPx, deckTooltip, makeAxis } from "../../components/holeDrawing/geometry";
import { ruNumber } from "../../lib/format";
import type { HoleGeometry, InitiationConfig } from "../../types";

const DRAW_PREFIX = "hs";
const WIDTH = 248;
const HEIGHT = 400;
const PAD = { left: 46, right: 68, top: 40, bottom: 32 };

/**
 * Глубина боевика от устья — тот же расчёт, что и в серверной схеме
 * (`blast_hole_viz.py::_booster_depth_m`): не выше перебур + 0,5 м от забоя,
 * и не глубже, чем позволяет длина НСИ от устья.
 */
function boosterDepthFromCollarM({
  depthM,
  overdrillM,
  chargeLengthM,
  nsiLengthM,
}: {
  depthM: number;
  overdrillM: number;
  chargeLengthM: number;
  nsiLengthM: number;
}): number {
  const maxFromBottom = depthM - (overdrillM + 0.5);
  const fromCollarByNsi = nsiLengthM;
  const chargeTopM = depthM - chargeLengthM;
  const deepest = Math.max(chargeTopM + 0.15, Math.min(maxFromBottom, depthM));
  return Math.min(deepest, Math.max(chargeTopM + 0.15, fromCollarByNsi));
}

export function HoleSchemeView({
  hole,
  initiation,
  crownMm,
  title,
}: {
  hole: HoleGeometry;
  initiation: InitiationConfig;
  crownMm: number;
  title?: string;
}) {
  const depthM = hole.depth_m;
  if (depthM <= 0) return null;

  const yTop = PAD.top;
  const yBottom = HEIGHT - PAD.bottom;
  const xAxis = PAD.left + (WIDTH - PAD.left - PAD.right) / 2;
  const width = barrelWidthPx(crownMm, { min: 20, max: 40, base: 152 });

  const axis = makeAxis({ x: xAxis, y: yTop }, { x: xAxis, y: yBottom }, depthM, width);
  const toY = (depth: number) => axis.at(depth).y;

  const stemmingM = Math.max(0, Math.min(hole.undercharge_m, depthM));
  const chargeLengthM = Math.max(0, Math.min(hole.charge_length_m, depthM - stemmingM));
  const subdrillFromM = Math.max(0, depthM - hole.overdrill_m);

  const decks: DeckLike[] = [];
  if (stemmingM > 0) decks.push({ kind: "stemming", from_m: 0, to_m: stemmingM, mass_kg: 0 });
  if (chargeLengthM > 0) {
    decks.push({
      kind: "charge",
      from_m: stemmingM,
      to_m: stemmingM + chargeLengthM,
      explosive_key: hole.explosive_label || hole.explosive_name,
      mass_kg: hole.charge_mass_kg,
    });
  }

  // Боевики: один или два, второй ставится по длине НСИ-2 (обычно выше первого).
  const nsiLengths = initiation.nsi_per_hole === 2
    ? [initiation.nsi_length_1_m, initiation.nsi_length_2_m]
    : [initiation.nsi_length_1_m];
  const primerDepths = nsiLengths
    .slice(0, Math.max(1, initiation.intermediate_detonators_per_hole))
    .map((nsiLengthM) =>
      boosterDepthFromCollarM({
        depthM,
        overdrillM: hole.overdrill_m,
        chargeLengthM,
        nsiLengthM,
      }),
    )
    .sort((a, b) => b - a);

  const dimX = xAxis + width / 2 + 26;
  const barrelEdge = xAxis + width / 2;
  // Во сколько раз ствол на схеме шире натурального — указываем на чертеже.
  const pxPerM = (yBottom - yTop) / depthM;
  const exaggeration = Math.max(1, Math.round(width / ((crownMm / 1000) * pxPerM)));

  return (
    <div className="hole-scheme">
      <svg className="hole-scheme-svg" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Конструкция заряда скважины">
        <HoleDrawingDefs prefix={DRAW_PREFIX} />

        {title && <text className="hole-scheme-title" x={WIDTH / 2} y={13} textAnchor="middle">{title.toUpperCase()}</text>}

        {/* Поверхность уступа у устья. */}
        <line className="hole-scheme-surface" x1={PAD.left - 22} y1={yTop} x2={WIDTH - 10} y2={yTop} />
        <rect
          className="hole-scheme-ground"
          x={PAD.left - 22}
          y={yTop}
          width={WIDTH - PAD.left - 10 + 22}
          height={yBottom - yTop + 14}
          fill={`url(#${DRAW_PREFIX}-rock)`}
        />

        <DepthScale
          x={PAD.left - 22}
          yTop={yTop}
          yBottom={yBottom}
          fromValue={0}
          toValue={depthM}
          toY={toY}
        />

        <HoleBarrel axis={axis} prefix={DRAW_PREFIX} subdrillFromM={subdrillFromM} />

        {decks.map((deck, i) => (
          <DeckShape key={i} axis={axis} prefix={DRAW_PREFIX} deck={deck} title={deckTooltip({ ...deck, mass_kg: deck.mass_kg ?? 0, explosive_key: deck.explosive_key ?? "" })} />
        ))}

        {primerDepths.map((depth, i) => (
          <Primer
            key={i}
            axis={axis}
            depthM={depth}
            label={primerDepths.length > 1 ? `Д${i + 1}` : undefined}
            delayLabel={i === 0 ? `${ruNumber(initiation.detonator_delay_ms, 0)} мс` : undefined}
            nsiOffsetPx={i === 0 ? -2.5 : 3.5}
            nsiExitPx={13}
            variant={i === 0 ? "primary" : "secondary"}
          />
        ))}

        {/* Выносные размеры конструкции заряда. */}
        {stemmingM > 0 && (
          <VerticalDimension
            prefix={DRAW_PREFIX}
            x={dimX}
            y1={toY(0)}
            y2={toY(stemmingM)}
            tickFromX={barrelEdge}
            labelSide="right"
            label={`забойка ${ruNumber(stemmingM, 1)}`}
          />
        )}
        {chargeLengthM > 0 && (
          <VerticalDimension
            prefix={DRAW_PREFIX}
            x={dimX}
            y1={toY(stemmingM)}
            y2={toY(stemmingM + chargeLengthM)}
            tickFromX={barrelEdge}
            labelSide="right"
            label={`заряд ${ruNumber(chargeLengthM, 1)}`}
          />
        )}
        {hole.overdrill_m > 0 && (
          <VerticalDimension
            prefix={DRAW_PREFIX}
            x={dimX}
            y1={toY(subdrillFromM)}
            y2={toY(depthM)}
            tickFromX={barrelEdge}
            labelSide="right"
            label={`перебур ${ruNumber(hole.overdrill_m, 1)}`}
          />
        )}
        <VerticalDimension
          prefix={DRAW_PREFIX}
          x={PAD.left - 4}
          y1={toY(0)}
          y2={toY(depthM)}
          tickFromX={xAxis - width / 2}
          label={`${ruNumber(depthM, 1)} м`}
        />

        {chargeLengthM > 0 && (
          <text
            className="hole-scheme-mass"
            x={xAxis}
            y={toY(stemmingM + chargeLengthM / 2)}
            textAnchor="middle"
            dominantBaseline="middle"
          >
            {ruNumber(hole.charge_mass_kg, 0)} кг
          </text>
        )}
      </svg>

      <div className="hole-scheme-caption">
        <b>{hole.explosive_label || hole.explosive_name}</b>
        <span>⌀ {ruNumber(crownMm, 0)}/{ruNumber(hole.charge_diameter_m * 1000, 0)} мм</span>
        <small>глубина в масштабе · ⌀ ×{ruNumber(exaggeration, 0)}</small>
      </div>
    </div>
  );
}
