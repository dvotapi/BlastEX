// Холст импорта чертежа: линии в цвете роли, точки отметок, панорама и
// масштаб колесом. Наведение и щелчок сообщают слой и объект — таблица
// слоёв подсвечивает ту же строку. Подписи не рисуются: их сотни, а отметку
// точки таблица показывает текстом.
//
// Чертёж карьера — десятки тысяч линий (TASK-013, PR 4: 30 000 линий в SVG
// давали ~0,9 с на кадр колеса), поэтому базовый слой — один `<canvas>`,
// перерисовка только при смене камеры или данных. Линию под курсором ищет
// сетка (`CanvasHitIndex`), подсветка — SVG поверх холста из одних
// подсвеченных линий.
//
// На шаге «Контур» холст работает инструментом (`tool`): щелчок отдаёт точку
// чертежа, линию под курсором и привязку (конец, пересечение, вершина,
// ближайшая точка), а слой-наложение рисует контуры и участки сборки.
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
  type PointerEvent,
  type ReactNode,
  type WheelEvent,
} from "react";
import {
  fitCamera,
  niceStep,
  screenToWorld,
  worldToScreen,
  zoomAt,
  type Camera,
  type Vec2,
  type Viewport,
} from "../../../lib/geometry2d";
import type { CadEntity } from "../../../types/cad";
import { drawingBounds, linePath, pointsPath } from "./cadGeometry";
import { inDrawOrder, roleColor } from "./cadRoles";
import { CanvasHitIndex } from "./canvasHit";
import type { Snap, SnapIndex } from "./contourGeometry";
import type { Pick } from "./contourState";

export type CanvasTarget = { layer: string; handle: string | null };

/** Порог перетаскивания: меньше — это щелчок, а не панорама. */
const DRAG_THRESHOLD_PX = 4;
const POINT_RADIUS_PX = 2.2;
const HIT_WIDTH_PX = 10;
/** Апертура привязки курсора на экране (как объектная привязка САПР). */
export const SNAP_APERTURE_PX = 10;

function matches(target: CanvasTarget | null, entity: CadEntity): boolean {
  if (!target || target.layer !== entity.layer) return false;
  return target.handle === null || target.handle === entity.handle;
}

// Толщина линии на холсте по роли (как было у SVG): контур — жирнее.
const LINE_WIDTH_PX: Record<string, number> = { block_contour: 2.2 };
const DEFAULT_LINE_WIDTH_PX = 1.4;

/** Камера, вписывающая весь чертёж в окно. */
export function fittedCamera(entities: CadEntity[], viewport: Viewport): Camera {
  const bounds = drawingBounds(entities);
  return bounds ? fitCamera(bounds, viewport, 0.06, 1, 1e-4, 400) : { x: 0, y: 0, scale: 1 };
}

/** Базовый слой: линии в цвете роли и точки отметок одним холстом. */
function BaseLayer({ lines, points, camera, viewport }: { lines: CadEntity[]; points: CadEntity[]; camera: Camera; viewport: Viewport }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const ratio = typeof window !== "undefined" ? Math.min(2, window.devicePixelRatio || 1) : 1;
  useEffect(() => {
    const canvas = ref.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    // Размер буфера — только при смене: присваивание пересоздаёт буфер холста.
    const width = Math.round(viewport.width * ratio);
    const height = Math.round(viewport.height * ratio);
    if (canvas.width !== width) canvas.width = width;
    if (canvas.height !== height) canvas.height = height;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, viewport.width, viewport.height);
    const cx = viewport.width / 2;
    const cy = viewport.height / 2;
    const sx = (x: number) => cx + (x - camera.x) * camera.scale;
    const sy = (y: number) => cy - (y - camera.y) * camera.scale;
    context.lineJoin = "round";
    // Линии одной роли — одним путём: тысячи `stroke` на кадр не нужны.
    let role = "";
    const flush = () => {
      if (role) context.stroke();
    };
    for (const entity of lines) {
      if (entity.role !== role) {
        flush();
        role = entity.role;
        context.beginPath();
        context.strokeStyle = roleColor(role);
        context.lineWidth = LINE_WIDTH_PX[role] ?? DEFAULT_LINE_WIDTH_PX;
        context.setLineDash(role === "ignore" ? [4, 3] : []);
      }
      const [first, ...rest] = entity.points;
      context.moveTo(sx(first[0]), sy(first[1]));
      for (const point of rest) context.lineTo(sx(point[0]), sy(point[1]));
      if (entity.closed && entity.points.length > 2) context.lineTo(sx(first[0]), sy(first[1]));
    }
    flush();
    context.setLineDash([]);
    for (const entity of points) {
      context.fillStyle = roleColor(entity.role);
      context.beginPath();
      context.arc(sx(entity.points[0][0]), sy(entity.points[0][1]), POINT_RADIUS_PX, 0, Math.PI * 2);
      context.fill();
    }
  }, [lines, points, camera.x, camera.y, camera.scale, viewport.width, viewport.height, ratio]);
  return (
    <canvas ref={ref} className="cad-base" aria-hidden="true" style={{ width: viewport.width, height: viewport.height }} />
  );
}

