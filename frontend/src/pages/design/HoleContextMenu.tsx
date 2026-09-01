import { useEffect, useRef } from "react";

export type HoleContextAction =
  | "inspect"
  | "delete"
  | "toggleEnabled"
  | "zoom"
  | "startTie"
  | "measure";

export function HoleContextMenu({
  x,
  y,
  holeId,
  enabled,
  onAction,
  onClose,
}: {
  x: number;
  y: number;
  holeId: string;
  enabled: boolean;
  onAction: (action: HoleContextAction) => void;
  onClose: () => void;
}) {
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onPointerDown(e: PointerEvent) {
      if (!menuRef.current?.contains(e.target as Node)) onClose();
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose]);

  return (
    <div
      ref={menuRef}
      className="hole-context-menu"
      style={{ left: x, top: y }}
      role="menu"
      aria-label={`Меню скважины ${holeId}`}
    >
      <button type="button" role="menuitem" onClick={() => onAction("inspect")}>
        Карточка скважины
      </button>
      <button type="button" role="menuitem" onClick={() => onAction("zoom")}>
        Приблизить к скважине
      </button>
      <button type="button" role="menuitem" onClick={() => onAction("startTie")}>
        Начать связь
      </button>
      <button type="button" role="menuitem" onClick={() => onAction("measure")}>
        Измерить расстояние
      </button>
      <button type="button" role="menuitem" onClick={() => onAction("toggleEnabled")}>
        {enabled ? "Исключить из расчёта" : "Вернуть в расчёт"}
      </button>
      <button type="button" role="menuitem" className="danger" onClick={() => onAction("delete")}>
        Удалить
      </button>
    </div>
  );
}
