// Меню связи по правой кнопке на плане (TASK-017, PR 4): ступень из номиналов
// системы, «Развернуть направление», «Удалить».
import { useEffect, useRef } from "react";
import { ruNumber } from "../../lib/format";
import { stepColor } from "./tieSteps";

export type TieContextMenuState = {
  tieId: string;
  fromHole: string;
  toHole: string;
  delayMs: number;
  x: number;
  y: number;
} | null;

export function TieContextMenu({
  menu,
  nominals,
  onClose,
  onSetDelay,
  onReverse,
  onRemove,
}: {
  menu: TieContextMenuState;
  nominals: number[];
  onClose: () => void;
  onSetDelay: (tieId: string, delayMs: number) => void;
  onReverse: (tieId: string) => void;
  onRemove: (tieId: string) => void;
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
  const label = `${menu.fromHole} → ${menu.toHole}`;

  return (
    <div ref={ref} className="hole-context-menu tie-context-menu" style={{ left: menu.x, top: menu.y }} role="menu" aria-label={`Меню связи ${label}`}>
      <small className="tie-context-title">{label}, {ruNumber(menu.delayMs, 0)} мс</small>
      <div className="tie-context-steps" role="group" aria-label="Ступень">
        <span>Ступень</span>
        {nominals.map((ms) => (
          <button
            key={ms}
            type="button"
            role="menuitemradio"
            aria-checked={ms === menu.delayMs}
            className={ms === menu.delayMs ? "active" : ""}
            style={{ color: stepColor(ms, nominals) }}
            onClick={() => { onSetDelay(menu.tieId, ms); onClose(); }}
          >
            {ruNumber(ms, 0)}
          </button>
        ))}
      </div>
      <button type="button" role="menuitem" onClick={() => { onReverse(menu.tieId); onClose(); }}>
        Развернуть направление
      </button>
      <button type="button" role="menuitem" onClick={() => { onRemove(menu.tieId); onClose(); }}>
        Удалить
      </button>
    </div>
  );
}