export type ScreenProjector = (point: number[]) => Vec2;

function SnapMarker({ snap, toScreen }: { snap: Snap; toScreen: ScreenProjector }) {
  const { x, y } = toScreen(snap.point);
  const r = 5;
  const shape =
    snap.kind === "intersection" ? (
      <path d={`M${x - r} ${y - r}L${x + r} ${y + r}M${x - r} ${y + r}L${x + r} ${y - r}`} />
    ) : snap.kind === "nearest" ? (
      <circle cx={x} cy={y} r={r - 1} />
    ) : snap.kind === "vertex" ? (
      <path d={`M${x} ${y - r}L${x + r} ${y}L${x} ${y + r}L${x - r} ${y}Z`} />
    ) : (
      <rect x={x - r} y={y - r} width={2 * r} height={2 * r} />
    );
  return <g className={`cad-snap kind-${snap.kind}`}>{shape}</g>;
}

export function CadCanvas({
  entities,
  fitKey,
  hover,
  selected,
  emphasized,
  onHover,
  onSelect,
  tool = false,
  snapIndex = null,
  snapMinM = 0,
  onPick,
  overlay,
}: {
  entities: CadEntity[];
  /** Смена ключа (другой файл, другой масштаб) заново вписывает чертёж. */
  fitKey: string;
  hover: CanvasTarget | null;
  selected: CanvasTarget | null;
  emphasized: string[];
  onHover: (target: CanvasTarget | null) => void;
  onSelect: (target: CanvasTarget) => void;
  /** Инструмент шага «Контур»: щелчок — точка чертежа, а не выбор строки. */
  tool?: boolean;
  snapIndex?: SnapIndex | null;
  /** Апертура привязки в метрах не меньше этого (допуск стыковки). */
  snapMinM?: number;
  onPick?: (pick: Pick) => void;
  overlay?: (toScreen: ScreenProjector) => ReactNode;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [viewport, setViewport] = useState<Viewport>({ width: 800, height: 600 });
  const [camera, setCamera] = useState<Camera | null>(null);
  const [panFrom, setPanFrom] = useState<{ screen: Vec2; camera: Camera } | null>(null);
  const dragMoved = useRef(false);
  const [snapMarker, setSnapMarker] = useState<Snap | null>(null);
  // Последнее сообщённое наведение: одно и то же не сообщается на каждый сдвиг мыши.
  const hovered = useRef<string>("");

  useEffect(() => {
    const element = wrapRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((items) => {
      const box = items[0]?.contentRect;
      if (box && box.width > 0 && box.height > 0) setViewport({ width: box.width, height: box.height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // Новый файл или масштаб — вписываем чертёж заново при следующей отрисовке.
  useEffect(() => setCamera(null), [fitKey]);

  const fitted = useMemo(() => fittedCamera(entities, viewport), [entities, viewport]);
  const cam = camera ?? fitted;

  const lines = useMemo(
    () => inDrawOrder(entities.filter((entity) => entity.geometry_type === "line" && entity.points.length >= 2)),
    [entities],
  );
  const points = useMemo(
    () => entities.filter((entity) => entity.geometry_type === "point" && entity.points.length > 0),
    [entities],
  );
  const hitIndex = useMemo(() => new CanvasHitIndex(entities), [entities]);
  // Выделенная цепочка — это тысячи отрезков: поиск по множеству, а не по массиву.
  const emphasizedSet = useMemo(() => new Set(emphasized), [emphasized]);
  // Подсветка — SVG поверх холста: пути только подсвеченных линий.
  const highlighted = lines
    .filter((entity) => matches(hover, entity) || selected?.handle === entity.handle || emphasizedSet.has(entity.handle))
    .map((entity) => ({ entity, d: linePath(entity.points, entity.closed, cam, viewport) }));
  const hoveredPoints = hover
    ? pointsPath(
        points.filter((entity) => entity.layer === hover.layer).map((entity) => entity.points[0]),
        cam,
        viewport,
        POINT_RADIUS_PX,
      )
    : "";

  /** Линия или слой точки под курсором: зона попадания — `HIT_WIDTH_PX` на экране. */
  function targetAt(screen: Vec2): CanvasTarget | null {
    const world = screenToWorld(cam, viewport, screen);
    // Как у SVG-зон: линия — 10 px, точка — свой кружок + 3 px; равными считаем линии в пределах 1 px.
    return hitIndex.hit([world.x, world.y], HIT_WIDTH_PX / 2 / cam.scale, (POINT_RADIUS_PX + 3) / cam.scale, 1 / cam.scale);
  }

  function reportHover(target: CanvasTarget | null) {
    const key = target ? `${target.layer}\u0000${target.handle ?? ""}` : "";
    if (key === hovered.current) return;
    hovered.current = key;
    onHover(target);
  }

  const toScreen: ScreenProjector = (point) => worldToScreen(cam, viewport, { x: point[0], y: point[1] });

  function snapAt(screen: Vec2): { world: Vec2; snap: Snap | null } {
    const world = screenToWorld(cam, viewport, screen);
    const aperture = Math.max(SNAP_APERTURE_PX / cam.scale, snapMinM);
    return { world, snap: snapIndex ? snapIndex.snap([world.x, world.y], aperture) : null };
  }

  function onCanvasClick(event: MouseEvent<SVGSVGElement>) {
    // Отпускание после панорамы — не щелчок по линии.
    if (dragMoved.current) return;
    const screen = local(event);
    const target = targetAt(screen);
    if (!tool) {
      if (target) onSelect(target);
      return;
    }
    if (!onPick) return;
    const { world, snap } = snapAt(screen);
    onPick({ world: [world.x, world.y], snap, handle: target?.handle ?? null });
  }

  function local(event: { clientX: number; clientY: number }): Vec2 {
    const rect = wrapRef.current?.getBoundingClientRect();
    return { x: event.clientX - (rect?.left ?? 0), y: event.clientY - (rect?.top ?? 0) };
  }

  function onWheel(event: WheelEvent<SVGSVGElement>) {
    setCamera(zoomAt(cam, viewport, local(event), event.deltaY < 0 ? 1.15 : 1 / 1.15, 1e-4, 400));
  }

  function onPointerDown(event: PointerEvent<SVGSVGElement>) {
    if (event.button !== 0) return;
    (event.target as Element).setPointerCapture?.(event.pointerId);
    dragMoved.current = false;
    setPanFrom({ screen: local(event), camera: cam });
  }

  function onMouseMove(event: MouseEvent<SVGSVGElement>) {
    if (panFrom && dragMoved.current) return;
    reportHover(targetAt(local(event)));
  }

  function onPointerMove(event: PointerEvent<SVGSVGElement>) {
    if (tool && (!panFrom || !dragMoved.current)) setSnapMarker(snapAt(local(event)).snap);
    if (!panFrom) return;
    const point = local(event);
    const dx = point.x - panFrom.screen.x;
    const dy = point.y - panFrom.screen.y;
    if (Math.hypot(dx, dy) > DRAG_THRESHOLD_PX) dragMoved.current = true;
    if (!dragMoved.current) return;
    setCamera({
      x: panFrom.camera.x - dx / panFrom.camera.scale,
      y: panFrom.camera.y + dy / panFrom.camera.scale,
      scale: panFrom.camera.scale,
    });
  }

  const scaleMeters = niceStep(90 / cam.scale);
  const scalePx = scaleMeters * cam.scale;

  return (
    <div className="cad-canvas-wrap" ref={wrapRef}>
      <BaseLayer lines={lines} points={points} camera={cam} viewport={viewport} />
      <svg
        className={`cad-canvas${tool ? " is-picking" : ""}${hover ? " is-over" : ""}`}
        role="img"
        aria-label="Чертёж: линии в цвете роли"
        width={viewport.width}
        height={viewport.height}
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={() => setPanFrom(null)}
        onPointerCancel={() => setPanFrom(null)}
        onPointerLeave={() => setSnapMarker(null)}
        onMouseMove={onMouseMove}
        onMouseLeave={() => reportHover(null)}
        onClick={onCanvasClick}
      >
        {hoveredPoints && <path className="cad-points is-hovered" d={hoveredPoints} />}
        <g className="cad-highlights">
          {highlighted.map(({ entity, d }) => (
            <path
              key={entity.handle}
              className={`cad-highlight${matches(hover, entity) ? " is-hovered" : ""}${selected?.handle === entity.handle ? " is-selected" : ""}${emphasizedSet.has(entity.handle) ? " is-emphasized" : ""}`}
              data-handle={entity.handle}
              d={d}
              style={{ stroke: roleColor(entity.role) }}
            />
          ))}
        </g>
        {overlay && <g className="cad-overlay">{overlay(toScreen)}</g>}
        {tool && snapMarker && <SnapMarker snap={snapMarker} toScreen={toScreen} />}
        <g className="cad-scale" transform={`translate(14 ${viewport.height - 16})`}>
          <path d={`M0 -4V0H${scalePx.toFixed(1)}V-4`} />
          <text x={scalePx + 6} y={0}>
            {scaleMeters} м
          </text>
        </g>
      </svg>
      <button type="button" className="secondary-button cad-fit" onClick={() => setCamera(null)}>
        По размеру
      </button>
    </div>
  );
}
