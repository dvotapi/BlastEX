// План Г.5 в окне проекта МВ (TASK-018, PR 6, В5): блоки, кольца опасных зон,
// ситуация карьера и точки постов, взрывной станции, укрытия и сбора.
// Данные — проектная `graphics` контекста v2 (сервер); точки — из формы.
// Выбрать вид точки → щелчок по плану ставит её; точку можно перетащить.
// Север вверх: y плана растёт к северу, у SVG — вниз.
import { useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import type { LayoutPointKind, ProjectGraphics } from "../../../types/massBlast";
import { parseNumber, type PointForm } from "./form";

type Box = { x: number; y: number; w: number; h: number };
type Pt = [number, number];

const ZONE_STYLE: Record<string, { stroke: string; label: string }> = {
  people: { stroke: "#b71c1c", label: "люди" },
  mechanisms: { stroke: "#e07b00", label: "механизмы" },
  buildings: { stroke: "#5b6bb5", label: "здания" },
};
const POINT_STYLE: Record<LayoutPointKind, { fill: string; short: string }> = {
  guard_post: { fill: "#b71c1c", short: "П" },
  blast_station: { fill: "#1f5fa8", short: "ВС" },
  shelter: { fill: "#2e7d32", short: "У" },
  gather: { fill: "#6d4c41", short: "С" },
};

function bounds(graphics: ProjectGraphics, points: Pt[]): Box | null {
  const xs: number[] = [];
  const ys: number[] = [];
  const add = ([x, y]: Pt) => {
    if (Number.isFinite(x) && Number.isFinite(y)) {
      xs.push(x);
      ys.push(y);
    }
  };
  graphics.outlines.forEach((ring) => ring.forEach(add));
  graphics.zones.forEach((zone) => zone.rings.forEach((ring) => ring.forEach(add)));
  if (!xs.length) points.forEach(add);
  if (!xs.length) return null;
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const pad = Math.max(maxX - minX, maxY - minY, 50) * 0.08;
  return { x: minX - pad, y: -(maxY + pad), w: maxX - minX + 2 * pad, h: maxY - minY + 2 * pad };
}

const path = (ring: Pt[], closed: boolean) =>
  ring.length ? `M${ring.map(([x, y]) => `${x},${-y}`).join("L")}${closed ? "Z" : ""}` : "";

export function LayoutPlan({
  graphics,
  points,
  kind,
  postRef,
  editable,
  onPlace,
  onMove,
}: {
  graphics: ProjectGraphics;
  points: PointForm[];
  kind: LayoutPointKind;
  postRef: string;
  editable: boolean;
  onPlace: (kind: LayoutPointKind, ref: string, x: number, y: number) => void;
  onMove: (index: number, x: number, y: number) => void;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const coords = useMemo(
    () => points.map((point) => [parseNumber(point.x), parseNumber(point.y)] as const),
    [points],
  );
  const initial = useMemo(
    () => bounds(graphics, coords.filter((c): c is readonly [number, number] => typeof c[0] === "number" && typeof c[1] === "number") as Pt[]),
    // Вид плана — по геометрии блока и зон; точки двигают только изначально пустой план.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [graphics],
  );
  const [view, setView] = useState<Box | null>(initial);
  // Новая геометрия (зоны пересчитаны после проверки) — план вписывается заново.
  useEffect(() => setView(initial), [initial]);
  const boxRef = useRef<Box | null>(null);
  boxRef.current = view ?? initial;
  // Масштаб колесом — своим слушателем с `passive: false`: у React `onWheel`
  // пассивный, и вместе с планом прокручивалось бы окно.
  const hasPlan = Boolean(initial);
  useEffect(() => {
    const element = svg.current;
    if (!element) return;
    const handler = (event: globalThis.WheelEvent) => {
      const current = boxRef.current;
      const matrix = element.getScreenCTM?.();
      if (!current || !matrix) return;
      event.preventDefault();
      const point = element.createSVGPoint();
      point.x = event.clientX;
      point.y = event.clientY;
      const at = point.matrixTransform(matrix.inverse());
      const factor = event.deltaY > 0 ? 1.2 : 1 / 1.2;
      setView({ x: at.x - (at.x - current.x) * factor, y: at.y - (at.y - current.y) * factor, w: current.w * factor, h: current.h * factor });
    };
    element.addEventListener("wheel", handler, { passive: false });
    return () => element.removeEventListener("wheel", handler);
  }, [hasPlan]);
  const drag = useRef<{ mode: "pan" | "point"; index?: number; client: Pt; box: Box; moved: boolean } | null>(null);
  const box = view ?? initial;
  if (!box) return <small className="drill-hint">Нет геометрии блока для плана: проверьте проект.</small>;
  const unit = box.w / 140;

  function world(event: { clientX: number; clientY: number }): Pt | null {
    const element = svg.current;
    const matrix = element?.getScreenCTM?.();
    if (!element || !matrix) return null;
    const point = element.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const local = point.matrixTransform(matrix.inverse());
    return [local.x, -local.y];
  }

  /** Сколько единиц плана в пикселе экрана (вид вписан с сохранением пропорций). */
  function scale(current: Box): number {
    const rect = svg.current?.getBoundingClientRect();
    if (!rect || !rect.width || !rect.height) return 1;
    return Math.max(current.w / rect.width, current.h / rect.height);
  }

  function onPointerDown(event: PointerEvent<SVGSVGElement>, index?: number) {
    event.stopPropagation();
    (event.currentTarget as Element).setPointerCapture?.(event.pointerId);
    drag.current = { mode: index === undefined ? "pan" : "point", index, client: [event.clientX, event.clientY], box: box!, moved: false };
  }

  function onPointerMove(event: PointerEvent<SVGSVGElement>) {
    const state = drag.current;
    if (!state) return;
    const dx = event.clientX - state.client[0];
    const dy = event.clientY - state.client[1];
    if (Math.hypot(dx, dy) > 3) state.moved = true;
    if (!state.moved) return;
    if (state.mode === "point" && editable && state.index !== undefined) {
      const at = world(event);
      if (at) onMove(state.index, Math.round(at[0] * 10) / 10, Math.round(at[1] * 10) / 10);
    } else if (state.mode === "pan") {
      const k = scale(state.box);
      setView({ ...state.box, x: state.box.x - dx * k, y: state.box.y - dy * k });
    }
  }

  function onPointerUp(event: PointerEvent<SVGSVGElement>) {
    const state = drag.current;
    drag.current = null;
    if (!state || state.moved || state.mode !== "pan" || !editable) return;
    const at = world(event);
    if (at) onPlace(kind, kind === "guard_post" ? postRef : "", Math.round(at[0] * 10) / 10, Math.round(at[1] * 10) / 10);
  }

  return (
    <div className="mb-plan">
      <svg
        ref={svg}
        role="img"
        aria-label="Ситуационный план: щелчок ставит выбранную точку"
        viewBox={`${box.x} ${box.y} ${box.w} ${box.h}`}
        preserveAspectRatio="xMidYMid meet"
        onPointerDown={(event) => onPointerDown(event)}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      >
        {graphics.situation.map((layer) =>
          layer.lines.map((line, index) => (
            <path key={`${layer.name}:${index}`} d={path(line as Pt[], false)} fill="none" stroke="#9aa59f" strokeWidth={unit * 0.25} />
          )),
        )}
        {graphics.zones.map((zone) =>
          zone.rings.map((ring, index) => (
            <path key={`${zone.kind}:${index}`} d={path(ring as Pt[], true)} fill="none"
              stroke={ZONE_STYLE[zone.kind]?.stroke ?? "#777"} strokeWidth={unit * 0.35} strokeDasharray={`${unit * 2} ${unit}`}>
              <title>{`Зона ${ZONE_STYLE[zone.kind]?.label ?? zone.kind}: ${Math.round(zone.value_m)} м`}</title>
            </path>
          )),
        )}
        {graphics.outlines.map((ring, index) => (
          <path key={`outline:${index}`} d={path(ring as Pt[], true)} fill="#2e3237" fillOpacity={0.25} stroke="#2e3237" strokeWidth={unit * 0.3} />
        ))}
        {points.map((point, index) => {
          const [x, y] = coords[index];
          if (typeof x !== "number" || typeof y !== "number") return null;
          const style = POINT_STYLE[point.kind];
          const label = point.kind === "guard_post" ? `${style.short}${point.ref}` : style.short;
          return (
            <g key={index} data-testid={`point-${index}`} onPointerDown={(event) => onPointerDown(event as unknown as PointerEvent<SVGSVGElement>, index)}
              style={{ cursor: editable ? "move" : "default" }}>
              <circle cx={x} cy={-y} r={unit * 1.4} fill={style.fill} stroke="#fff" strokeWidth={unit * 0.3} />
              <text x={x + unit * 1.8} y={-y + unit * 0.6} fontSize={unit * 2.2} fill={style.fill}>{label}</text>
            </g>
          );
        })}
      </svg>
      <div className="mb-plan-legend">
        {graphics.zones.map((zone) => (
          <span key={zone.kind} style={{ color: ZONE_STYLE[zone.kind]?.stroke }}>— зона {ZONE_STYLE[zone.kind]?.label ?? zone.kind} {Math.round(zone.value_m)} м</span>
        ))}
        <button type="button" className="link-button" onClick={() => setView(initial)}>Весь план</button>
      </div>
      {!graphics.has_situation && (
        <small className="frag-warnings">Ситуации карьера нет: на Г.5 будет пометка «привязать по плану карьера». Точки ставятся относительно блока.</small>
      )}
    </div>
  );
}
