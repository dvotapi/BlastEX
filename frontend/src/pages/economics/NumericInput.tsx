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
  disabled,
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
  /**
   * Читателю без права правки поле показывается, но не принимает ввод — иначе
   * интерфейс врёт: комбобоксы рядом уже выключены по тому же признаку, а
   * числа молча правились и уходили в пересчёт.
   */
  disabled?: boolean;
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
      disabled={disabled}
      onChange={(event) => handleChange(event.target.value)}
      onBlur={() => {
        // Поле нельзя оставить пустым: возвращаем последнее принятое число.
        if (text.trim() === "" && !allowEmpty) setText(sent.current);
      }}
    />
  );
}
