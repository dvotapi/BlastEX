import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { money } from "../format";

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

/**
 * Свой комбобокс со справочником в строке сметы: кнопка, показывающая
 * выбранное имя, и поповер с полем поиска. Не модальная палитра на весь
 * экран (в отличие от `CommandPalette`) — раскрывается прямо под кнопкой и
 * закрывается кликом вне себя.
 */
export function CatalogSelect({
  id,
  label,
  value,
  options,
  placeholder = "не выбрано",
  onChange,
  disabled,
}: {
  id: string;
  label: string;
  value: string;
  options: CatalogOption[];
  placeholder?: string;
  onChange: (code: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

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
    inputRef.current?.focus();
  }, [open]);

  // Клик вне комбобокса закрывает поповер — обычный паттерн выпадающих
  // списков проекта (см. `HoleContextMenu`), здесь на `mousedown`, а не на
  // `click`, чтобы поповер не подхватывал клик, которым его же открыли.
  useEffect(() => {
    if (!open) return undefined;
    function onMouseDown(e: MouseEvent) {
      if (containerRef.current?.contains(e.target as Node)) return;
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
        className="catalog-select-button"
        onClick={() => setOpen((o) => !o)}
        onKeyDown={onButtonKeyDown}
      >
        <span>{selected?.name ?? placeholder}</span>
      </button>
      {open && (
        <div className="catalog-select-popover" onKeyDown={onPopoverKeyDown}>
          <input
            ref={inputRef}
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
        </div>
      )}
    </div>
  );
}
