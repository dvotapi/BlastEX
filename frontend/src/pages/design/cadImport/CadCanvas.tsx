// Холст импорта чертежа: линии в цвете роли, точки отметок, панорама и
// масштаб колесом. Наведение и щелчок сообщают слой и объект — таблица
// слоёв подсвечивает ту же строку. Подписи не рисуются: их сотни, а отметку
// точки таблица показывает текстом.
import { useEffect, useMemo, useRef, useState, type PointerEvent, type WheelEvent } from "react";
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
  const pointGroups = useMemo(() => {
    const groups = new Map<string, CadEntity[]>();
    for (const entity of entities) {
      if (entity.geometry_type !== "point") continue;
      const key = `${entity.layer}\u0000${entity.role}`;
      groups.set(key, [...(groups.get(key) ?? []), entity]);
    }
    return [...groups.values()];
  }, [entities]);

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

  function select(target: CanvasTarget) {
    // Отпускание после панорамы — не щелчок по линии.
    if (dragMoved.current) return;
    onSelect(target);
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
        {lines.map((entity) => {
          const d = linePath(entity.points, entity.closed, cam, viewport);
          const state = `${matches(hover, entity) ? " is-hovered" : ""}${matches(selected, entity) && selected?.handle ? " is-selected" : ""}${emphasized.includes(entity.handle) ? " is-emphasized" : ""}`;
          return (
            <g key={entity.handle}>
              <path
                className={`cad-line role-${entity.role}${state}`}
                data-handle={entity.handle}
                d={d}
                style={{ stroke: roleColor(entity.role) }}
              />
              <path
                className="cad-hit"
                data-handle={entity.handle}
                d={d}
                strokeWidth={HIT_WIDTH_PX}
                onMouseEnter={() => onHover({ layer: entity.layer, handle: entity.handle })}
                onMouseLeave={() => onHover(null)}
                onClick={() => select({ layer: entity.layer, handle: entity.handle })}
              />
            </g>
          );
        })}
        {pointGroups.map((group) => {
          const first = group[0];
          const target = { layer: first.layer, handle: null };
          const hovered = hover?.layer === first.layer;
          return (
            <g key={`${first.layer}:${first.role}`}>
              <path
                className={`cad-points${hovered ? " is-hovered" : ""}`}
                d={pointsPath(group.map((entity) => entity.points[0]), cam, viewport, POINT_RADIUS_PX)}
                style={{ fill: roleColor(first.role) }}
              />
              <path
                className="cad-hit cad-hit-points"
                d={pointsPath(group.map((entity) => entity.points[0]), cam, viewport, POINT_RADIUS_PX + 3)}
                onMouseEnter={() => onHover(target)}
                onMouseLeave={() => onHover(null)}
                onClick={() => select(target)}
              />
            </g>
          );
        })}
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
