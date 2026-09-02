import { useEffect, useRef } from "react";

export type HoleContextMenuState = {
  holeId: string;
  x: number;
  y: number;
} | null;

export function HoleContextMenu({
  menu,
  onClose,
  onOpenInspector,
  onToggleEnabled,
  onToggleStarter,
  onCopyParams,
  onZoomToHole,
  isStarter,
  enabled,
}: {
  menu: HoleContextMenuState;
  onClose: () => void;
  onOpenInspector: (id: string) => void;
  onToggleEnabled: (id: string, enabled: boolean) => void;
  onToggleStarter: (id: string) => void;
  onCopyParams: (id: string) => void;
  onZoomToHole: (id: string) => void;
  isStarter: boolean;
  enabled: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menu) return undefined;
    function onPointerDown(e: PointerEvent) {
      if (ref.current?.contains(e.target as Node)) return;
      onClose();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [menu, onClose]);

  if (!menu) return null;

  return (
    <div
      ref={ref}
      className="hole-context-menu"
      style={{ left: menu.x, top: menu.y }}
      role="menu"
      aria-label={`Меню скважины ${menu.holeId}`}
    >
      <button type="button" role="menuitem" onClick={() => { onOpenInspector(menu.holeId); onClose(); }}>
        Открыть карточку
      </button>
      <button type="button" role="menuitem" onClick={() => { onZoomToHole(menu.holeId); onClose(); }}>
        Зум к скважине
      </button>
      <button type="button" role="menuitem" onClick={() => { onToggleEnabled(menu.holeId, !enabled); onClose(); }}>
        {enabled ? "Исключить из расчёта" : "Включить в расчёт"}
      </button>
      <button type="button" role="menuitem" onClick={() => { onToggleStarter(menu.holeId); onClose(); }}>
        {isStarter ? "Снять стартер" : "Назначить стартером"}
      </button>
      <button type="button" role="menuitem" onClick={() => { onCopyParams(menu.holeId); onClose(); }}>
        Копировать параметры
      </button>
    </div>
  );
}
