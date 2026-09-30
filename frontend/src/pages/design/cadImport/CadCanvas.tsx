// Холст импорта чертежа: линии в цвете роли, точки отметок, панорама и
// масштаб колесом. Наведение и щелчок сообщают слой и объект — таблица
// слоёв подсвечивает ту же строку. Подписи не рисуются: их сотни, а отметку
// точки таблица показывает текстом.
//
// Чертёж карьера — десятки тысяч линий, поэтому пути считаются только при
// смене камеры, а базовый слой не перерисовывается на наведение: подсветка —
// отдельный слой поверх него из одних подсвеченных линий.
import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent,
  type WheelEvent,
} from "react";
import {
  fitCamera,
  niceStep,
  zoomAt,
  type Camera,
  type Vec2,
  type Viewport,
} from "../../../lib/geometry2d";
import type { CadEntity } from "../../../types/cad";
import { drawingBounds, linePath, pointsPath } from "./cadGeometry";
import { roleColor } from "./cadRoles";

export type CanvasTarget = { layer: string; handle: string | null };

/** Порог перетаскивания: меньше — это щелчок, а не панорама. */
const DRAG_THRESHOLD_PX = 4;
const POINT_RADIUS_PX = 2.2;
const HIT_WIDTH_PX = 10;
// Порядок слоёв рисования: ситуация под бровками, контур — сверху.
const ROLE_ORDER = [
  "ignore",
  "situation",
  "contour_line",
  "feature_line",
  "spot_heights",
  "design_line",
  "crest_bottom",
  "crest_top",
  "block_contour",
];

function matches(target: CanvasTarget | null, entity: CadEntity): boolean {
  if (!target || target.layer !== entity.layer) return false;
  return target.handle === null || target.handle === entity.handle;
}

type LinePath = { entity: CadEntity; d: string };
type PointGroup = { key: string; layer: string; role: string; d: string; hit: string };

/** Базовый слой: перерисовывается только при смене камеры или данных. */
const LineLayer = memo(function LineLayer({
  paths,
  onHover,
  onSelect,
}: {
  paths: LinePath[];
  onHover: (target: CanvasTarget | null) => void;
  onSelect: (target: CanvasTarget) => void;
}) {
  return (
    <g>
      {paths.map(({ entity, d }) => (
        <g key={entity.handle}>
          <path className={`cad-line role-${entity.role}`} data-handle={entity.handle} d={d} style={{ stroke: roleColor(entity.role) }} />
          <path
            className="cad-hit"
            data-handle={entity.handle}
            d={d}
            strokeWidth={HIT_WIDTH_PX}
            onMouseEnter={() => onHover({ layer: entity.layer, handle: entity.handle })}
            onMouseLeave={() => onHover(null)}
            onClick={() => onSelect({ layer: entity.layer, handle: entity.handle })}
          />
        </g>
      ))}
    </g>
  );
});

export function CadCanvas({
  entities,
  fitKey,
  hover,
  selected,
  emphasized,
  onHover,
  onSelect,
}: {
  entities: CadEntity[];
  /** Смена ключа (другой файл, другой масштаб) заново вписывает чертёж. */
  fitKey: string;
  hover: CanvasTarget | null;
  selected: CanvasTarget | null;
  emphasized: string[];
  onHover: (target: CanvasTarget | null) => void;
  onSelect: (target: CanvasTarget) => void;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [viewport, setViewport] = useState<Viewport>({ width: 800, height: 600 });
  const [camera, setCamera] = useState<Camera | null>(null);
  const [panFrom, setPanFrom] = useState<{ screen: Vec2; camera: Camera } | null>(null);
  const dragMoved = useRef(false);
  const bounds = useMemo(() => drawingBounds(entities), [entities]);

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

  const fitted = bounds ? fitCamera(bounds, viewport, 0.06, 1, 1e-4, 400) : { x: 0, y: 0, scale: 1 };
  const cam = camera ?? fitted;

  const lines = useMemo(
    () =>
      entities
        .filter((entity) => entity.geometry_type === "line")
        .sort((a, b) => ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role)),
    [entities],
  );
  const paths = useMemo<LinePath[]>(
    () => lines.map((entity) => ({ entity, d: linePath(entity.points, entity.closed, cam, viewport) })),
    // Камера и вьюпорт — по значениям: вписанная камера пересоздаётся на каждой отрисовке.
    [lines, cam.x, cam.y, cam.scale, viewport.width, viewport.height],
  );
  const pointGroups = useMemo<PointGroup[]>(() => {
    const groups = new Map<string, CadEntity[]>();
    for (const entity of entities) {
      if (entity.geometry_type !== "point") continue;
      const key = `${entity.layer}\u0000${entity.role}`;
      const group = groups.get(key);
      if (group) group.push(entity);
      else groups.set(key, [entity]);
    }
    return [...groups.entries()].map(([key, group]) => {
      const points = group.map((entity) => entity.points[0]);
      return {
        key,
        layer: group[0].layer,
        role: group[0].role,
        d: pointsPath(points, cam, viewport, POINT_RADIUS_PX),
        hit: pointsPath(points, cam, viewport, POINT_RADIUS_PX + 3),
      };
    });
  }, [entities, cam.x, cam.y, cam.scale, viewport.width, viewport.height]);
  // Выделенная цепочка — это тысячи отрезков: поиск по множеству, а не по массиву.
  const emphasizedSet = useMemo(() => new Set(emphasized), [emphasized]);
  const highlighted = paths.filter(
    ({ entity }) =>
      matches(hover, entity) || (selected?.handle === entity.handle) || emphasizedSet.has(entity.handle),
  );

  // Обработчики базового слоя стабильны — иначе memo не спасёт от перерисовки.
  const latest = useRef({ onHover, onSelect });
  latest.current = { onHover, onSelect };
  const hoverStable = useCallback((target: CanvasTarget | null) => latest.current.onHover(target), []);
  const selectStable = useCallback((target: CanvasTarget) => {
    // Отпускание после панорамы — не щелчок по линии.
    if (dragMoved.current) return;
    latest.current.onSelect(target);
  }, []);

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

  function onPointerMove(event: PointerEvent<SVGSVGElement>) {
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
      <svg
        className="cad-canvas"
        role="img"
        aria-label="Чертёж: линии в цвете роли"
        width={viewport.width}
        height={viewport.height}
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={() => setPanFrom(null)}
        onPointerCancel={() => setPanFrom(null)}
      >
        <LineLayer paths={paths} onHover={hoverStable} onSelect={selectStable} />
        {pointGroups.map((group) => {
          const target = { layer: group.layer, handle: null };
          return (
            <g key={group.key}>
              <path
                className={`cad-points${hover?.layer === group.layer ? " is-hovered" : ""}`}
                d={group.d}
                style={{ fill: roleColor(group.role) }}
              />
              <path
                className="cad-hit cad-hit-points"
                d={group.hit}
                onMouseEnter={() => hoverStable(target)}
                onMouseLeave={() => hoverStable(null)}
                onClick={() => selectStable(target)}
              />
            </g>
          );
        })}
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
