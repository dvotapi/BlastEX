import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DeckShape } from "../../components/holeDrawing/DeckShape";
import { DepthScale } from "../../components/holeDrawing/DepthScale";
import { HorizontalDimension, VerticalDimension } from "../../components/holeDrawing/DimensionLine";
import { HoleBarrel } from "../../components/holeDrawing/HoleBarrel";
import { ScaleBar } from "../../components/holeDrawing/ScaleBar";
import { WarningBadge } from "../../components/holeDrawing/WarningBadge";
import { HoleDrawingDefs } from "../../components/holeDrawing/defs";
import { Primer } from "../../components/holeDrawing/Primer";
import { deckTooltip, exaggerationFactor, labelDetail, makeAxis } from "../../components/holeDrawing/geometry";
import { ruNumber } from "../../lib/format";
import {
  type Camera,
  type Vec2,
  type Viewport,
  holeLength,
  localBasis,
  screenToWorld,
  worldToScreen,
  zoomAt,
} from "../../lib/geometry2d";
import type { BlockContour, Hole, HoleLoad, InitiationNetwork, ValidationWarning } from "../../types/design";

const DRAW_PREFIX = "sec";
const VIEW_HEIGHT = 460;
const SCALE_X = 46; // отступ слева под шкалу отметок
const FIT_MARGIN = 0.9;
/** Целевая ширина ствола самой крупной скважины при вписывании, px. */
const TARGET_BARREL_PX = 15;

type Tooltip = { x: number; y: number; text: string };

