import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ruNumber } from "../../lib/format";
import {
  Camera,
  MAX_SCALE,
  MIN_SCALE,
  Vec2,
  Viewport,
  boundsOf,
  distance,
  fitCamera,
  niceStep,
  panCameraByScreen,
  projectOnSegment,
  rectContains,
  rectFromCorners,
  screenToWorld,
  snap,
  visibleBounds,
  worldToScreen,
  zoomAt,
} from "../../lib/geometry2d";
import type { BlockContour, Hole, HoleLoad, InitiationNetwork, Isoline, Point3 } from "../../types/design";
import { insertContourVertex, removeContourVertices } from "./contourEdits";

const HOLE_HIT_RADIUS_PX = 12;
const VERTEX_HIT_RADIUS_PX = 10;
const EDGE_HIT_RADIUS_PX = 8;
const NEIGHBOUR_COUNT = 5;
const SPACING_TOLERANCE_M = 0.5;
const CLICK_SLOP_PX = 4;
const GRID_TARGET_PX = 70;
const ZOOM_STEP = 1.3;
const ARROW_PAN_PX = 60;
const DEFAULT_CAMERA: Camera = { x: 0, y: 0, scale: 6 };

type Mode = "contour" | "holes";
type PlanTool = "select" | "add" | "face" | "pan";

const SNAP_OPTIONS = [0, 0.25, 0.5, 1, 2.5, 5];

type DragState =
  | { kind: "none" }
  | { kind: "pan"; pointerId: number; startScreen: Vec2; startCamera: Camera; moved: boolean; button: number }
  | { kind: "vertex"; pointerId: number; index: number; grabOffset: Vec2; moved: boolean }
  | { kind: "holes"; pointerId: number; ids: string[]; anchorId: string; startWorld: Vec2; deltaWorld: Vec2; moved: boolean }
  | { kind: "rubber"; pointerId: number; startScreen: Vec2; currentScreen: Vec2; additive: boolean; moved: boolean };

type Hover =
  | { kind: "none" }
  | { kind: "vertex"; index: number }
  | { kind: "edge"; index: number; point: Vec2 }
  | { kind: "hole"; id: string };

