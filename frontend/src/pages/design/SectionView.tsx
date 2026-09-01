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
import { surfaceElevation } from "../../lib/surfaces";
import type { BlockContour, Hole, HoleLoad, InitiationNetwork, SurfaceSet, ValidationWarning } from "../../types/design";
import { isExplosiveDeckKind, networkTies, primerDepths } from "../../types/design";
import type { HoleHealth } from "./holeHealth";
import { healthColor } from "./holeHealth";

const DRAW_PREFIX = "sec";
const VIEW_HEIGHT = 460;
const SCALE_X = 46; // отступ слева под шкалу отметок
const FIT_MARGIN = 0.9;
/** Целевая ширина ствола самой крупной скважины при вписывании, px. */
const TARGET_BARREL_PX = 15;
/** Ниже этой ширины ствол перестаёт читаться. */
const MIN_BARREL_PX = 3;
/** Сдвиг курсора, после которого жест считается панорамой, а не кликом. */
const DRAG_THRESHOLD_PX = 4;

type Tooltip = { x: number; y: number; text: string };

export function SectionView({
  contour,
  holes,
  loads,
  surfaces,
  network,
  warnings,
  rowAzimuthDeg,
  selectedRow,
  onSelectedRowChange,
  healthById,
  selectedHoleIds,
  onHoleInspect,
}: {
  contour: BlockContour;
  holes: Hole[];
  loads: HoleLoad[];
  surfaces?: SurfaceSet;
  network?: InitiationNetwork | null;
  warnings?: ValidationWarning[];
  rowAzimuthDeg: number;
  selectedRow: number | null;
  onSelectedRowChange: (row: number) => void;
  healthById?: Record<string, HoleHealth>;
  selectedHoleIds?: Set<string>;
  onHoleInspect?: (holeId: string) => void;
}) {
  // <svg> появляется только когда в ряду есть скважины, поэтому наблюдаем за
  // ним через callback-ref: обычный useRef с эффектом на [] не сработал бы,
  // если первый рендер прошёл по ветке «сетки ещё нет».
  const [svgEl, setSvgEl] = useState<SVGSVGElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const attachSvg = useCallback((el: SVGSVGElement | null) => {
    svgRef.current = el;
    setSvgEl(el);
  }, []);
  const [viewport, setViewport] = useState<Viewport>({ width: 860, height: VIEW_HEIGHT });
  const [camera, setCamera] = useState<Camera | null>(null);
  const [exaggeration, setExaggeration] = useState(1);
  const [hovered, setHovered] = useState<Tooltip | null>(null);
  const [activeHole, setActiveHole] = useState<string | null>(null);
  const [panFrom, setPanFrom] = useState<{ screen: Vec2; camera: Camera } | null>(null);
  /** Панорама «съедает» клик: иначе каждое перетаскивание переключало подсветку. */
  const dragMoved = useRef(false);

  useEffect(() => {
    if (!svgEl) return;
    const observer = new ResizeObserver((entries) => {
      const box = entries[0]?.contentRect;
      if (box && box.width > 0) setViewport({ width: box.width, height: box.height || VIEW_HEIGHT });
    });
    observer.observe(svgEl);
    return () => observer.disconnect();
  }, [svgEl]);

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

  const rowTies = useMemo(() => {
    if (!network) return [];
    const ids = new Set(rowHoles.map(({ hole }) => hole.id));
    return networkTies(network).filter((tie) => ids.has(tie.from_hole) && ids.has(tie.to_hole));
  }, [network, rowHoles]);

  /** Границы чертежа в мировых координатах (u вдоль ряда, z — отметка). */
  const bounds = useMemo(() => {
    if (!rowHoles.length) return null;
    const uValues = rowHoles.map((r) => r.u);
    const zValues = rowHoles.flatMap((r) => [r.hole.collar.z, r.hole.toe.z]);
    zValues.push(contour.bench.crest_z_m, contour.bench.toe_z_m);
    for (const { hole } of rowHoles) {
      const topZ = surfaceElevation(surfaces?.top, hole.collar.x, hole.collar.y);
      const floorZ = surfaceElevation(surfaces?.floor, hole.collar.x, hole.collar.y);
      if (topZ !== null) zValues.push(topZ);
      if (floorZ !== null) zValues.push(floorZ);
    }
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
      minDiameterM: Math.min(...rowHoles.map((r) => r.hole.diameter_mm)) / 1000,
    };
  }, [rowHoles, contour.bench, surfaces]);

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
        exaggerationFactor({
          maxDiameterM: bounds.maxDiameterM,
          minDiameterM: bounds.minDiameterM,
          pxPerM: scale,
          targetPx: TARGET_BARREL_PX,
          maxWidthPx: bounds.meanGap * scale * 0.3,
          minWidthPx: MIN_BARREL_PX,
        }),
      );
    },
    [bounds, viewport.width, viewport.height],
  );

  // Вписываем заново при смене ряда, размера панели и самой геометрии: иначе
  // после правки отметок уступа или глубины камера остаётся смотреть в пустоту.
  const geometryKey = bounds
    ? [bounds.uMin, bounds.uMax, bounds.zMin, bounds.zMax].map((v) => Math.round(v * 100)).join(",")
    : "";
  const fitKey = `${row}:${rowHoles.length}:${Math.round(viewport.width)}:${geometryKey}`;
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

  const profile = sampleRowProfile(rowHoles, surfaces, contour.bench.crest_z_m, contour.bench.toe_z_m);
  const yCrest = sy(profile.crestZ);
  const yToeLevel = sy(profile.floorZ);
  const xFaceTop = toScreen(bounds!.uFaceTop, 0).x;
  const xFaceBottom = toScreen(bounds!.uFaceTop - bounds!.faceRunM, 0).x;
  const topPolyline = profile.top.map((p) => `${toScreen(p.u, p.z).x} ${sy(p.z)}`);
  const rockCrest = topPolyline.length ? `L${topPolyline.join(" L")}` : `L${xFaceTop} ${yCrest} L${viewport.width + 40} ${yCrest}`;

  const rockPath = [
    `M${xFaceBottom} ${yToeLevel}`,
    `L${xFaceTop} ${sy(profile.top[0]?.z ?? profile.crestZ)}`,
    rockCrest.startsWith("L") ? rockCrest : `L${xFaceTop} ${yCrest}`,
    `L${viewport.width + 40} ${sy(profile.top[profile.top.length - 1]?.z ?? profile.crestZ)}`,
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
    // Ширина ствола ровно та, что заявлена подписью ⌀ ×N: нижний предел уже
    // заложен в сам коэффициент, отсекать здесь нельзя — подпись начнёт врать.
    const widthPx = (hole.diameter_mm / 1000) * cam.scale * exaggeration;
    return makeAxis(collarPx, toePx, length, widthPx);
  }

  // Скважины, попавшие в текущий кадр. В режиме «Уступ» длинный ряд уходит за
  // край, поэтому и размеры, и полную глубину привязываем к видимым скважинам,
  // а не к первой/последней в ряду — иначе выносные размеры уезжают с экрана.
  const visible = rowHoles.filter(({ hole }) => {
    const x = makeHoleAxis(hole).collar.x;
    return x > SCALE_X + 24 && x < viewport.width - 150;
  });
  const first = visible[0] ?? rowHoles[0];
  const dimHole = visible.length ? visible[visible.length - 1] : null;
  const firstAxis = makeHoleAxis(first.hole);
  const dimAxis = dimHole ? makeHoleAxis(dimHole.hole) : null;
  const dimLoad = dimHole ? loadById.get(dimHole.hole.id) : undefined;
  const dimLength = dimHole ? holeLength(dimHole.hole.collar, dimHole.hole.toe) || 1 : 0;
  const dimChargeDecks = dimLoad?.decks.filter((d) => isExplosiveDeckKind(d.kind)) ?? [];
  const dimStemming = dimLoad?.decks.filter((d) => d.kind === "stemming").reduce((s, d) => s + (d.to_m - d.from_m), 0) ?? 0;
  const dimChargeLen = dimChargeDecks.reduce((s, d) => s + (d.to_m - d.from_m), 0);
  const chargeColumnFromM = dimChargeDecks.length ? Math.min(...dimChargeDecks.map((d) => d.from_m)) : 0;
  const chargeColumnToM = dimChargeDecks.length ? Math.max(...dimChargeDecks.map((d) => d.to_m)) : 0;
  const dimX = dimAxis ? dimAxis.collar.x + dimAxis.widthPx / 2 + 40 : 0;

  // Считаем сами замечания, а не помеченные скважины: на одной скважине их
  // может быть несколько, и часть замечаний относится к другим рядам.
  const rowWarningCount = rowHoles.reduce((sum, { hole }) => sum + (warningsByHole.get(hole.id)?.length ?? 0), 0);
  const totalWarningCount = warnings?.length ?? 0;
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
    dragMoved.current = false;
    setPanFrom({ screen: { x: e.clientX - rect.left, y: e.clientY - rect.top }, camera });
  }

  function onPointerMove(e: React.PointerEvent<SVGSVGElement>) {
    if (!panFrom) return;
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    const dx = e.clientX - rect.left - panFrom.screen.x;
    const dy = e.clientY - rect.top - panFrom.screen.y;
    if (Math.hypot(dx, dy) > DRAG_THRESHOLD_PX) dragMoved.current = true;
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
            ref={attachSvg}
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
              d={
                profile.top.length
                  ? `M${xFaceBottom} ${yToeLevel} L${xFaceTop} ${sy(profile.top[0].z)} L${topPolyline.join(" L")}`
                  : `M${xFaceBottom} ${yToeLevel} L${xFaceTop} ${yCrest} L${viewport.width + 40} ${yCrest}`
              }
            />
            <line className="bench-level" x1={SCALE_X} y1={yToeLevel} x2={viewport.width} y2={yToeLevel} />
            <text className="section-level-label" x={SCALE_X + 8} y={yCrest - 7} textAnchor="start">
              бровка {ruNumber(profile.crestZ, 1)}
            </text>
            <text className="section-level-label" x={SCALE_X + 8} y={yToeLevel - 6} textAnchor="start">
              подошва {ruNumber(profile.floorZ, 1)}
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
              const selectedOnPlan = selectedHoleIds?.has(hole.id) ?? false;
              const holeWarnings = warningsByHole.get(hole.id);
              const holeHealth = healthById?.[hole.id];
              const delayMs = network?.downhole_delay_ms?.[hole.id];
              const subdrillFromM = Math.max(0, axis.lengthM - (hole.subdrill_m || 0));
              const holePrimers = load ? primerDepths(load) : [];

              return (
                <g
                  key={hole.id}
                  className={`section-hole${active || selectedOnPlan ? " active" : ""}${holeWarnings || (holeHealth && holeHealth.severity > 0) ? " flagged" : ""}`}
                  onClick={() => {
                    if (dragMoved.current) return;
                    setActiveHole(active ? null : hole.id);
                    onHoleInspect?.(hole.id);
                  }}
                >
                  {holeHealth && holeHealth.severity > 0 && (
                    <circle
                      cx={axis.collar.x}
                      cy={axis.collar.y - axis.widthPx / 2 - 8}
                      r={4}
                      className="section-health-dot"
                      fill={healthColor(holeHealth.code, holeHealth.severity)}
                    />
                  )}
                  <HoleBarrel axis={axis} prefix={DRAW_PREFIX} subdrillFromM={subdrillFromM} highlighted={active || selectedOnPlan} />

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

                  {holePrimers.map((depthM, i) => (
                    <Primer
                      key={`primer-${i}`}
                      axis={axis}
                      depthM={depthM}
                      label={detail.showPrimerLabels && holePrimers.length > 1 ? `Д${i + 1}` : undefined}
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

            {rowTies.map((tie, tieIndex) => {
              const from = rowHoles.find(({ hole }) => hole.id === tie.from_hole);
              const to = rowHoles.find(({ hole }) => hole.id === tie.to_hole);
              if (!from || !to) return null;
              const y = yCrest - 10 - tieIndex * 12;
              const x1 = makeHoleAxis(from.hole).collar.x;
              const x2 = makeHoleAxis(to.hole).collar.x;
              return (
                <g key={tie.id || `tie-${tieIndex}`} className="section-network-tie">
                  <line x1={x1} y1={y} x2={x2} y2={y} />
                  <text x={(x1 + x2) / 2} y={y - 3} textAnchor="middle">
                    {tie.delay_ms > 0 ? `${ruNumber(tie.delay_ms, 0)} мс` : "связь"}
                  </text>
                </g>
              );
            })}

            {dimAxis && dimHole && dimLoad && (
              <>
                {dimStemming > 0 && (
                  <VerticalDimension
                    prefix={DRAW_PREFIX}
                    x={dimX}
                    y1={dimAxis.at(0).y}
                    y2={dimAxis.at(dimStemming).y}
                    tickFromX={dimAxis.collar.x + dimAxis.widthPx / 2}
                    labelSide="right"
                    label={`забойка ${ruNumber(dimStemming, 1)}`}
                  />
                )}
                {chargeColumnToM > chargeColumnFromM && (
                  <VerticalDimension
                    prefix={DRAW_PREFIX}
                    x={dimX}
                    y1={dimAxis.at(chargeColumnFromM).y}
                    y2={dimAxis.at(chargeColumnToM).y}
                    tickFromX={dimAxis.collar.x + dimAxis.widthPx / 2}
                    labelSide="right"
                    label={
                      dimChargeDecks.length > 1
                        ? `колонна ${ruNumber(chargeColumnToM - chargeColumnFromM, 1)} · ВВ ${ruNumber(dimChargeLen, 1)}`
                        : `заряд ${ruNumber(dimChargeLen, 1)}`
                    }
                  />
                )}
                {dimHole.hole.subdrill_m > 0 && (
                  <VerticalDimension
                    prefix={DRAW_PREFIX}
                    x={dimX}
                    y1={dimAxis.at(dimLength - dimHole.hole.subdrill_m).y}
                    y2={dimAxis.at(dimLength).y}
                    tickFromX={dimAxis.collar.x + dimAxis.widthPx / 2}
                    labelSide="right"
                    label={`перебур ${ruNumber(dimHole.hole.subdrill_m, 1)}`}
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
          <span><i className="legend-charge" /> заряд (несколько ВВ)</span>
          <span><i className="legend-stemming" /> забойка</span>
          <span><i className="legend-air" /> возд. промежуток</span>
          <span><i className="legend-water" /> вода</span>
          <span><i className="legend-inert" /> инерт</span>
          <span><i className="legend-primer" /> боевик + НСИ</span>
          <span><i className="legend-subdrill" /> перебур</span>
          <span><i className="legend-rock" /> массив</span>
          {rowWarningCount > 0 && (
            <span className="legend-warning">
              <i className="legend-flag" /> замечаний в ряду: {rowWarningCount}
              {totalWarningCount > rowWarningCount && ` · всего по блоку: ${totalWarningCount}`}
            </span>
          )}
          <small className="section-note">масштаб по осям единый · ⌀ скважин ×{ruNumber(exaggeration, 0)}</small>
        </div>
      </div>
    </section>
  );
}

function sampleRowProfile(
  rowHoles: Array<{ hole: Hole; u: number }>,
  surfaces: SurfaceSet | undefined,
  fallbackCrest: number,
  fallbackFloor: number,
) {
  const top: Array<{ u: number; z: number }> = [];
  const floor: Array<{ u: number; z: number }> = [];
  if (!rowHoles.length) {
    return { top, floor, crestZ: fallbackCrest, floorZ: fallbackFloor };
  }
  const first = rowHoles[0];
  const last = rowHoles[rowHoles.length - 1];
  const span = Math.max(1e-6, last.u - first.u);
  const samples = Math.max(8, Math.min(48, rowHoles.length * 3));
  for (let i = 0; i <= samples; i += 1) {
    const t = i / samples;
    const u = first.u + span * t;
    const x = first.hole.collar.x + (last.hole.collar.x - first.hole.collar.x) * t;
    const y = first.hole.collar.y + (last.hole.collar.y - first.hole.collar.y) * t;
    const topZ = surfaceElevation(surfaces?.top, x, y);
    const floorZ = surfaceElevation(surfaces?.floor, x, y);
    top.push({ u, z: topZ ?? fallbackCrest });
    floor.push({ u, z: floorZ ?? fallbackFloor });
  }
  return {
    top,
    floor,
    crestZ: top.reduce((s, p) => s + p.z, 0) / top.length,
    floorZ: floor.reduce((s, p) => s + p.z, 0) / floor.length,
  };
}