export function SectionView({
  contour,
  holes,
  loads,
  network,
  warnings,
  rowAzimuthDeg,
  selectedRow,
  onSelectedRowChange,
}: {
  contour: BlockContour;
  holes: Hole[];
  loads: HoleLoad[];
  network?: InitiationNetwork | null;
  warnings?: ValidationWarning[];
  rowAzimuthDeg: number;
  selectedRow: number | null;
  onSelectedRowChange: (row: number) => void;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [viewport, setViewport] = useState<Viewport>({ width: 860, height: VIEW_HEIGHT });
  const [camera, setCamera] = useState<Camera | null>(null);
  const [exaggeration, setExaggeration] = useState(1);
  const [hovered, setHovered] = useState<Tooltip | null>(null);
  const [activeHole, setActiveHole] = useState<string | null>(null);
  const [panFrom, setPanFrom] = useState<{ screen: Vec2; camera: Camera } | null>(null);

  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const box = entries[0]?.contentRect;
      if (box && box.width > 0) setViewport({ width: box.width, height: box.height || VIEW_HEIGHT });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const loadById = useMemo(() => {
    const map = new Map<string, HoleLoad>();
    for (const load of loads) map.set(load.hole_id, load);
    return map;
  }, [loads]);

  /** Предупреждения сервера, разложенные по скважинам. */
  const warningsByHole = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const w of warnings ?? []) {
      if (!w.hole_id) continue;
      const list = map.get(w.hole_id) ?? [];
      list.push(w.message);
      map.set(w.hole_id, list);
    }
    return map;
  }, [warnings]);

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

  /** Границы чертежа в мировых координатах (u вдоль ряда, z — отметка). */
  const bounds = useMemo(() => {
    if (!rowHoles.length) return null;
    const uValues = rowHoles.map((r) => r.u);
    const zValues = rowHoles.flatMap((r) => [r.hole.collar.z, r.hole.toe.z]);
    zValues.push(contour.bench.crest_z_m, contour.bench.toe_z_m);
    const gaps = uValues.slice(1).map((u, i) => u - uValues[i]);
    const meanGap = gaps.length ? gaps.reduce((a, b) => a + b, 0) / gaps.length : 5;
    const benchHeightM = Math.max(0, contour.bench.crest_z_m - contour.bench.toe_z_m);
    const faceAngle = Math.max(30, Math.min(90, contour.bench.face_angle_deg || 75));
    const faceRunM = benchHeightM / Math.tan((faceAngle * Math.PI) / 180);
    return {
      meanGap,
      faceRunM,
      uFaceTop: Math.min(...uValues) - meanGap,
      uMin: Math.min(...uValues) - meanGap - faceRunM,
      uMax: Math.max(...uValues) + meanGap * 0.6,
      zMin: Math.min(...zValues),
      zMax: Math.max(...zValues),
      maxDiameterM: Math.max(...rowHoles.map((r) => r.hole.diameter_mm)) / 1000,
    };
  }, [rowHoles, contour.bench]);

  /**
   * "bench" — уступ на всю высоту панели, длинный ряд листается панорамой
   * (так чертёж остаётся читаемым при любом числе скважин);
   * "row" — весь ряд целиком, обзорный вид.
   */
  const fit = useCallback(
    (mode: "bench" | "row" = "bench") => {
      if (!bounds) return;
      const uSpan = Math.max(1e-6, bounds.uMax - bounds.uMin);
      const zSpan = Math.max(1e-6, bounds.zMax - bounds.zMin);
      const usableW = viewport.width - SCALE_X - 30;
      const usableH = viewport.height - 96;
      // Единый масштаб по обеим осям: углы наклона скважин и откоса — истинные.
      const byRow = Math.min(usableW / uSpan, usableH / zSpan) * FIT_MARGIN;
      const byBench = (usableH / zSpan) * FIT_MARGIN;
      const scale = Math.min(400, Math.max(0.5, mode === "row" ? byRow : byBench));
      const showsWholeRow = uSpan * scale <= usableW;
      const next = {
        x: showsWholeRow
          ? (bounds.uMin + bounds.uMax) / 2 + SCALE_X / 2 / scale
          : bounds.uMin + usableW / 2 / scale,
        y: (bounds.zMin + bounds.zMax) / 2 - 12 / scale,
        scale,
      };
      setCamera(next);
      setExaggeration(
        exaggerationFactor(bounds.maxDiameterM, scale, TARGET_BARREL_PX, bounds.meanGap * scale * 0.3),
      );
    },
    [bounds, viewport.width, viewport.height],
  );

  // Вписываем при первой отрисовке и при смене ряда/размера панели.
  const fitKey = `${row}:${rowHoles.length}:${Math.round(viewport.width)}`;
  const lastFitKey = useRef("");
  useEffect(() => {
    if (!bounds) return;
    if (lastFitKey.current === fitKey) return;
    lastFitKey.current = fitKey;
    fit();
  }, [bounds, fitKey, fit]);

  if (!rows.length || !rowHoles.length) {
    return (
      <section className="panel">
        <header><b>Разрез по ряду</b></header>
        <div className="panel-body"><small>Постройте сетку скважин, чтобы увидеть разрез.</small></div>
      </section>
    );
  }

  const cam = camera ?? { x: 0, y: contour.bench.crest_z_m, scale: 10 };
  const toScreen = (u: number, z: number) => worldToScreen(cam, viewport, { x: u, y: z });
  const sy = (z: number) => toScreen(0, z).y;

  const yCrest = sy(contour.bench.crest_z_m);
  const yToeLevel = sy(contour.bench.toe_z_m);
  const xFaceTop = toScreen(bounds!.uFaceTop, 0).x;
  const xFaceBottom = toScreen(bounds!.uFaceTop - bounds!.faceRunM, 0).x;

  const rockPath = [
    `M${xFaceBottom} ${yToeLevel}`,
    `L${xFaceTop} ${yCrest}`,
    `L${viewport.width + 40} ${yCrest}`,
    `L${viewport.width + 40} ${viewport.height + 40}`,
    `L${xFaceBottom} ${viewport.height + 40}`,
    "Z",
  ].join(" ");

  // Видимый диапазон отметок — шкала слева всегда покрывает то, что на экране.
  const zVisibleTop = screenToWorld(cam, viewport, { x: 0, y: 0 }).y;
  const zVisibleBottom = screenToWorld(cam, viewport, { x: 0, y: viewport.height }).y;

  function makeHoleAxis(hole: Hole) {
    const u = hole.collar.x * rowDir.x + hole.collar.y * rowDir.y;
    const uToe = hole.toe.x * rowDir.x + hole.toe.y * rowDir.y;
    const collarPx = toScreen(u, hole.collar.z);
    const toePx = toScreen(uToe, hole.toe.z);
    const length = holeLength(hole.collar, hole.toe) || 1;
    // Ширина ствола: реальный диаметр × общий коэффициент преувеличения.
    const widthPx = Math.max(3, (hole.diameter_mm / 1000) * cam.scale * exaggeration);
    return makeAxis(collarPx, toePx, length, widthPx);
  }

  const first = rowHoles[0];
  const last = rowHoles[rowHoles.length - 1];
  const firstAxis = makeHoleAxis(first.hole);
  const lastAxis = makeHoleAxis(last.hole);
  const lastLoad = loadById.get(last.hole.id);
  const lastLength = holeLength(last.hole.collar, last.hole.toe) || 1;
  const lastChargeDecks = lastLoad?.decks.filter((d) => d.kind === "charge") ?? [];
  const lastStemming = lastLoad?.decks.filter((d) => d.kind === "stemming").reduce((s, d) => s + (d.to_m - d.from_m), 0) ?? 0;
  const lastChargeLen = lastChargeDecks.reduce((s, d) => s + (d.to_m - d.from_m), 0);
  const chargeColumnFromM = lastChargeDecks.length ? Math.min(...lastChargeDecks.map((d) => d.from_m)) : 0;
  const chargeColumnToM = lastChargeDecks.length ? Math.max(...lastChargeDecks.map((d) => d.to_m)) : 0;
  const dimX = lastAxis.collar.x + lastAxis.widthPx / 2 + 40;

  const flaggedCount = rowHoles.filter(({ hole }) => warningsByHole.has(hole.id)).length;
  // Плотность скважин на экране решает, какие подписи ещё читаемы.
  const spacingPx = bounds!.meanGap * cam.scale;
  const detail = labelDetail(spacingPx);

  function onWheel(e: React.WheelEvent<SVGSVGElement>) {
    if (!camera) return;
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    const point = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    setCamera(zoomAt(camera, viewport, point, e.deltaY < 0 ? 1.12 : 1 / 1.12, 0.5, 400));
  }

  function onPointerDown(e: React.PointerEvent<SVGSVGElement>) {
    if (!camera) return;
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    (e.target as Element).setPointerCapture?.(e.pointerId);
    setPanFrom({ screen: { x: e.clientX - rect.left, y: e.clientY - rect.top }, camera });
  }

  function onPointerMove(e: React.PointerEvent<SVGSVGElement>) {
    if (!panFrom) return;
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    const dx = e.clientX - rect.left - panFrom.screen.x;
    const dy = e.clientY - rect.top - panFrom.screen.y;
    setCamera({
      x: panFrom.camera.x - dx / panFrom.camera.scale,
      y: panFrom.camera.y + dy / panFrom.camera.scale,
      scale: panFrom.camera.scale,
    });
  }

  function endPan() {
    setPanFrom(null);
  }

  const tooltipWidth = hovered ? Math.min(420, 12 + hovered.text.length * 5.6) : 0;
  const tooltipX = hovered ? Math.max(6, Math.min(hovered.x - tooltipWidth / 2, viewport.width - tooltipWidth - 6)) : 0;
  const tooltipY = hovered ? Math.max(22, hovered.y - 14) : 0;

  return (
    <section className="panel section-view-panel">
      <header>
        <b>Разрез по ряду</b>
        <select value={row ?? ""} onChange={(e) => onSelectedRowChange(Number(e.target.value))}>
          {rows.map((r) => <option key={r} value={r}>{r < 0 ? `Контур ${-r}` : `Ряд ${r + 1}`}</option>)}
        </select>
      </header>
      <div className="panel-body">
        <div className="section-canvas-wrap">
          <svg
            ref={svgRef}
            className={`section-svg${panFrom ? " panning" : ""}`}
            role="img"
            aria-label="Разрез по ряду скважин"
            onWheel={onWheel}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={endPan}
            onPointerCancel={endPan}
            onMouseLeave={() => { setHovered(null); endPan(); }}
          >
            <HoleDrawingDefs prefix={DRAW_PREFIX} />

            <path className="rock-mass" d={rockPath} fill={`url(#${DRAW_PREFIX}-rock)`} />
            <path
              className="bench-profile"
              d={`M${xFaceBottom} ${yToeLevel} L${xFaceTop} ${yCrest} L${viewport.width + 40} ${yCrest}`}
            />
            <line className="bench-level" x1={SCALE_X} y1={yToeLevel} x2={viewport.width} y2={yToeLevel} />
            <text className="section-level-label" x={SCALE_X + 8} y={yCrest - 7} textAnchor="start">
              бровка {ruNumber(contour.bench.crest_z_m, 1)}
            </text>
            <text className="section-level-label" x={SCALE_X + 8} y={yToeLevel - 6} textAnchor="start">
              подошва {ruNumber(contour.bench.toe_z_m, 1)}
            </text>

            <DepthScale
              x={SCALE_X}
              yTop={0}
              yBottom={viewport.height}
              fromValue={zVisibleTop}
              toValue={zVisibleBottom}
              toY={sy}
              title="Отметка"
            />

            {rowHoles.length > 1 && (
              <HorizontalDimension
                prefix={DRAW_PREFIX}
                y={yCrest - 24}
                x1={firstAxis.collar.x}
                x2={makeHoleAxis(rowHoles[1].hole).collar.x}
                tickFromY={yCrest - 2}
                label={`a = ${ruNumber(rowHoles[1].u - first.u, 1)} м`}
              />
            )}

            {rowHoles.map(({ hole }, holeIndex) => {
              const load = loadById.get(hole.id);
              const axis = makeHoleAxis(hole);
              const active = activeHole === hole.id;
              const holeWarnings = warningsByHole.get(hole.id);
              const delayMs = network?.downhole_delay_ms?.[hole.id];
              const subdrillFromM = Math.max(0, axis.lengthM - (hole.subdrill_m || 0));

              return (
                <g
                  key={hole.id}
                  className={`section-hole${active ? " active" : ""}${holeWarnings ? " flagged" : ""}`}
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
                        setHovered({ x: mid.x, y: mid.y, text: `${hole.id}: ${deckTooltip(deck)}` });
                      }}
                    />
                  ))}

                  {load?.primers.map((depthM, i) => (
                    <Primer
                      key={`primer-${i}`}
                      axis={axis}
                      depthM={depthM}
                      label={detail.showPrimerLabels && load.primers.length > 1 ? `Д${i + 1}` : undefined}
                      delayLabel={detail.showPrimerLabels && i === 0 && delayMs !== undefined ? `${ruNumber(delayMs, 0)} мс` : undefined}
                      nsiOffsetPx={i === 0 ? 0 : 3.2}
                      nsiExitPx={14}
                      variant={i === 0 ? "primary" : "secondary"}
                    />
                  ))}

                  {detail.showId && holeIndex % detail.idEvery === 0 && (
                    <text className="section-hole-id" x={axis.collar.x} y={axis.collar.y - 46} textAnchor="middle">
                      {hole.id}
                    </text>
                  )}
                  {detail.showMeta && (
                    <text className="section-hole-meta" x={axis.collar.x} y={axis.collar.y - 36} textAnchor="middle">
                      ⌀{ruNumber(hole.diameter_mm, 0)} · {ruNumber(axis.lengthM, 1)} м
                    </text>
                  )}
                  {detail.showMass && load && load.total_charge_kg > 0 && (
                    <text className="section-hole-mass" x={axis.toe.x} y={axis.toe.y + 18} textAnchor="middle">
                      {ruNumber(load.total_charge_kg, 0)} кг
                    </text>
                  )}

                  {holeWarnings && (
                    <WarningBadge
                      x={axis.collar.x + axis.widthPx / 2 + 9}
                      y={axis.collar.y - 26}
                      count={holeWarnings.length}
                      onHover={(on) =>
                        setHovered(
                          on
                            ? { x: axis.collar.x, y: axis.collar.y - 26, text: holeWarnings.join(" · ") }
                            : null,
                        )
                      }
                    />
                  )}
                </g>
              );
            })}

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
                {chargeColumnToM > chargeColumnFromM && (
                  <VerticalDimension
                    prefix={DRAW_PREFIX}
                    x={dimX}
                    y1={lastAxis.at(chargeColumnFromM).y}
                    y2={lastAxis.at(chargeColumnToM).y}
                    tickFromX={lastAxis.collar.x + lastAxis.widthPx / 2}
                    labelSide="right"
                    label={
                      lastChargeDecks.length > 1
                        ? `колонна ${ruNumber(chargeColumnToM - chargeColumnFromM, 1)} · ВВ ${ruNumber(lastChargeLen, 1)}`
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

            <VerticalDimension
              prefix={DRAW_PREFIX}
              x={firstAxis.collar.x - firstAxis.widthPx / 2 - 16}
              y1={firstAxis.collar.y}
              y2={firstAxis.toe.y}
              tickFromX={firstAxis.collar.x - firstAxis.widthPx / 2}
              label={`${ruNumber(holeLength(first.hole.collar, first.hole.toe), 1)} м`}
            />

            <ScaleBar
              x={SCALE_X + 10}
              y={viewport.height - 16}
              pxPerM={cam.scale}
              note={`⌀ ×${ruNumber(exaggeration, 0)}`}
            />

            {hovered && (
              <g className="section-tooltip" pointerEvents="none">
                <rect x={tooltipX} y={tooltipY - 15} width={tooltipWidth} height={19} rx={5} />
                <text x={tooltipX + tooltipWidth / 2} y={tooltipY - 2} textAnchor="middle">{hovered.text}</text>
              </g>
            )}
          </svg>

          <div className="section-controls">
            <button type="button" onClick={() => fit("bench")} title="Уступ на всю высоту">Уступ</button>
            <button type="button" onClick={() => fit("row")} title="Показать ряд целиком">Ряд</button>
            <button
              type="button"
              onClick={() => camera && setCamera(zoomAt(camera, viewport, { x: viewport.width / 2, y: viewport.height / 2 }, 1.25, 0.5, 400))}
              title="Приблизить"
            >+</button>
            <button
              type="button"
              onClick={() => camera && setCamera(zoomAt(camera, viewport, { x: viewport.width / 2, y: viewport.height / 2 }, 1 / 1.25, 0.5, 400))}
              title="Отдалить"
            >−</button>
          </div>
          <div className="section-hint">колесо — масштаб, перетаскивание — панорама</div>
        </div>

        <div className="section-legend">
          <span><i className="legend-charge" /> заряд</span>
          <span><i className="legend-stemming" /> забойка</span>
          <span><i className="legend-air" /> возд. промежуток</span>
          <span><i className="legend-primer" /> боевик + НСИ</span>
          <span><i className="legend-subdrill" /> перебур</span>
          <span><i className="legend-rock" /> массив</span>
          {flaggedCount > 0 && (
            <span className="legend-warning"><i className="legend-flag" /> замечаний: {flaggedCount}</span>
          )}
          <small className="section-note">масштаб по осям единый · ⌀ скважин ×{ruNumber(exaggeration, 0)}</small>
        </div>
      </div>
    </section>
  );
}
