import { useEffect, useMemo, useRef, useState } from "react";
import { ruNumber } from "../../lib/format";
import {
  Camera,
  Vec2,
  Viewport,
  distance,
  rectContains,
  rectFromCorners,
  screenToWorld,
  worldToScreen,
  zoomAt,
} from "../../lib/geometry2d";
import type { BlastDomain, BlockContour, Hole, HoleLoad, InitiationNetwork, Isoline, Point3, Receptor, VibrationPrediction } from "../../types/design";
import { RECEPTOR_KIND_LABELS, networkTies } from "../../types/design";

const HOLE_HIT_RADIUS_PX = 11;
const VERTEX_HIT_RADIUS_PX = 9;
const EDGE_HIT_RADIUS_PX = 8;
const RECEPTOR_HIT_RADIUS_PX = 12;
const NEIGHBOUR_COUNT = 5;
const SPACING_TOLERANCE_M = 0.5;

type Mode = "contour" | "holes" | "tie" | "timing";

type DragState =
  | { kind: "none" }
  | { kind: "pan"; startScreen: Vec2; startCamera: Camera }
  | { kind: "vertex"; index: number }
  | { kind: "holes"; ids: string[]; startWorld: Vec2; deltaWorld: Vec2 }
  | { kind: "rubber"; startScreen: Vec2; currentScreen: Vec2 };

