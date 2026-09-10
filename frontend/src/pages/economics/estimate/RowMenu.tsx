import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useAnchoredPosition } from "./useAnchoredPosition";

/**
 * Пункт меню строки сметы.
 *
 * `expanded`/`controls` заполняются у пунктов-раскрывашек — тех, что не
 * выполняют действие, а показывают панель под строкой (формулу, редактор
 * величины). Для программ чтения с экрана такой пункт — переключатель, а не
 * команда, поэтому он обязан называть своё состояние и управляемый узел.
 */
export type RowMenuItem = {
  label: string;
  onSelect: () => void;
  danger?: boolean;
  expanded?: boolean;
  controls?: string;
};

/** Ширина списка: та же величина, что в `.row-menu-list`. */
const MENU_MIN_WIDTH = 180;

/**
 * Меню действий строки сметы (⋯): раскрывается по клику под кнопкой,
 * закрывается кликом вне себя или Escape — тот же паттерн, что у
 * `CatalogSelect` и `HoleContextMenu`.
 *
 * Список, как и поповер справочника, рисуется порталом в `document.body`:
 * внутри строки его обрезала бы таблица.
 */
export function RowMenu({ items, label }: { items: RowMenuItem[]; label: string }) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  // Меню прижимается правым краем к кнопке: она стоит у правого края таблицы.
  const position = useAnchoredPosition(triggerRef, open, "end", MENU_MIN_WIDTH);

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
    <div className="row-menu" ref={containerRef}>
      <button
        ref={triggerRef}
        type="button"
        className="row-menu-trigger"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        ⋯
      </button>
      {open && position && createPortal(
        <div
          ref={menuRef}
          className="row-menu-list"
          role="menu"
          aria-label={label}
          style={{ position: "fixed", top: position.top, left: position.left }}
        >
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              className={item.danger ? "danger" : undefined}
              aria-expanded={item.expanded}
              aria-controls={item.controls}
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
