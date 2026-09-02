import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";

type Position = { x: number; y: number };

const EDGE_PADDING = 8;

// Позиция живёт на уровне модуля: панель размонтируется при закрытии и при
// смене этапа, а инженер ожидает, что она откроется там, куда он её оттащил.
let lastPosition: Position = { x: EDGE_PADDING, y: EDGE_PADDING };
let lastCollapsed = false;

function clampToParent(aside: HTMLElement, next: Position): Position {
  const parent = aside.offsetParent as HTMLElement | null;
  if (!parent) return next;
  const maxX = Math.max(EDGE_PADDING, parent.clientWidth - aside.offsetWidth - EDGE_PADDING);
  const maxY = Math.max(EDGE_PADDING, parent.clientHeight - aside.offsetHeight - EDGE_PADDING);
  return {
    x: Math.min(maxX, Math.max(EDGE_PADDING, next.x)),
    y: Math.min(maxY, Math.max(EDGE_PADDING, next.y)),
  };
}

export function StageInspector({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const asideRef = useRef<HTMLElement>(null);
  const [position, setPosition] = useState<Position>(lastPosition);
  const [collapsed, setCollapsed] = useState(lastCollapsed);
  const [dragging, setDragging] = useState(false);
  const dragStart = useRef<{ pointer: Position; origin: Position } | null>(null);

  useEffect(() => { lastPosition = position; }, [position]);
  useEffect(() => { lastCollapsed = collapsed; }, [collapsed]);

  // После монтирования и при смене размера окна панель не должна оказаться за
  // краем карты — например, если её оттащили вправо на широком экране.
  useEffect(() => {
    const aside = asideRef.current;
    if (!aside) return undefined;
    const settle = () => setPosition((prev) => clampToParent(aside, prev));
    settle();
    window.addEventListener("resize", settle);
    return () => window.removeEventListener("resize", settle);
  }, [collapsed]);

  const onHeaderPointerDown = useCallback((e: ReactPointerEvent<HTMLElement>) => {
    if (e.button !== 0) return;
    if ((e.target as HTMLElement).closest("button")) return;
    dragStart.current = { pointer: { x: e.clientX, y: e.clientY }, origin: position };
    e.currentTarget.setPointerCapture(e.pointerId);
    setDragging(true);
  }, [position]);

  const onHeaderPointerMove = useCallback((e: ReactPointerEvent<HTMLElement>) => {
    const start = dragStart.current;
    const aside = asideRef.current;
    if (!start || !aside) return;
    setPosition(clampToParent(aside, {
      x: start.origin.x + (e.clientX - start.pointer.x),
      y: start.origin.y + (e.clientY - start.pointer.y),
    }));
  }, []);

  const endDrag = useCallback((e: ReactPointerEvent<HTMLElement>) => {
    if (!dragStart.current) return;
    dragStart.current = null;
    setDragging(false);
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
  }, []);

  return (
    <aside
      ref={asideRef}
      className={`stage-inspector${collapsed ? " collapsed" : ""}${dragging ? " dragging" : ""}`}
      aria-label={title}
      style={{ left: position.x, top: position.y }}
    >
      <header
        onPointerDown={onHeaderPointerDown}
        onPointerMove={onHeaderPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onDoubleClick={() => setCollapsed((prev) => !prev)}
        title="Перетащите за заголовок · двойной клик — свернуть"
      >
        <b>{title}</b>
        <span className="stage-inspector-actions">
          <button
            type="button"
            className="stage-inspector-collapse"
            onClick={() => setCollapsed((prev) => !prev)}
            aria-label={collapsed ? "Развернуть панель" : "Свернуть панель"}
            aria-expanded={!collapsed}
          >
            {collapsed ? "+" : "−"}
          </button>
          <button type="button" className="stage-inspector-close" onClick={onClose} aria-label="Закрыть панель">×</button>
        </span>
      </header>
      {!collapsed && (
        <div className="stage-inspector-body">
          {children}
        </div>
      )}
    </aside>
  );
}