export function PlanCanvas({
  contour,
  holes,
  mode,
  selected,
  onSelectedChange,
  onContourVerticesChange,
  onToggleFreeFace,
  onMoveHoles,
  onAddHole,
  camera,
  onCameraChange,
  spacingHint,
  loadsById,
  network,
  isolines,
  timesMs,
  animationMs,
  pendingTieFromId,
  onTieHoles,
  onClearPendingTie,
  domains,
  drawingDomainId,
  onDomainVertexAdd,
  mapValues,
  mapRange,
  receptors,
  selectedReceptorId,
  placingReceptor,
  onAddReceptor,
  onSelectReceptor,
  vibrationPredictions,
}: {
  contour: BlockContour;
  holes: Hole[];
  mode: Mode;
  selected: Set<string>;
  onSelectedChange: (ids: Set<string>) => void;
  onContourVerticesChange: (vertices: Point3[]) => void;
  onToggleFreeFace: (edgeIndex: number) => void;
  onMoveHoles: (ids: string[], dx: number, dy: number) => void;
  onAddHole: (world: Vec2) => void;
  camera: Camera;
  onCameraChange: (camera: Camera) => void;
  spacingHint: { a: number; b: number };
  loadsById?: Record<string, HoleLoad>;
  network?: InitiationNetwork | null;
  isolines?: Isoline[];
  timesMs?: Record<string, number> | null;
  animationMs?: number | null;
  pendingTieFromId?: string | null;
  onTieHoles?: (fromId: string, toId: string) => void;
  onClearPendingTie?: () => void;
  domains?: BlastDomain[];
  drawingDomainId?: string | null;
  onDomainVertexAdd?: (domainId: string, point: Point3) => void;
  mapValues?: Record<string, number>;
  mapRange?: { min: number; max: number } | null;
  receptors?: Receptor[];
  selectedReceptorId?: string | null;
  placingReceptor?: boolean;
  onAddReceptor?: (world: Vec2) => void;
  onSelectReceptor?: (id: string) => void;
  vibrationPredictions?: VibrationPrediction[];
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [viewport, setViewport] = useState<Viewport>({ width: 800, height: 520 });
  const [drag, setDrag] = useState<DragState>({ kind: "none" });
  const [spacePressed, setSpacePressed] = useState(false);

  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const box = entries[0]?.contentRect;
      if (box) setViewport({ width: box.width, height: box.height });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.code === "Space") setSpacePressed(true);
    }
    function onKeyUp(e: KeyboardEvent) {
      if (e.code === "Space") setSpacePressed(false);
    }
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, []);

  function toScreenPoint(e: { clientX: number; clientY: number }): Vec2 {
    const rect = svgRef.current!.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  function worldOf(screen: Vec2): Vec2 {
    return screenToWorld(camera, viewport, screen);
  }

  function holeScreenPos(hole: Hole): Vec2 {
    let point = { x: hole.collar.x, y: hole.collar.y };
    if (drag.kind === "holes" && drag.ids.includes(hole.id)) {
      point = { x: point.x + drag.deltaWorld.x, y: point.y + drag.deltaWorld.y };
    }
    return worldToScreen(camera, viewport, point);
  }

  function hitReceptor(screen: Vec2): Receptor | null {
    const items = receptors ?? [];
    for (let i = items.length - 1; i >= 0; i -= 1) {
      const receptor = items[i];
      const p = worldToScreen(camera, viewport, { x: receptor.location.x, y: receptor.location.y });
      if (distance(p, screen) <= RECEPTOR_HIT_RADIUS_PX) return receptor;
    }
    return null;
  }

  function hitHole(screen: Vec2): Hole | null {
    for (let i = holes.length - 1; i >= 0; i -= 1) {
      const h = holes[i];
      if (!h.enabled) continue;
      const p = worldToScreen(camera, viewport, { x: h.collar.x, y: h.collar.y });
      if (distance(p, screen) <= HOLE_HIT_RADIUS_PX) return h;
    }
    return null;
  }

  function hitVertex(screen: Vec2): number | null {
    for (let i = 0; i < contour.vertices.length; i += 1) {
      const p = worldToScreen(camera, viewport, contour.vertices[i]);
      if (distance(p, screen) <= VERTEX_HIT_RADIUS_PX) return i;
    }
    return null;
  }

  function hitEdge(screen: Vec2): number | null {
    const n = contour.vertices.length;
    if (n < 2) return null;
    for (let i = 0; i < n; i += 1) {
      const a = worldToScreen(camera, viewport, contour.vertices[i]);
      const b = worldToScreen(camera, viewport, contour.vertices[(i + 1) % n]);
      if (pointToSegmentDistance(screen, a, b) <= EDGE_HIT_RADIUS_PX) return i;
    }
    return null;
  }

  function handleWheel(e: React.WheelEvent) {
    e.preventDefault();
    const screen = toScreenPoint(e);
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    onCameraChange(zoomAt(camera, viewport, screen, factor));
  }

  function handlePointerDown(e: React.PointerEvent) {
    const screen = toScreenPoint(e);
    (e.target as Element).setPointerCapture(e.pointerId);

    if (spacePressed || e.button === 1) {
      setDrag({ kind: "pan", startScreen: screen, startCamera: camera });
      return;
    }

    if (placingReceptor && onAddReceptor) {
      const world = worldOf(screen);
      const existing = hitReceptor(screen);
      if (existing && onSelectReceptor) {
        onSelectReceptor(existing.id);
        return;
      }
      onAddReceptor({ x: round2(world.x), y: round2(world.y) });
      return;
    }

    const receptorHit = hitReceptor(screen);
    if (receptorHit && onSelectReceptor && !drawingDomainId) {
      onSelectReceptor(receptorHit.id);
      return;
    }

    if (drawingDomainId && onDomainVertexAdd) {
      const world = worldOf(screen);
      onDomainVertexAdd(drawingDomainId, { x: round2(world.x), y: round2(world.y), z: contour.bench.crest_z_m });
      return;
    }

    if (mode === "contour") {
      const vertexIndex = hitVertex(screen);
      if (vertexIndex !== null) {
        setDrag({ kind: "vertex", index: vertexIndex });
        return;
      }
      const edgeIndex = hitEdge(screen);
      if (edgeIndex !== null) {
        onToggleFreeFace(edgeIndex);
        return;
      }
      const world = worldOf(screen);
      onContourVerticesChange([...contour.vertices, { x: round2(world.x), y: round2(world.y), z: contour.bench.crest_z_m }]);
      return;
    }

    const hole = hitHole(screen);
    if (mode === "tie" && hole && onTieHoles) {
      if (pendingTieFromId && pendingTieFromId !== hole.id) {
        onTieHoles(pendingTieFromId, hole.id);
      } else {
        onSelectedChange(new Set([hole.id]));
      }
      return;
    }

    if (hole) {
      const ids = selected.has(hole.id) && selected.size > 0 ? Array.from(selected) : [hole.id];
      if (!selected.has(hole.id)) onSelectedChange(new Set(ids));
      if (mode === "holes") {
        setDrag({ kind: "holes", ids, startWorld: worldOf(screen), deltaWorld: { x: 0, y: 0 } });
      }
      return;
    }

    if (mode === "tie") {
      onClearPendingTie?.();
      if (!e.shiftKey) onSelectedChange(new Set());
      return;
    }

    if (!e.shiftKey) onSelectedChange(new Set());
    setDrag({ kind: "rubber", startScreen: screen, currentScreen: screen });
  }

  function handlePointerMove(e: React.PointerEvent) {
    const screen = toScreenPoint(e);
    if (drag.kind === "pan") {
      const world0 = screenToWorld(drag.startCamera, viewport, drag.startScreen);
      const world1 = screenToWorld(drag.startCamera, viewport, screen);
      onCameraChange({ ...drag.startCamera, x: drag.startCamera.x - (world1.x - world0.x), y: drag.startCamera.y - (world1.y - world0.y) });
      return;
    }
    if (drag.kind === "vertex") {
      const world = worldOf(screen);
      const next = contour.vertices.map((v, i) => (i === drag.index ? { ...v, x: round2(world.x), y: round2(world.y) } : v));
      onContourVerticesChange(next);
      return;
    }
    if (drag.kind === "holes") {
      const world = worldOf(screen);
      setDrag({ ...drag, deltaWorld: { x: world.x - drag.startWorld.x, y: world.y - drag.startWorld.y } });
      return;
    }
    if (drag.kind === "rubber") {
      setDrag({ ...drag, currentScreen: screen });
    }
  }

  function handlePointerUp() {
    if (drag.kind === "holes") {
      const { dx, dy } = { dx: round2(drag.deltaWorld.x), dy: round2(drag.deltaWorld.y) };
      if (dx !== 0 || dy !== 0) onMoveHoles(drag.ids, dx, dy);
    }
    if (drag.kind === "rubber") {
      const rect = rectFromCorners(drag.startScreen, drag.currentScreen);
      const ids = holes.filter((h) => rectContains(rect, worldToScreen(camera, viewport, { x: h.collar.x, y: h.collar.y }))).map((h) => h.id);
      if (ids.length) onSelectedChange(new Set(ids));
    }
    setDrag({ kind: "none" });
  }

  function handleDoubleClick(e: React.MouseEvent) {
    if (mode !== "holes" || drawingDomainId) return;
    const screen = toScreenPoint(e);
    if (hitHole(screen)) return;
    onAddHole(worldOf(screen));
  }

  const draggedSingleHole =
    drag.kind === "holes" && drag.ids.length === 1 ? holes.find((h) => h.id === drag.ids[0]) : null;
  const dimensionLines = draggedSingleHole
    ? buildDimensionLines(draggedSingleHole, drag.kind === "holes" ? drag.deltaWorld : { x: 0, y: 0 }, holes, spacingHint)
    : [];

  const origin = worldToScreen(camera, viewport, { x: 0, y: 0 });
  const freeFaceSet = new Set(contour.free_faces.map((f) => f.join("-")));
  const maxChargeKg = loadsById
    ? Math.max(0, ...Object.values(loadsById).map((ld) => ld.total_charge_kg))
    : 0;
  const holesById = useMemo(() => {
    const map = new Map<string, Hole>();
    for (const h of holes) map.set(h.id, h);
    return map;
  }, [holes]);
  const animating = timesMs != null && animationMs != null;

  return (
    <div className="plan-canvas-wrap">
      <svg
        ref={svgRef}
        className="plan-canvas"
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onDoubleClick={handleDoubleClick}
      >
        <defs>
          <marker id="arrow-connector" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="#7a6ee0" />
          </marker>
        </defs>

        <line x1={0} y1={origin.y} x2={viewport.width} y2={origin.y} className="axis-line" />
        <line x1={origin.x} y1={0} x2={origin.x} y2={viewport.height} className="axis-line" />

        {isolines?.map((iso, i) => {
          const passed = animating && iso.time_ms <= animationMs!;
          const nextIso = isolines[i + 1];
          const isFront = animating && iso.time_ms <= animationMs! && (nextIso == null || nextIso.time_ms > animationMs!);
          const cls = isFront ? "isoline-segment front" : passed ? "isoline-segment passed" : "isoline-segment";
          return (
            <g key={`iso-${i}`}>
              {iso.segments.map((seg, j) => {
                const a = worldToScreen(camera, viewport, { x: seg[0][0], y: seg[0][1] });
                const b = worldToScreen(camera, viewport, { x: seg[1][0], y: seg[1][1] });
                return <line key={j} x1={a.x} y1={a.y} x2={b.x} y2={b.y} className={cls} />;
              })}
              {iso.segments[0] && (
                <text
                  x={worldToScreen(camera, viewport, { x: iso.segments[0][0][0], y: iso.segments[0][0][1] }).x}
                  y={worldToScreen(camera, viewport, { x: iso.segments[0][0][0], y: iso.segments[0][0][1] }).y - 4}
                  className={`isoline-label${isFront ? " front" : ""}`}
                >
                  {ruNumber(iso.time_ms, 0)}
                </text>
              )}
            </g>
          );
        })}

        {domains?.map((domain) => {
          if (domain.polygon.length < 2) return null;
          const screenPts = domain.polygon.map((v) => worldToScreen(camera, viewport, v));
          const points = screenPts.map((p) => `${p.x},${p.y}`).join(" ");
          const closed = domain.polygon.length >= 3
            ? `${points} ${screenPts[0].x},${screenPts[0].y}`
            : points;
          return (
            <g key={`domain-${domain.id}`}>
              {domain.polygon.length >= 3 && (
                <polygon
                  className={`domain-shape${domain.id === drawingDomainId ? " active" : ""}`}
                  points={points}
                  style={{ fill: domain.color || "#8fa399" }}
                />
              )}
              <polyline
                className="domain-outline"
                points={closed}
                style={{ stroke: domain.color || "#8fa399" }}
              />
            </g>
          );
        })}

        {contour.vertices.length >= 2 && (
          <polygon
            className="contour-shape"
            points={contour.vertices.map((v) => { const p = worldToScreen(camera, viewport, v); return `${p.x},${p.y}`; }).join(" ")}
          />
        )}
        {contour.vertices.map((v, i) => {
          if (contour.vertices.length < 2) return null;
          const a = worldToScreen(camera, viewport, v);
          const b = worldToScreen(camera, viewport, contour.vertices[(i + 1) % contour.vertices.length]);
          const isFree = freeFaceSet.has([i, (i + 1) % contour.vertices.length].join("-"));
          return <line key={`edge-${i}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} className={isFree ? "contour-edge free" : "contour-edge"} />;
        })}
        {mode === "contour" && !drawingDomainId && contour.vertices.map((v, i) => {
          const p = worldToScreen(camera, viewport, v);
          return <circle key={`vertex-${i}`} cx={p.x} cy={p.y} r={5} className="contour-vertex" />;
        })}
        {drawingDomainId && domains?.find((d) => d.id === drawingDomainId)?.polygon.map((v, i) => {
          const p = worldToScreen(camera, viewport, v);
          return <rect key={`dvertex-${i}`} x={p.x - 4} y={p.y - 4} width={8} height={8} className="domain-vertex" />;
        })}

        {network?.detonating_cords?.map((cord) => {
          const pts = cord.hole_ids.map((id) => holesById.get(id)).filter((h): h is Hole => Boolean(h));
          if (pts.length < 2) return null;
          const screen = pts.map((h) => worldToScreen(camera, viewport, { x: h.collar.x, y: h.collar.y }));
          return (
            <polyline
              key={cord.id}
              className="detcord-line"
              fill="none"
              points={screen.map((p) => `${p.x},${p.y}`).join(" ")}
            />
          );
        })}
        {(network ? networkTies(network) : []).map((c, i) => {
          const from = holesById.get(c.from_hole);
          const to = holesById.get(c.to_hole);
          if (!from || !to) return null;
          const a = worldToScreen(camera, viewport, { x: from.collar.x, y: from.collar.y });
          const b = worldToScreen(camera, viewport, { x: to.collar.x, y: to.collar.y });
          const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
          return (
            <g key={c.id || `conn-${i}`}>
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} className="connector-line" markerEnd="url(#arrow-connector)" />
              {c.delay_ms > 0 && <text x={mid.x} y={mid.y - 2} className="connector-label">{ruNumber(c.delay_ms, 0)}</text>}
            </g>
          );
        })}

        {(receptors ?? []).map((receptor) => {
          const p = worldToScreen(camera, viewport, { x: receptor.location.x, y: receptor.location.y });
          const pred = vibrationPredictions?.find((item) => item.receptor_id === receptor.id);
          const selectedRec = receptor.id === selectedReceptorId;
          return (
            <g key={`rec-${receptor.id}`} className={`receptor-marker kind-${receptor.kind}${selectedRec ? " selected" : ""}${pred?.exceeds_limit ? " over" : ""}`}>
              <rect x={p.x - 6} y={p.y - 6} width={12} height={12} transform={`rotate(45 ${p.x} ${p.y})`} />
              <text x={p.x + 10} y={p.y - 6} className="receptor-label">
                {receptor.name || RECEPTOR_KIND_LABELS[receptor.kind] || receptor.kind}
                {pred ? ` ${ruNumber(pred.ppv_mm_s, 1)}` : ""}
              </text>
            </g>
          );
        })}

        {holes.map((h) => {
          const p = holeScreenPos(h);
          const isSelected = selected.has(h.id);
          const load = loadsById?.[h.id];
          const mapValue = mapValues?.[h.id];
          const mapColor = mapValue !== undefined && mapRange ? mapMetricColor(mapValue, mapRange.min, mapRange.max) : null;
          const chargeColor = load && maxChargeKg > 0 ? chargeMassColor(load.total_charge_kg, maxChargeKg) : null;
          const fillColor = mapColor ?? chargeColor;
          let animClass = "";
          if (animating) {
            const t = timesMs![h.id];
            animClass = t !== undefined && t <= animationMs! ? " fired" : " unfired";
          }
          const isStarter = Boolean(
            network?.starter_items?.some((item) => item.hole_id === h.id) || network?.starters?.includes(h.id),
          );
          const pending = pendingTieFromId === h.id;
          const t = timesMs?.[h.id];
          return (
            <g key={h.id} className={`hole-marker kind-${h.kind}${isSelected ? " selected" : ""}${!h.enabled ? " disabled" : ""}${isStarter ? " starter" : ""}${pending ? " pending-tie" : ""}${animClass}`}>
              <circle cx={p.x} cy={p.y} r={isSelected || pending ? 7 : 5.5} style={fillColor ? { fill: fillColor } : undefined} />
              {mode === "timing" && t !== undefined && (
                <text x={p.x + 8} y={p.y - 6} className="hole-time-label">{ruNumber(t, 0)}</text>
              )}
            </g>
          );
        })}

        {dimensionLines.map((line, i) => {
          const a = worldToScreen(camera, viewport, line.from);
          const b = worldToScreen(camera, viewport, line.to);
          const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
          return (
            <g key={i} className={line.warn ? "dimension warn" : "dimension"}>
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
              <text x={mid.x} y={mid.y - 4}>{ruNumber(line.distance, 2)} м</text>
            </g>
          );
        })}

        {drag.kind === "rubber" && (
          <rect
            className="rubber-band"
            x={Math.min(drag.startScreen.x, drag.currentScreen.x)}
            y={Math.min(drag.startScreen.y, drag.currentScreen.y)}
            width={Math.abs(drag.currentScreen.x - drag.startScreen.x)}
            height={Math.abs(drag.currentScreen.y - drag.startScreen.y)}
          />
        )}
      </svg>
      <div className="plan-canvas-hint">
        {placingReceptor
          ? "Клик — новый рецептор на плане · пробел + перетаскивание — панорама"
          : drawingDomainId
          ? "Клик — вершина геологического региона · пробел + перетаскивание — панорама"
          : mode === "contour"
            ? "Клик по пустому месту — новая точка контура · клик по ребру — открытый откос · пробел + перетаскивание — панорама"
            : mode === "tie"
              ? pendingTieFromId
                ? `Связь от ${pendingTieFromId}: кликните вторую скважину · пустое место — сброс`
                : "Клик по скважине — начало связи · две скважины создают коннектор · пробел + перетаскивание — панорама"
              : mode === "timing"
                ? "Анимация последовательности взрыва и изолинии времени · пробел + перетаскивание — панорама"
                : "Двойной клик — новая скважина · перетаскивание — перемещение · рамка — выделение · пробел + перетаскивание — панорама"}
      </div>
    </div>
  );
}

function mapMetricColor(value: number, min: number, max: number): string {
  const span = max - min;
  const ratio = span <= 1e-9 ? 0.5 : Math.max(0, Math.min(1, (value - min) / span));
  const hue = 210 - 210 * ratio; // blue (low) → red (high)
  return `hsl(${hue}, 70%, 46%)`;
}

function chargeMassColor(massKg: number, maxMassKg: number): string {
  const ratio = Math.max(0, Math.min(1, massKg / maxMassKg));
  const hue = 48 - 48 * ratio; // жёлтый (лёгкий заряд) → красный (тяжёлый)
  return `hsl(${hue}, 72%, 46%)`;
}

function round2(v: number): number {
  return Math.round(v * 100) / 100;
}

function pointToSegmentDistance(p: Vec2, a: Vec2, b: Vec2): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const lengthSq = dx * dx + dy * dy;
  if (lengthSq < 1e-9) return distance(p, a);
  const t = Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / lengthSq));
  return distance(p, { x: a.x + t * dx, y: a.y + t * dy });
}

function buildDimensionLines(
  dragged: Hole,
  delta: Vec2,
  holes: Hole[],
  spacingHint: { a: number; b: number },
): { from: Vec2; to: Vec2; distance: number; warn: boolean }[] {
  const current = { x: dragged.collar.x + delta.x, y: dragged.collar.y + delta.y };
  const others = holes.filter((h) => h.id !== dragged.id && h.enabled);
  const withDistance = others
    .map((h) => ({ hole: h, d: distance(current, { x: h.collar.x, y: h.collar.y }) }))
    .sort((a, b) => a.d - b.d)
    .slice(0, NEIGHBOUR_COUNT);
  const expected = Math.min(spacingHint.a || Infinity, spacingHint.b || Infinity);
  return withDistance.map(({ hole, d }) => ({
    from: current,
    to: { x: hole.collar.x, y: hole.collar.y },
    distance: d,
    warn: Number.isFinite(expected) && Math.abs(d - expected) > SPACING_TOLERANCE_M && d < expected * 1.8,
  }));
}
