import { useMemo, useState } from "react";
import { DeckShape } from "../../components/holeDrawing/DeckShape";
import { DepthScale } from "../../components/holeDrawing/DepthScale";
import { HorizontalDimension, VerticalDimension } from "../../components/holeDrawing/DimensionLine";
import { HoleBarrel } from "../../components/holeDrawing/HoleBarrel";
import { HoleDrawingDefs } from "../../components/holeDrawing/defs";
import { Primer } from "../../components/holeDrawing/Primer";
import { barrelWidthPx, deckTooltip, makeAxis } from "../../components/holeDrawing/geometry";
import { ruNumber } from "../../lib/format";
import { holeLength, localBasis } from "../../lib/geometry2d";
import type { BlockContour, Hole, HoleLoad, InitiationNetwork } from "../../types/design";

const DRAW_PREFIX = "sec";
const WIDTH = 880;
const HEIGHT = 430;
const PAD = { left: 74, right: 118, top: 78, bottom: 44 };

type Tooltip = { x: number; y: number; text: string };

export function SectionView({
  contour,
  holes,
  loads,
  network,
  rowAzimuthDeg,
  selectedRow,
  onSelectedRowChange,
}: {
  contour: BlockContour;
  holes: Hole[];
  loads: HoleLoad[];
  network?: InitiationNetwork | null;
  rowAzimuthDeg: number;
  selectedRow: number | null;
  onSelectedRowChange: (row: number) => void;
}) {
  const [hovered, setHovered] = useState<Tooltip | null>(null);
  const [activeHole, setActiveHole] = useState<string | null>(null);

  const loadById = useMemo(() => {
    const map = new Map<string, HoleLoad>();
    for (const load of loads) map.set(load.hole_id, load);
    return map;
  }, [loads]);

  const rows = useMemo(() => {
    const set = new Set<number>();
    for (const h of holes) if (h.enabled) set.add(h.row);
    return Array.from(set).sort((a, b) => a - b);
  }, [holes]);

  const { rowDir } = useMemo(() => localBasis(rowAzimuthDeg), [rowAzimuthDeg]);
  const row = selectedRow ?? rows[0] ?? null;
  const rowHoles = useMemo(() => {
    if (row === null) return [];
    return holes
      .filter((h) => h.enabled && h.row === row)
      .map((h) => ({ hole: h, u: h.collar.x * rowDir.x + h.collar.y * rowDir.y }))
      .sort((a, b) => a.u - b.u);
  }, [holes, row, rowDir]);

  if (!rows.length || !rowHoles.length) {
    return (
      <section className="panel">
        <header><b>Разрез по ряду</b></header>
        <div className="panel-body"><small>Постройте сетку скважин, чтобы увидеть разрез.</small></div>
      </section>
    );
  }

  // --- Масштабы чертежа -----------------------------------------------------
  const uValues = rowHoles.map((r) => r.u);
  const zValues = rowHoles.flatMap((r) => [r.hole.collar.z, r.hole.toe.z]);
  zValues.push(contour.bench.crest_z_m, contour.bench.toe_z_m);
  const zTop = Math.max(...zValues);
  const zBottom = Math.min(...zValues);
  const zSpan = Math.max(1e-6, zTop - zBottom);
  const zMax = zTop + zSpan * 0.05;
  const zMin = zBottom - zSpan * 0.04;

  // Средний шаг между скважинами — им же оцениваем вынос откоса за первую скважину.
  const gaps = uValues.slice(1).map((u, i) => u - uValues[i]);
  const meanGap = gaps.length ? gaps.reduce((a, b) => a + b, 0) / gaps.length : 5;
  const uMin = Math.min(...uValues) - meanGap * 1.35;
  const uMax = Math.max(...uValues) + meanGap * 0.55;

  const sx = (u: number) => PAD.left + ((u - uMin) / Math.max(1e-6, uMax - uMin)) * (WIDTH - PAD.left - PAD.right);
  const sy = (z: number) => PAD.top + ((zMax - z) / Math.max(1e-6, zMax - zMin)) * (HEIGHT - PAD.top - PAD.bottom);

  const yCrest = sy(contour.bench.crest_z_m);
  const yToeLevel = sy(contour.bench.toe_z_m);
  const yBottomEdge = HEIGHT - PAD.bottom;
  const xRight = WIDTH - PAD.right;

  // --- Профиль уступа: площадка, откос забоя, подошва ------------------------
  const benchHeightM = Math.max(0, contour.bench.crest_z_m - contour.bench.toe_z_m);
  const faceAngle = Math.max(30, Math.min(90, contour.bench.face_angle_deg || 75));
  const faceRunM = benchHeightM / Math.tan((faceAngle * Math.PI) / 180);
  const xFaceTop = sx(uValues[0] - meanGap);
  const xFaceBottom = sx(uValues[0] - meanGap - faceRunM);
  const rockPath = [
    `M${xFaceBottom} ${yToeLevel}`,
    `L${xFaceTop} ${yCrest}`,
    `L${xRight + PAD.right} ${yCrest}`,
    `L${xRight + PAD.right} ${yBottomEdge}`,
    `L${xFaceBottom} ${yBottomEdge}`,
    "Z",
  ].join(" ");

  const first = rowHoles[0];
  const last = rowHoles[rowHoles.length - 1];

  function makeHoleAxis(hole: Hole) {
    const u = hole.collar.x * rowDir.x + hole.collar.y * rowDir.y;
    const uToe = hole.toe.x * rowDir.x + hole.toe.y * rowDir.y;
    const collarPx = { x: sx(u), y: sy(hole.collar.z) };
    const toePx = { x: sx(uToe), y: sy(hole.toe.z) };
    const length = holeLength(hole.collar, hole.toe) || 1;
    return makeAxis(collarPx, toePx, length, barrelWidthPx(hole.diameter_mm));
  }

  // Размерные линии строятся по последней скважине — справа от неё есть поле.
  const lastAxis = makeHoleAxis(last.hole);
  const lastLoad = loadById.get(last.hole.id);
  const lastLength = holeLength(last.hole.collar, last.hole.toe) || 1;
  const lastChargeDecks = lastLoad?.decks.filter((d) => d.kind === "charge") ?? [];
  const lastStemming = lastLoad?.decks.filter((d) => d.kind === "stemming").reduce((s, d) => s + (d.to_m - d.from_m), 0) ?? 0;
  // Суммарная длина ВВ и границы колонны — при рассредоточенном заряде это разные величины.
  const lastChargeLen = lastChargeDecks.reduce((s, d) => s + (d.to_m - d.from_m), 0);
  const chargeColumnFromM = lastChargeDecks.length ? Math.min(...lastChargeDecks.map((d) => d.from_m)) : 0;
  const chargeColumnToM = lastChargeDecks.length ? Math.max(...lastChargeDecks.map((d) => d.to_m)) : 0;
  const chargeColumnLen = chargeColumnToM - chargeColumnFromM;
  const dimX = lastAxis.collar.x + lastAxis.widthPx / 2 + 40;

  function showTip(x: number, y: number, text: string) {
    setHovered({ x, y, text });
  }

  const tooltipWidth = hovered ? Math.min(360, 7 + hovered.text.length * 5.4) : 0;
  const tooltipX = hovered ? Math.max(6, Math.min(hovered.x - tooltipWidth / 2, WIDTH - tooltipWidth - 6)) : 0;
  const tooltipY = hovered ? Math.max(20, hovered.y - 14) : 0;

  return (
    <section className="panel section-view-panel">
      <header>
        <b>Разрез по ряду</b>
        <select value={row ?? ""} onChange={(e) => onSelectedRowChange(Number(e.target.value))}>
          {rows.map((r) => <option key={r} value={r}>{r < 0 ? `Контур ${-r}` : `Ряд ${r + 1}`}</option>)}
        </select>
      </header>
      <div className="panel-body">
        <svg
          className="section-svg"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          role="img"
          aria-label="Разрез по ряду скважин"
          onMouseLeave={() => setHovered(null)}
        >
          <HoleDrawingDefs prefix={DRAW_PREFIX} />

          {/* Массив породы и профиль уступа. */}
          <path className="rock-mass" d={rockPath} fill={`url(#${DRAW_PREFIX}-rock)`} />
          <path
            className="bench-profile"
            d={`M${xFaceBottom} ${yToeLevel} L${xFaceTop} ${yCrest} L${xRight + PAD.right} ${yCrest}`}
          />
          <line className="bench-level" x1={PAD.left - 10} y1={yToeLevel} x2={xRight + PAD.right} y2={yToeLevel} />
          {/* Подписи отметок — слева над откосом, где чертёж свободен. */}
          <text className="section-level-label" x={PAD.left - 6} y={yCrest - 7} textAnchor="start">
            бровка {ruNumber(contour.bench.crest_z_m, 1)}
          </text>
          <text className="section-level-label" x={PAD.left - 6} y={yToeLevel - 6} textAnchor="start">
            подошва {ruNumber(contour.bench.toe_z_m, 1)}
          </text>

          <DepthScale
            x={PAD.left - 26}
            yTop={sy(zMax)}
            yBottom={sy(zMin)}
            fromValue={zMax}
            toValue={zMin}
            toY={sy}
            title="Отметка"
          />

          {/* Шаг сетки между первыми двумя скважинами. */}
          {rowHoles.length > 1 && (
            <HorizontalDimension
              prefix={DRAW_PREFIX}
              y={yCrest - 24}
              x1={sx(uValues[0])}
              x2={sx(uValues[1])}
              tickFromY={yCrest - 2}
              label={`a = ${ruNumber(uValues[1] - uValues[0], 1)} м`}
            />
          )}

          {rowHoles.map(({ hole }) => {
            const load = loadById.get(hole.id);
            const axis = makeHoleAxis(hole);
            const active = activeHole === hole.id;
            const delayMs = network?.downhole_delay_ms?.[hole.id];
            const subdrillFromM = Math.max(0, axis.lengthM - (hole.subdrill_m || 0));

            return (
              <g
                key={hole.id}
                className={`section-hole${active ? " active" : ""}`}
                onClick={() => setActiveHole(active ? null : hole.id)}
              >
                <HoleBarrel axis={axis} prefix={DRAW_PREFIX} subdrillFromM={subdrillFromM} highlighted={active} />

                {load?.decks.map((deck, i) => (
                  <DeckShape
                    key={i}
                    axis={axis}
                    prefix={DRAW_PREFIX}
                    deck={deck}
                    title={deckTooltip(deck)}
                    onHover={(on) => {
                      if (!on) return setHovered(null);
                      const mid = axis.at((deck.from_m + deck.to_m) / 2);
                      showTip(mid.x, mid.y, `${hole.id}: ${deckTooltip(deck)}`);
                    }}
                  />
                ))}

                {load?.primers.map((depthM, i) => (
                  <Primer
                    key={`primer-${i}`}
                    axis={axis}
                    depthM={depthM}
                    label={load.primers.length > 1 ? `Д${i + 1}` : undefined}
                    delayLabel={i === 0 && delayMs !== undefined ? `${ruNumber(delayMs, 0)} мс` : undefined}
                    nsiOffsetPx={i === 0 ? 0 : 3.2}
                    nsiExitPx={14}
                    variant={i === 0 ? "primary" : "secondary"}
                  />
                ))}

                {/* Подписи поднимаются выше выхода волновода НСИ над устьем. */}
                <text className="section-hole-id" x={axis.collar.x} y={axis.collar.y - 46} textAnchor="middle">
                  {hole.id}
                </text>
                <text className="section-hole-meta" x={axis.collar.x} y={axis.collar.y - 36} textAnchor="middle">
                  ⌀{ruNumber(hole.diameter_mm, 0)} · {ruNumber(axis.lengthM, 1)} м
                </text>
                {load && load.total_charge_kg > 0 && (
                  <text className="section-hole-mass" x={axis.toe.x} y={axis.toe.y + 18} textAnchor="middle">
                    {ruNumber(load.total_charge_kg, 0)} кг
                  </text>
                )}
              </g>
            );
          })}

          {/* Выносные размеры конструкции заряда — по последней скважине. */}
          {lastLoad && (
            <>
              {lastStemming > 0 && (
                <VerticalDimension
                  prefix={DRAW_PREFIX}
                  x={dimX}
                  y1={lastAxis.at(0).y}
                  y2={lastAxis.at(lastStemming).y}
                  tickFromX={lastAxis.collar.x + lastAxis.widthPx / 2}
                  labelSide="right"
                  label={`забойка ${ruNumber(lastStemming, 1)}`}
                />
              )}
              {chargeColumnLen > 0 && (
                <VerticalDimension
                  prefix={DRAW_PREFIX}
                  x={dimX}
                  y1={lastAxis.at(chargeColumnFromM).y}
                  y2={lastAxis.at(chargeColumnToM).y}
                  tickFromX={lastAxis.collar.x + lastAxis.widthPx / 2}
                  labelSide="right"
                  label={
                    lastChargeDecks.length > 1
                      ? `колонна ${ruNumber(chargeColumnLen, 1)} · ВВ ${ruNumber(lastChargeLen, 1)}`
                      : `заряд ${ruNumber(lastChargeLen, 1)}`
                  }
                />
              )}
              {last.hole.subdrill_m > 0 && (
                <VerticalDimension
                  prefix={DRAW_PREFIX}
                  x={dimX}
                  y1={lastAxis.at(lastLength - last.hole.subdrill_m).y}
                  y2={lastAxis.at(lastLength).y}
                  tickFromX={lastAxis.collar.x + lastAxis.widthPx / 2}
                  labelSide="right"
                  label={`перебур ${ruNumber(last.hole.subdrill_m, 1)}`}
                />
              )}
            </>
          )}

          {/* Полная глубина первой скважины — слева, у шкалы отметок. */}
          <VerticalDimension
            prefix={DRAW_PREFIX}
            x={makeHoleAxis(first.hole).collar.x - barrelWidthPx(first.hole.diameter_mm) / 2 - 16}
            y1={makeHoleAxis(first.hole).collar.y}
            y2={makeHoleAxis(first.hole).toe.y}
            tickFromX={makeHoleAxis(first.hole).collar.x - barrelWidthPx(first.hole.diameter_mm) / 2}
            label={`${ruNumber(holeLength(first.hole.collar, first.hole.toe), 1)} м`}
          />

          {hovered && (
            <g className="section-tooltip" pointerEvents="none">
              <rect x={tooltipX} y={tooltipY - 15} width={tooltipWidth} height={19} rx={5} />
              <text x={tooltipX + tooltipWidth / 2} y={tooltipY - 2} textAnchor="middle">{hovered.text}</text>
            </g>
          )}
        </svg>

        <div className="section-legend">
          <span><i className="legend-charge" /> заряд</span>
          <span><i className="legend-stemming" /> забойка</span>
          <span><i className="legend-air" /> возд. промежуток</span>
          <span><i className="legend-primer" /> боевик + НСИ</span>
          <span><i className="legend-subdrill" /> перебур</span>
          <span><i className="legend-rock" /> массив</span>
          <small className="section-note">диаметр скважины показан вне масштаба</small>
        </div>
      </div>
    </section>
  );
}
