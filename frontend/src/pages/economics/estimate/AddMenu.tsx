import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useAnchoredPosition } from "./useAnchoredPosition";

/** Те же величины, что у меню строки: список ведёт себя одинаково. */
const MENU_MIN_WIDTH = 180;
const MENU_HEIGHT = 140;

/**
 * Кнопка «+ Добавить …» со списком того, что ещё можно добавить в раздел
 * сметы: скрытые роли номенклатуры, свободные роли техники.
 *
 * От `RowMenu` отличается только видом кнопки — список ведёт себя так же и по
 * той же причине рисуется порталом: внутри таблицы его обрезало бы.
 */
export function AddMenu({
  label,
  items,
}: {
  /** Подпись кнопки и заголовок списка: «Добавить материал». */
  label: string;
  /** Пустой список кнопку не рисует: добавлять нечего. */
  items: Array<{ code: string; label: string; onSelect: () => void }>;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const position = useAnchoredPosition(triggerRef, open, "start", MENU_MIN_WIDTH, MENU_HEIGHT);

  useEffect(() => {
    if (!open) return undefined;
    function onMouseDown(e: MouseEvent) {
      const target = e.target as Node;
      if (containerRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      setOpen(false);
      triggerRef.current?.focus();
    }
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (items.length === 0) return null;

  return (
    <div className="estimate-add-menu" ref={containerRef}>
      <button
        ref={triggerRef}
        type="button"
        className="row-add"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        + {label}
      </button>
      {open && position && createPortal(
        <div
          ref={menuRef}
          className="row-menu-list"
          role="menu"
          aria-label={label}
          style={{ position: "fixed", top: position.top, left: position.left, minWidth: position.minWidth }}
        >
          {items.map((item) => (
            <button
              key={item.code}
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                item.onSelect();
              }}
            >
              {item.label}
            </button>
          ))}
        </div>,
        document.body,
      )}
    </div>
  );
}