export function PlanCanvas({
  contour,
  holes,
  mode,
  selected,
  onSelectedChange,
  onContourChange,
  onToggleFreeFace,
  onMoveHoles,
  onAddHole,
  onDeleteHoles,
  camera,
  onCameraChange,
  spacingHint,
  loadsById,
  network,
  isolines,
  timesMs,
  animationMs,
}: {
  contour: BlockContour;
  holes: Hole[];
  mode: Mode;
  selected: Set<string>;
  onSelectedChange: (ids: Set<string>) => void;
  onContourChange: (vertices: Point3[], freeFaces?: number[][], coalesce?: boolean) => void;
  onToggleFreeFace: (edgeIndex: number) => void;
  onMoveHoles: (ids: string[], dx: number, dy: number) => void;
  onAddHole: (world: Vec2) => void;
  onDeleteHoles: (ids: string[]) => void;
  camera: Camera;
  onCameraChange: (camera: Camera) => void;
  spacingHint: { a: number; b: number };
  loadsById?: Record<string, HoleLoad>;
  network?: InitiationNetwork | null;
  isolines?: Isoline[];
  timesMs?: Record<string, number> | null;
  animationMs?: number | null;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [viewport, setViewport] = useState<Viewport>({ width: 800, height: 520 });
  const [drag, setDragState] = useState<DragState>({ kind: "none" });
  const [hover, setHover] = useState<Hover>({ kind: "none" });
  const [cursorWorld, setCursorWorld] = useState<Vec2 | null>(null);
  const [tool, setTool] = useState<PlanTool>("select");
  const [spaceHeld, setSpaceHeld] = useState(false);
  const [selectedVertices, setSelectedVertices] = useState<Set<number>>(new Set());
  const [showGrid, setShowGrid] = useState(true);
  const [snapStep, setSnapStep] = useState(0.5);
  const [showHelp, setShowHelp] = useState(false);

  // Актуальные значения для нативных слушателей (wheel/keydown) — без них
  // обработчики залипают на камере первого рендера.
  const cameraRef = useRef(camera);
  cameraRef.current = camera;
  const viewportRef = useRef(viewport);
  viewportRef.current = viewport;
  const pointerInsideRef = useRef(false);
  // Зеркало состояния перетаскивания: pointerdown и pointerup быстрого клика
  // приходят до перерисовки, и обработчики обязаны видеть свежее значение.
  const dragRef = useRef<DragState>(drag);
  const setDrag = useCallback((next: DragState) => {
    dragRef.current = next;
    setDragState(next);
  }, []);
  const pinchRef = useRef<{ pointers: Map<number, Vec2>; distance: number; center: Vec2 } | null>(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const box = entries[0]?.contentRect;
      if (box && box.width > 0 && box.height > 0) setViewport({ width: box.width, height: box.height });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Смена режима начинает работу заново: инструмент — «Выбор» (иначе клик по
  // скважине неожиданно добавлял бы новую), выделение вершин сбрасывается.
  useEffect(() => {
    setSelectedVertices(new Set());
    setTool("select");
  }, [mode]);

  const contentPoints = useMemo<Vec2[]>(
    () => [
      ...contour.vertices.map((v) => ({ x: v.x, y: v.y })),
      ...holes.map((h) => ({ x: h.collar.x, y: h.collar.y })),
    ],
    [contour.vertices, holes],
  );

  const fitToContent = useCallback(() => {
    const bounds = boundsOf(contentPoints);
    if (!bounds) {
      onCameraChange(DEFAULT_CAMERA);
      return;
    }
    onCameraChange(fitCamera(bounds, viewportRef.current, 0.12, camera.scale));
  }, [contentPoints, onCameraChange, camera.scale]);

  // Геометрия, появившаяся целым набором (открыли паспорт, разложили сетку),
  // сразу вписывается в окно. Ручное добавление точки по одной вид не трогает —
  // иначе план «уезжает» из-под курсора между кликами.
  const previousCountRef = useRef(contentPoints.length);
  useEffect(() => {
    const previous = previousCountRef.current;
    const current = contentPoints.length;
    previousCountRef.current = current;
    if (current - previous < 2) return;
    const bounds = boundsOf(contentPoints);
    if (bounds) onCameraChange(fitCamera(bounds, viewportRef.current, 0.12, camera.scale));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contentPoints.length]);

  const zoomBy = useCallback(
    (factor: number, at?: Vec2) => {
      const point = at ?? { x: viewportRef.current.width / 2, y: viewportRef.current.height / 2 };
      onCameraChange(zoomAt(cameraRef.current, viewportRef.current, point, factor));
    },
    [onCameraChange],
  );

  // React вешает wheel пассивно, поэтому preventDefault там не работает и
  // страница прокручивается вместо зума — слушаем событие нативно.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    function onWheel(e: WheelEvent) {
      e.preventDefault();
      const rect = el!.getBoundingClientRect();
      const screen = { x: e.clientX - rect.left, y: e.clientY - rect.top };
      const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? rect.height : 1;
      if (e.shiftKey || e.altKey) {
        const shift = e.deltaY * unit;
        onCameraChange(
          e.shiftKey
            ? panCameraByScreen(cameraRef.current, shift, 0)
            : panCameraByScreen(cameraRef.current, 0, shift),
        );
        return;
      }
      const delta = e.deltaY * unit * (e.ctrlKey ? 0.6 : 1);
      const factor = Math.exp(-delta * 0.0022);
      onCameraChange(zoomAt(cameraRef.current, viewportRef.current, screen, factor));
    }
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [onCameraChange]);

  const deleteSelectedVertices = useCallback(() => {
    if (!selectedVertices.size) return;
    const next = removeContourVertices(contour.vertices, contour.free_faces, selectedVertices);
    onContourChange(next.vertices, next.freeFaces);
    setSelectedVertices(new Set());
  }, [contour.vertices, contour.free_faces, selectedVertices, onContourChange]);

  const deleteVertexAt = useCallback(
    (index: number) => {
      const next = removeContourVertices(contour.vertices, contour.free_faces, [index]);
      onContourChange(next.vertices, next.freeFaces);
      setSelectedVertices(new Set());
      setHover({ kind: "none" });
    },
    [contour.vertices, contour.free_faces, onContourChange],
  );

  // Пробел = панорама. Слушаем на окне (а не только на сфокусированном холсте),
  // чтобы жест работал при наведении мышью, и гасим прокрутку страницы.
  useEffect(() => {
    function isTyping(target: EventTarget | null): boolean {
      const el = target as HTMLElement | null;
      if (!el || !el.tagName) return false;
      return el.tagName === "INPUT" || el.tagName === "SELECT" || el.tagName === "TEXTAREA" || el.isContentEditable;
    }
    function active(target: EventTarget | null): boolean {
      if (isTyping(target)) return false;
      // Курсор над планом — пробел всегда панорама. Если же курсор увели, а
      // фокус остался на кнопке панели, пробел должен нажимать эту кнопку.
      if (pointerInsideRef.current) return true;
      const focused = document.activeElement;
      if (focused && (focused.tagName === "BUTTON" || focused.tagName === "A")) return false;
      const wrap = wrapRef.current;
      return !!wrap && wrap.contains(focused);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.code !== "Space" || !active(e.target)) return;
      e.preventDefault();
      setSpaceHeld(true);
    }
    function onKeyUp(e: KeyboardEvent) {
      if (e.code !== "Space") return;
      if (active(e.target)) e.preventDefault();
      setSpaceHeld(false);
    }
    function onBlur() {
      setSpaceHeld(false);
    }
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", onBlur);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", onBlur);
    };
  }, []);

  function toScreenPoint(e: { clientX: number; clientY: number }): Vec2 {
    const rect = wrapRef.current!.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  function worldOf(screen: Vec2): Vec2 {
    return screenToWorld(camera, viewport, screen);
  }

  function toScreen(point: Vec2): Vec2 {
    return worldToScreen(camera, viewport, point);
  }

  function applySnap(world: Vec2): Vec2 {
    if (snapStep <= 0) return { x: round2(world.x), y: round2(world.y) };
    return { x: round2(snap(world.x, snapStep)), y: round2(snap(world.y, snapStep)) };
  }

  function holeScreenPos(hole: Hole): Vec2 {
    let point = { x: hole.collar.x, y: hole.collar.y };
    if (drag.kind === "holes" && drag.ids.includes(hole.id)) {
      point = { x: point.x + drag.deltaWorld.x, y: point.y + drag.deltaWorld.y };
    }
    return toScreen(point);
  }

  function hitHole(screen: Vec2): Hole | null {
    for (let i = holes.length - 1; i >= 0; i -= 1) {
      const h = holes[i];
      const p = toScreen({ x: h.collar.x, y: h.collar.y });
      if (distance(p, screen) <= HOLE_HIT_RADIUS_PX) return h;
    }
    return null;
  }

  function hitVertex(screen: Vec2): number | null {
    for (let i = contour.vertices.length - 1; i >= 0; i -= 1) {
      const p = toScreen(contour.vertices[i]);
      if (distance(p, screen) <= VERTEX_HIT_RADIUS_PX) return i;
    }
    return null;
  }

  function hitEdge(screen: Vec2): { index: number; point: Vec2 } | null {
    const n = contour.vertices.length;
    if (n < 2) return null;
    let best: { index: number; point: Vec2; d: number } | null = null;
    for (let i = 0; i < n; i += 1) {
      const a = toScreen(contour.vertices[i]);
      const b = toScreen(contour.vertices[(i + 1) % n]);
      const projection = projectOnSegment(screen, a, b);
      if (projection.distance <= EDGE_HIT_RADIUS_PX && (!best || projection.distance < best.d)) {
        best = { index: i, point: projection.point, d: projection.distance };
      }
    }
    return best ? { index: best.index, point: best.point } : null;
  }

  function updateHover(screen: Vec2) {
    if (mode === "contour") {
      const vertexIndex = hitVertex(screen);
      if (vertexIndex !== null) {
        setHover({ kind: "vertex", index: vertexIndex });
        return;
      }
      const edge = hitEdge(screen);
      setHover(edge ? { kind: "edge", index: edge.index, point: edge.point } : { kind: "none" });
      return;
    }
    const hole = hitHole(screen);
    setHover(hole ? { kind: "hole", id: hole.id } : { kind: "none" });
  }

  function appendVertex(world: Vec2) {
    const snapped = applySnap(world);
    onContourChange([...contour.vertices, { x: snapped.x, y: snapped.y, z: contour.bench.crest_z_m }]);
  }

  function splitEdge(edgeIndex: number, world: Vec2) {
    const snapped = applySnap(world);
    const next = insertContourVertex(contour.vertices, contour.free_faces, edgeIndex, {
      x: snapped.x,
      y: snapped.y,
      z: contour.bench.crest_z_m,
    });
    onContourChange(next.vertices, next.freeFaces);
  }

  function startPan(e: React.PointerEvent, screen: Vec2) {
    setDrag({ kind: "pan", pointerId: e.pointerId, startScreen: screen, startCamera: camera, moved: false, button: e.button });
  }

  function handlePointerDown(e: React.PointerEvent) {
    const drag = dragRef.current;
    if (e.button === 2 && drag.kind !== "none") return;
    const screen = toScreenPoint(e);
    wrapRef.current?.focus({ preventScroll: true });
    (e.currentTarget as Element).setPointerCapture(e.pointerId);

    if (e.pointerType === "touch") {
      const pinch = pinchRef.current ?? { pointers: new Map<number, Vec2>(), distance: 0, center: screen };
      pinch.pointers.set(e.pointerId, screen);
      pinchRef.current = pinch;
      if (pinch.pointers.size === 2) {
        const [a, b] = Array.from(pinch.pointers.values());
        pinch.distance = distance(a, b);
        pinch.center = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
        setDrag({ kind: "none" });
        return;
      }
    }

    // Средняя и правая кнопки, пробел и инструмент «рука» — всегда панорама.
    if (e.button === 1 || e.button === 2 || spaceHeld || tool === "pan") {
      startPan(e, screen);
      return;
    }
    if (e.button !== 0) return;

    if (mode === "contour") {
      const vertexIndex = hitVertex(screen);
      const edge = hitEdge(screen);

      if (tool === "face") {
        if (edge) onToggleFreeFace(edge.index);
        return;
      }
      if (tool === "add") {
        if (edge && vertexIndex === null) splitEdge(edge.index, worldOf(edge.point));
        else if (vertexIndex === null) appendVertex(worldOf(screen));
        return;
      }
      // tool === "select"
      if (vertexIndex !== null) {
        setSelectedVertices((prev) => {
          if (e.shiftKey || e.ctrlKey || e.metaKey) {
            const next = new Set(prev);
            if (next.has(vertexIndex)) next.delete(vertexIndex);
            else next.add(vertexIndex);
            return next;
          }
          return prev.has(vertexIndex) ? prev : new Set([vertexIndex]);
        });
        const vertexScreen = toScreen(contour.vertices[vertexIndex]);
        setDrag({
          kind: "vertex",
          pointerId: e.pointerId,
          index: vertexIndex,
          grabOffset: { x: vertexScreen.x - screen.x, y: vertexScreen.y - screen.y },
          moved: false,
        });
        return;
      }
      setDrag({
        kind: "rubber",
        pointerId: e.pointerId,
        startScreen: screen,
        currentScreen: screen,
        additive: e.shiftKey,
        moved: false,
      });
      return;
    }

    // mode === "holes"
    if (tool === "add") {
      if (!hitHole(screen)) onAddHole(applySnap(worldOf(screen)));
      return;
    }
    const hole = hitHole(screen);
    if (hole) {
      let ids: string[];
      if (e.shiftKey || e.ctrlKey || e.metaKey) {
        const next = new Set(selected);
        if (next.has(hole.id)) next.delete(hole.id);
        else next.add(hole.id);
        onSelectedChange(next);
        ids = Array.from(next.size ? next : new Set([hole.id]));
      } else if (selected.has(hole.id)) {
        ids = Array.from(selected);
      } else {
        ids = [hole.id];
        onSelectedChange(new Set(ids));
      }
      setDrag({
        kind: "holes",
        pointerId: e.pointerId,
        ids,
        anchorId: hole.id,
        startWorld: worldOf(screen),
        deltaWorld: { x: 0, y: 0 },
        moved: false,
      });
      return;
    }
    setDrag({
      kind: "rubber",
      pointerId: e.pointerId,
      startScreen: screen,
      currentScreen: screen,
      additive: e.shiftKey,
      moved: false,
    });
  }

  function handlePointerMove(e: React.PointerEvent) {
    const drag = dragRef.current;
    const screen = toScreenPoint(e);
    setCursorWorld(worldOf(screen));

    const pinch = pinchRef.current;
    if (pinch && pinch.pointers.has(e.pointerId)) {
      pinch.pointers.set(e.pointerId, screen);
      if (pinch.pointers.size === 2) {
        const [a, b] = Array.from(pinch.pointers.values());
        const nextDistance = distance(a, b);
        const nextCenter = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
        if (pinch.distance > 0) {
          const zoomed = zoomAt(camera, viewport, nextCenter, nextDistance / pinch.distance);
          onCameraChange(
            panCameraByScreen(zoomed, -(nextCenter.x - pinch.center.x), -(nextCenter.y - pinch.center.y)),
          );
        }
        pinch.distance = nextDistance;
        pinch.center = nextCenter;
        return;
      }
    }

    if (drag.kind === "none") {
      updateHover(screen);
      return;
    }
    if (drag.pointerId !== e.pointerId) return;

    if (drag.kind === "pan") {
      const world0 = screenToWorld(drag.startCamera, viewport, drag.startScreen);
      const world1 = screenToWorld(drag.startCamera, viewport, screen);
      onCameraChange({
        ...drag.startCamera,
        x: drag.startCamera.x - (world1.x - world0.x),
        y: drag.startCamera.y - (world1.y - world0.y),
      });
      if (!drag.moved && distance(screen, drag.startScreen) > CLICK_SLOP_PX) setDrag({ ...drag, moved: true });
      return;
    }
    if (drag.kind === "vertex") {
      const target = { x: screen.x + drag.grabOffset.x, y: screen.y + drag.grabOffset.y };
      const world = applySnap(worldOf(target));
      const next = contour.vertices.map((v, i) => (i === drag.index ? { ...v, x: world.x, y: world.y } : v));
      // Шаг истории создаёт только первое смещение — иначе одно перетаскивание
      // забивало бы весь стек undo промежуточными позициями.
      onContourChange(next, undefined, drag.moved);
      if (!drag.moved) setDrag({ ...drag, moved: true });
      return;
    }
    if (drag.kind === "holes") {
      const anchor = holes.find((h) => h.id === drag.anchorId);
      const raw = worldOf(screen);
      let delta = { x: raw.x - drag.startWorld.x, y: raw.y - drag.startWorld.y };
      if (e.shiftKey) {
        // Shift — ортогональное перемещение вдоль преобладающей оси.
        if (Math.abs(delta.x) >= Math.abs(delta.y)) delta = { x: delta.x, y: 0 };
        else delta = { x: 0, y: delta.y };
      }
      if (anchor && snapStep > 0) {
        const snapped = applySnap({ x: anchor.collar.x + delta.x, y: anchor.collar.y + delta.y });
        delta = { x: snapped.x - anchor.collar.x, y: snapped.y - anchor.collar.y };
      }
      setDrag({ ...drag, deltaWorld: delta, moved: true });
      return;
    }
    if (drag.kind === "rubber") {
      setDrag({ ...drag, currentScreen: screen, moved: distance(screen, drag.startScreen) > CLICK_SLOP_PX });
    }
  }

  function handlePointerUp(e: React.PointerEvent) {
    const drag = dragRef.current;
    const screen = toScreenPoint(e);
    const pinch = pinchRef.current;
    if (pinch) {
      pinch.pointers.delete(e.pointerId);
      if (pinch.pointers.size === 0) pinchRef.current = null;
      else pinch.distance = 0;
    }

    if (drag.kind !== "none" && drag.pointerId === e.pointerId) {
      if (drag.kind === "pan" && !drag.moved && drag.button === 2) {
        // Правый клик без перетаскивания — быстрое удаление объекта под курсором.
        if (mode === "contour") {
          const vertexIndex = hitVertex(screen);
          if (vertexIndex !== null) deleteVertexAt(vertexIndex);
        } else {
          const hole = hitHole(screen);
          if (hole) {
            onDeleteHoles([hole.id]);
            const next = new Set(selected);
            next.delete(hole.id);
            onSelectedChange(next);
          }
        }
      }
      if (drag.kind === "holes" && drag.moved) {
        const dx = round2(drag.deltaWorld.x);
        const dy = round2(drag.deltaWorld.y);
        if (dx !== 0 || dy !== 0) onMoveHoles(drag.ids, dx, dy);
      }
      if (drag.kind === "rubber") {
        const rect = rectFromCorners(drag.startScreen, drag.currentScreen);
        if (drag.moved) {
          if (mode === "contour") {
            const indices = contour.vertices
              .map((v, i) => ({ i, p: toScreen(v) }))
              .filter(({ p }) => rectContains(rect, p))
              .map(({ i }) => i);
            setSelectedVertices((prev) => (drag.additive ? new Set([...prev, ...indices]) : new Set(indices)));
          } else {
            const ids = holes
              .filter((h) => rectContains(rect, toScreen({ x: h.collar.x, y: h.collar.y })))
              .map((h) => h.id);
            onSelectedChange(drag.additive ? new Set([...selected, ...ids]) : new Set(ids));
          }
        } else if (!drag.additive) {
          // Клик по пустому месту — снять выделение.
          if (mode === "contour") setSelectedVertices(new Set());
          else if (selected.size) onSelectedChange(new Set());
        }
      }
      setDrag({ kind: "none" });
    }
    updateHover(screen);
  }

  function handlePointerLeave() {
    pointerInsideRef.current = false;
    setCursorWorld(null);
    setHover({ kind: "none" });
  }

  function handleDoubleClick(e: React.MouseEvent) {
    // Двойной клик — сокращение инструмента «Выбор». У остальных инструментов
    // одиночный клик уже что-то делает, и дублировать его не нужно.
    if (tool !== "select") return;
    const screen = toScreenPoint(e);
    if (mode === "contour") {
      const vertexIndex = hitVertex(screen);
      if (vertexIndex !== null) {
        deleteVertexAt(vertexIndex);
        return;
      }
      const edge = hitEdge(screen);
      if (edge) splitEdge(edge.index, worldOf(edge.point));
      return;
    }
    if (!hitHole(screen)) onAddHole(applySnap(worldOf(screen)));
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    const target = e.target as HTMLElement;
    // В полях панели инструментов (например, выбор шага привязки) клавиши
    // принадлежат самому полю.
    if (target.tagName === "INPUT" || target.tagName === "SELECT" || target.tagName === "TEXTAREA") return;
    const key = e.key.toLowerCase();
    if (key === "delete" || key === "backspace") {
      if (mode === "contour" && selectedVertices.size) {
        e.preventDefault();
        e.stopPropagation();
        deleteSelectedVertices();
      }
      return;
    }
    if (key === "escape") {
      setSelectedVertices(new Set());
      onSelectedChange(new Set());
      setDrag({ kind: "none" });
      return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (key === "v" || key === "1" || key === "м") setTool("select");
    else if (key === "a" || key === "2" || key === "ф") setTool("add");
    else if (mode === "contour" && (key === "f" || key === "3" || key === "а")) setTool("face");
    else if (key === "h" || key === "4" || key === "р") setTool("pan");
    else if (key === "+" || key === "=") zoomBy(ZOOM_STEP);
    else if (key === "-" || key === "_") zoomBy(1 / ZOOM_STEP);
    else if (key === "0") fitToContent();
    else if (key === "arrowleft") { e.preventDefault(); onCameraChange(panCameraByScreen(camera, -ARROW_PAN_PX, 0)); }
    else if (key === "arrowright") { e.preventDefault(); onCameraChange(panCameraByScreen(camera, ARROW_PAN_PX, 0)); }
    else if (key === "arrowup") { e.preventDefault(); onCameraChange(panCameraByScreen(camera, 0, -ARROW_PAN_PX)); }
    else if (key === "arrowdown") { e.preventDefault(); onCameraChange(panCameraByScreen(camera, 0, ARROW_PAN_PX)); }
  }

  const panning = drag.kind === "pan";
  const cursorClass = panning
    ? "grabbing"
    : spaceHeld || tool === "pan"
      ? "grab"
      : tool === "add"
        ? "crosshair"
        : tool === "face"
          ? "face"
          : hover.kind === "vertex" || hover.kind === "hole"
            ? "move"
            : "default";

  const gridStep = niceStep(GRID_TARGET_PX / camera.scale);
  const view = visibleBounds(camera, viewport);
  const gridLinesX: number[] = [];
  const gridLinesY: number[] = [];
  if (showGrid && gridStep > 0) {
    const maxLines = 400;
    const startX = Math.floor(view.minX / gridStep) * gridStep;
    for (let x = startX, guard = 0; x <= view.maxX && guard < maxLines; x += gridStep, guard += 1) gridLinesX.push(x);
    const startY = Math.floor(view.minY / gridStep) * gridStep;
    for (let y = startY, guard = 0; y <= view.maxY && guard < maxLines; y += gridStep, guard += 1) gridLinesY.push(y);
  }

  const scaleBarMeters = niceStep(120 / camera.scale);
  const scaleBarPx = scaleBarMeters * camera.scale;

  const draggedSingleHole =
    drag.kind === "holes" && drag.ids.length === 1 ? holes.find((h) => h.id === drag.ids[0]) : null;
  const dimensionLines = draggedSingleHole
    ? buildDimensionLines(draggedSingleHole, drag.kind === "holes" ? drag.deltaWorld : { x: 0, y: 0 }, holes, spacingHint)
    : [];

  const origin = toScreen({ x: 0, y: 0 });
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

  const hoveredVertexScreen =
    mode === "contour" && hover.kind === "vertex" && drag.kind === "none" && contour.vertices[hover.index]
      ? toScreen(contour.vertices[hover.index])
      : null;

  const tools: { id: PlanTool; label: string; icon: string; title: string }[] = [
    { id: "select", label: "Выбор", icon: "⬈", title: "Выбор и перетаскивание (V)" },
    {
      id: "add",
      label: mode === "contour" ? "Точка" : "Скважина",
      icon: "＋",
      title: mode === "contour" ? "Добавить точку контура (A)" : "Добавить скважину (A)",
    },
    ...(mode === "contour"
      ? [{ id: "face" as PlanTool, label: "Откос", icon: "▤", title: "Отметить открытый откос (F)" }]
      : []),
    { id: "pan", label: "Панорама", icon: "✥", title: "Панорама — тянуть холст (H)" },
  ];

  const toolbar = (
    <div className="plan-toolbar">
      <div className="plan-tool-group">
        {tools.map((item) => (
          <button
            key={item.id}
            type="button"
            className={tool === item.id ? "active" : ""}
            title={item.title}
            aria-pressed={tool === item.id}
            onClick={() => setTool(item.id)}
          >
            <span aria-hidden="true">{item.icon}</span> {item.label}
          </button>
        ))}
      </div>
      <div className="plan-tool-group">
        <button type="button" title="Приблизить (+)" disabled={camera.scale >= MAX_SCALE} onClick={() => zoomBy(ZOOM_STEP)}>＋</button>
        <button type="button" title="Отдалить (−)" disabled={camera.scale <= MIN_SCALE} onClick={() => zoomBy(1 / ZOOM_STEP)}>−</button>
        <button type="button" title="Показать всё (0)" onClick={fitToContent}>⤢ По размеру</button>
      </div>
      <div className="plan-tool-group">
        <label className="plan-toggle" title="Показывать координатную сетку">
          <input type="checkbox" checked={showGrid} onChange={(e) => setShowGrid(e.target.checked)} /> Сетка
        </label>
        <label className="plan-toggle" title="Привязка координат к шагу">
          Привязка
          <select value={snapStep} onChange={(e) => setSnapStep(Number(e.target.value))}>
            {SNAP_OPTIONS.map((step) => (
              <option key={step} value={step}>{step === 0 ? "выкл" : `${formatMeters(step)} м`}</option>
            ))}
          </select>
        </label>
      </div>
      {mode === "contour" ? (
        <div className="plan-tool-group">
          <button
            type="button"
            title="Удалить выделенные точки (Delete)"
            disabled={!selectedVertices.size}
            onClick={deleteSelectedVertices}
          >
            🗑 Удалить точки{selectedVertices.size ? ` (${selectedVertices.size})` : ""}
          </button>
          <button
            type="button"
            title="Удалить все точки контура"
            disabled={!contour.vertices.length}
            onClick={() => { onContourChange([], []); setSelectedVertices(new Set()); }}
          >
            Очистить контур
          </button>
        </div>
      ) : (
        <div className="plan-tool-group">
          <button
            type="button"
            title="Удалить выделенные скважины (Delete)"
            disabled={!selected.size}
            onClick={() => { onDeleteHoles(Array.from(selected)); onSelectedChange(new Set()); }}
          >
            🗑 Удалить скважины{selected.size ? ` (${selected.size})` : ""}
          </button>
        </div>
      )}
      <button
        type="button"
        className={`plan-help-toggle${showHelp ? " active" : ""}`}
        title="Управление планом"
        aria-expanded={showHelp}
        onClick={() => setShowHelp((prev) => !prev)}
      >
        ？
      </button>
    </div>
  );

  return (
    // Обработчик клавиш висит на всей панели: горячие клавиши обязаны работать
    // и когда фокус остался на кнопке инструмента.
    <div className="plan-canvas-panel" onKeyDown={handleKeyDown}>
      {toolbar}
      <div
        ref={wrapRef}
        className={`plan-canvas-wrap cursor-${cursorClass}`}
        tabIndex={0}
        role="application"
        aria-label="План блока"
        onPointerEnter={() => { pointerInsideRef.current = true; }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onPointerLeave={handlePointerLeave}
        onDoubleClick={handleDoubleClick}
        onContextMenu={(e) => e.preventDefault()}
      >
      <svg className="plan-canvas">
        <defs>
          <marker id="arrow-connector" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="#7a6ee0" />
          </marker>
        </defs>

        {showGrid && (
          <g className="plan-grid">
            {gridLinesX.map((x) => {
              const p = toScreen({ x, y: 0 });
              return <line key={`gx-${x}`} x1={p.x} y1={0} x2={p.x} y2={viewport.height} className={isMajor(x, gridStep) ? "grid-line major" : "grid-line"} />;
            })}
            {gridLinesY.map((y) => {
              const p = toScreen({ x: 0, y });
              return <line key={`gy-${y}`} x1={0} y1={p.y} x2={viewport.width} y2={p.y} className={isMajor(y, gridStep) ? "grid-line major" : "grid-line"} />;
            })}
          </g>
        )}

        <line x1={0} y1={origin.y} x2={viewport.width} y2={origin.y} className="axis-line" />
        <line x1={origin.x} y1={0} x2={origin.x} y2={viewport.height} className="axis-line" />

        {isolines?.map((iso, i) => (
          <g key={`iso-${i}`}>
            {iso.segments.map((seg, j) => {
              const a = toScreen({ x: seg[0][0], y: seg[0][1] });
              const b = toScreen({ x: seg[1][0], y: seg[1][1] });
              return <line key={j} x1={a.x} y1={a.y} x2={b.x} y2={b.y} className="isoline-segment" />;
            })}
          </g>
        ))}

        {contour.vertices.length >= 3 && (
          <polygon
            className="contour-shape"
            points={contour.vertices.map((v) => { const p = toScreen(v); return `${p.x},${p.y}`; }).join(" ")}
          />
        )}
        {contour.vertices.length >= 2 && contour.vertices.map((v, i) => {
          const a = toScreen(v);
          const b = toScreen(contour.vertices[(i + 1) % contour.vertices.length]);
          const isFree = freeFaceSet.has([i, (i + 1) % contour.vertices.length].join("-"));
          const isHovered = mode === "contour" && hover.kind === "edge" && hover.index === i;
          return (
            <line
              key={`edge-${i}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              className={`contour-edge${isFree ? " free" : ""}${isHovered ? " hovered" : ""}`}
            />
          );
        })}

        {mode === "contour" && hover.kind === "edge" && (tool === "add" || tool === "select") && (
          <circle cx={hover.point.x} cy={hover.point.y} r={4.5} className="contour-insert-hint" />
        )}

        {mode === "contour" && contour.vertices.map((v, i) => {
          const p = toScreen(v);
          const isSelected = selectedVertices.has(i);
          const isHovered = hover.kind === "vertex" && hover.index === i;
          return (
            <g key={`vertex-${i}`} className={`contour-vertex-group${isSelected ? " selected" : ""}${isHovered ? " hovered" : ""}`}>
              <circle cx={p.x} cy={p.y} r={isSelected ? 7 : 5.5} className="contour-vertex" />
              <text x={p.x + 9} y={p.y - 8} className="contour-vertex-label">{i + 1}</text>
            </g>
          );
        })}

        {network?.connectors.map((c, i) => {
          const from = holesById.get(c.from_hole);
          const to = holesById.get(c.to_hole);
          if (!from || !to) return null;
          const a = toScreen({ x: from.collar.x, y: from.collar.y });
          const b = toScreen({ x: to.collar.x, y: to.collar.y });
          const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
          return (
            <g key={`conn-${i}`}>
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} className="connector-line" markerEnd="url(#arrow-connector)" />
              {c.delay_ms > 0 && <text x={mid.x} y={mid.y - 2} className="connector-label">{ruNumber(c.delay_ms, 0)}</text>}
            </g>
          );
        })}

        {holes.map((h) => {
          const p = holeScreenPos(h);
          const isSelected = selected.has(h.id);
          const isHovered = hover.kind === "hole" && hover.id === h.id;
          const load = loadsById?.[h.id];
          const chargeColor = load && maxChargeKg > 0 ? chargeMassColor(load.total_charge_kg, maxChargeKg) : null;
          const radius = Math.max(isSelected ? 6.5 : 5, ((h.diameter_mm / 1000) * camera.scale) / 2);
          let animClass = "";
          if (animating) {
            const t = timesMs![h.id];
            animClass = t !== undefined && t <= animationMs! ? " fired" : " unfired";
          }
          return (
            <g
              key={h.id}
              className={`hole-marker kind-${h.kind}${isSelected ? " selected" : ""}${isHovered ? " hovered" : ""}${!h.enabled ? " disabled" : ""}${animClass}`}
            >
              <circle cx={p.x} cy={p.y} r={radius} style={chargeColor ? { fill: chargeColor } : undefined} />
            </g>
          );
        })}

        {dimensionLines.map((line, i) => {
          const a = toScreen(line.from);
          const b = toScreen(line.to);
          const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
          return (
            <g key={i} className={line.warn ? "dimension warn" : "dimension"}>
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
              <text x={mid.x} y={mid.y - 4}>{ruNumber(line.distance, 2)} м</text>
            </g>
          );
        })}

        {drag.kind === "rubber" && drag.moved && (
          <rect
            className="rubber-band"
            x={Math.min(drag.startScreen.x, drag.currentScreen.x)}
            y={Math.min(drag.startScreen.y, drag.currentScreen.y)}
            width={Math.abs(drag.currentScreen.x - drag.startScreen.x)}
            height={Math.abs(drag.currentScreen.y - drag.startScreen.y)}
          />
        )}

        <g className="plan-scale-bar" transform={`translate(${viewport.width - scaleBarPx - 18}, ${viewport.height - 20})`}>
          <line x1={0} y1={0} x2={scaleBarPx} y2={0} />
          <line x1={0} y1={-4} x2={0} y2={4} />
          <line x1={scaleBarPx} y1={-4} x2={scaleBarPx} y2={4} />
          <text x={scaleBarPx / 2} y={-7}>{formatMeters(scaleBarMeters)} м</text>
        </g>
      </svg>

      {hoveredVertexScreen && tool === "select" && (
        <button
          type="button"
          className="vertex-delete-badge"
          style={{ left: hoveredVertexScreen.x - 26, top: hoveredVertexScreen.y - 26 }}
          title="Удалить точку (Delete)"
          onPointerDown={(e) => { e.stopPropagation(); e.preventDefault(); }}
          onClick={(e) => {
            e.stopPropagation();
            if (hover.kind === "vertex") deleteVertexAt(hover.index);
          }}
        >
          ×
        </button>
      )}

      <div className="plan-readout">
        {cursorWorld ? (
          <span>X {ruNumber(cursorWorld.x, 1)} · Y {ruNumber(cursorWorld.y, 1)} м</span>
        ) : (
          <span>Курсор вне плана</span>
        )}
        <span className="plan-readout-sep">|</span>
        <span>сетка {formatMeters(gridStep)} м</span>
        <span className="plan-readout-sep">|</span>
        <span>{ruNumber(camera.scale, camera.scale >= 10 ? 0 : 2)} px/м</span>
      </div>

      {showHelp ? (
        <div className="plan-help">
          <b>Управление планом</b>
          <ul>
            <li><i>Перемещение:</i> тянуть правой или средней кнопкой мыши, либо пробел + перетаскивание, либо инструмент «Панорама», либо стрелки на клавиатуре.</li>
            <li><i>Масштаб:</i> колесо мыши над планом (страница при этом не прокручивается), кнопки ＋/−, клавиши + и −, «По размеру» или 0 — вписать всё в окно.</li>
            <li><i>Контур:</i> «Точка» — клик добавляет вершину, клик по ребру вставляет её в середину ребра. «Выбор» — перетаскивание вершины, рамка выделяет несколько.</li>
            <li><i>Удаление точки:</i> двойной клик по ней, правый клик, крестик рядом с ней или Delete для выделенных.</li>
            <li><i>Откосы:</i> инструмент «Откос» — клик по ребру помечает его открытым.</li>
            <li><i>Скважины:</i> «Скважина» — клик добавляет, «Выбор» — перетаскивание (Shift — строго по оси), рамка выделяет, Delete удаляет.</li>
            <li><i>Клавиши:</i> V — выбор, A — добавление, F — откос, H — панорама, Esc — снять выделение.</li>
          </ul>
        </div>
      ) : (
        <div className="plan-canvas-hint">
          {mode === "contour"
            ? "Колесо — масштаб · правая кнопка или пробел — перемещение · двойной клик по точке — удалить · «？» — все жесты"
            : "Колесо — масштаб · правая кнопка или пробел — перемещение · двойной клик — новая скважина · «？» — все жесты"}
        </div>
      )}
      </div>
    </div>
  );
}

function isMajor(value: number, step: number): boolean {
  return Math.abs(Math.round(value / step) % 5) === 0;
}

function formatMeters(value: number): string {
  if (value >= 1) return ruNumber(value, value % 1 === 0 ? 0 : 1);
  return ruNumber(value, 2);
}

function chargeMassColor(massKg: number, maxMassKg: number): string {
  const ratio = Math.max(0, Math.min(1, massKg / maxMassKg));
  const hue = 48 - 48 * ratio; // жёлтый (лёгкий заряд) → красный (тяжёлый)
  return `hsl(${hue}, 72%, 46%)`;
}

function round2(v: number): number {
  return Math.round(v * 100) / 100;
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
