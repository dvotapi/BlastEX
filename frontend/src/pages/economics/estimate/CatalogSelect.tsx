import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { money } from "../format";
import { useAnchoredPosition } from "./useAnchoredPosition";

/**
 * Позиция справочника в комбобоксе строки сметы. `caption` — необязательная
 * подсказка (вторая строка), которая тоже участвует в поиске по подстроке.
 */
export type CatalogOption = {
  code: string;
  name: string;
  caption?: string;
  price?: number;
  unit?: string;
  disabled?: boolean;
};

/** Ширина поповера: та же величина, что в `.catalog-select-popover`. */
const POPOVER_MIN_WIDTH = 260;

/**
 * Свой комбобокс со справочником в строке сметы: кнопка, показывающая
 * выбранное имя, и поповер с полем поиска. Не модальная палитра на весь
 * экран (в отличие от `CommandPalette`) — раскрывается прямо под кнопкой и
 * закрывается кликом вне себя.
 *
 * В строке сметы кнопка выглядит обычным текстом (`variant="ghost"`):
 * название статьи читается как название, а не как поле ввода, и только при
 * наведении и с клавиатуры показывает, что его можно сменить. Вид поля с
 * рамкой (`variant="field"`) остаётся там, где выбор — самостоятельный
 * элемент формы, а не ячейка таблицы: в карточке бурения.
 *
 * Поповер рисуется порталом в `document.body`: ячейка названия обрезает
 * содержимое по многоточию, и список, нарисованный внутри строки, был бы
 * срезан по её высоте.
 */
export function CatalogSelect({
  id,
  label,
  value,
  options,
  placeholder = "не выбрано",
  onChange,
  disabled,
  variant = "ghost",
}: {
  id: string;
  label: string;
  value: string;
  options: CatalogOption[];
  placeholder?: string;
  onChange: (code: string) => void;
  disabled?: boolean;
  variant?: "ghost" | "field";
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const position = useAnchoredPosition(buttonRef, open, "start", POPOVER_MIN_WIDTH);

  const selected = options.find((option) => option.code === value);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter(
      (option) =>
        option.name.toLowerCase().includes(q) || (option.caption ?? "").toLowerCase().includes(q),
    );
  }, [options, query]);

  // Смена запроса — активный пункт снова первый: старый индекс мог указывать
  // мимо нового, короткого списка.
  useEffect(() => {
    setActive(0);
  }, [query]);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActive(0);
  }, [open]);

  // Фокус ставится ref-колбэком в момент монтирования поля, а не эффектом по
  // `open`: поповер живёт в портале и появляется на рендер позже кнопки —
  // когда `useAnchoredPosition` уже измерил её, — поэтому в эффекте по `open`
  // поля ещё не существует.
  const focusSearch = useCallback((node: HTMLInputElement | null) => {
    node?.focus();
  }, []);

  // Клик вне комбобокса закрывает поповер — обычный паттерн выпадающих
  // списков проекта (см. `HoleContextMenu`), здесь на `mousedown`, а не на
  // `click`, чтобы поповер не подхватывал клик, которым его же открыли.
  //
  // Проверяются оба узла: поповер живёт в портале и предком кнопки не
  // является, поэтому по одному контейнеру клик по пункту списка считался бы
  // «кликом вне» и закрывал список раньше, чем срабатывал выбор.
  useEffect(() => {
    if (!open) return undefined;
    function onMouseDown(e: MouseEvent) {
      const target = e.target as Node;
      if (containerRef.current?.contains(target) || popoverRef.current?.contains(target)) return;
      setOpen(false);
    }
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [open]);

  function close() {
    setOpen(false);
    buttonRef.current?.focus();
  }

  function choose(option: CatalogOption) {
    if (option.disabled) return;
    onChange(option.code);
    close();
  }

  function onButtonKeyDown(e: KeyboardEvent<HTMLButtonElement>) {
    if (disabled) return;
    if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
    }
  }

  function onPopoverKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, Math.max(0, filtered.length - 1)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const option = filtered[active];
      if (option) choose(option);
    }
  }

  const listboxId = `${id}-listbox`;
  const activeOption = filtered[active];
  const activeOptionId = activeOption ? `${id}-option-${activeOption.code}` : undefined;

  return (
    <div className="catalog-select" ref={containerRef}>
      <button
        ref={buttonRef}
        type="button"
        id={id}
        role="combobox"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        aria-activedescendant={open ? activeOptionId : undefined}
        disabled={disabled}
        className={`catalog-select-button is-${variant}`}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={onButtonKeyDown}
      >
        {/* `title`: в строке сметы название урезано по ширине колонки, а
            полное имя позиции сметчику нужно целиком. */}
        <span className="catalog-select-value" title={selected?.name ?? undefined}>
          {selected?.name ?? placeholder}
        </span>
        <span className="catalog-select-caret" aria-hidden="true">▾</span>
      </button>
      {open && position && createPortal(
        <div
          ref={popoverRef}
          className="catalog-select-popover"
          style={{ position: "fixed", top: position.top, left: position.left }}
          onKeyDown={onPopoverKeyDown}
        >
          <input
            ref={focusSearch}
            type="search"
            role="searchbox"
            aria-label="Поиск в справочнике"
            className="catalog-select-search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <ul role="listbox" id={listboxId} className="catalog-select-list">
            {filtered.length === 0 && <li className="catalog-select-empty">Ничего не найдено</li>}
            {filtered.map((option, index) => (
              <li key={option.code}>
                <button
                  type="button"
                  id={`${id}-option-${option.code}`}
                  role="option"
                  aria-selected={option.code === value}
                  disabled={option.disabled}
                  className={index === active ? "active" : undefined}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => choose(option)}
                >
                  <span className="catalog-select-option-name">
                    {option.name}
                    {option.caption && <small>{option.caption}</small>}
                  </span>
                  {option.price !== undefined && (
                    <span className="catalog-select-option-price">
                      {`${money(option.price)} ₽${option.unit ? `/${option.unit}` : ""}`}
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </div>,
        document.body,
      )}
    </div>
  );
}
