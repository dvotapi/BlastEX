import { useEffect, useRef, useState } from "react";
import type { Numeric } from "../../types/blockEconomics";

function toText(value: Numeric | null | undefined): string {
  return value === null || value === undefined || value === "" ? "" : String(value);
}

/**
 * Числовое поле параметров модели.
 *
 * Наружу отдаётся только разобранное число: пустое или недописанное значение
 * остаётся в поле, но не уходит в запрос — иначе пересчёт падает с 422, стоит
 * пользователю очистить поле перед вводом нового числа.
 */
export function NumericInput({
  value,
  onChange,
  allowEmpty = false,
  min,
  max,
  step,
  placeholder,
  ariaLabel,
}: {
  value: Numeric | null;
  onChange: (value: string | null) => void;
  /** Пустое значение осмысленно (норматив по умолчанию) и отправляется как null. */
  allowEmpty?: boolean;
  min?: number;
  max?: number;
  step?: number;
  placeholder?: string;
  ariaLabel?: string;
}) {
  const [text, setText] = useState(() => toText(value));
  const sent = useRef(toText(value));

  useEffect(() => {
    const incoming = toText(value);
    // Значение пришло снаружи (загрузка параметров по умолчанию) — показать его.
    if (incoming !== sent.current) {
      sent.current = incoming;
      setText(incoming);
    }
  }, [value]);

  function handleChange(raw: string) {
    setText(raw);
    if (raw.trim() === "") {
      if (allowEmpty) {
        sent.current = "";
        onChange(null);
      }
      return;
    }
    if (!Number.isFinite(Number(raw))) return;
    sent.current = raw;
    onChange(raw);
  }

  return (
    <input
      type="number"
      inputMode="decimal"
      value={text}
      min={min}
      max={max}
      step={step}
      placeholder={placeholder}
      aria-label={ariaLabel}
      onChange={(event) => handleChange(event.target.value)}
      onBlur={() => {
        // Поле нельзя оставить пустым: возвращаем последнее принятое число.
        if (text.trim() === "" && !allowEmpty) setText(sent.current);
      }}
    />
  );
}
