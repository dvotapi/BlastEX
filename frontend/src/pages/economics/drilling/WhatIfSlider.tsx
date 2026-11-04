/**
 * Бегунок пробного значения ручки цены метра («что если»).
 *
 * Тот же приём, что у `RigPlanShiftsSlider`: движение живёт в локальном
 * состоянии и уходит наружу один раз — по отпусканию указателя или после
 * короткой паузы при шагах клавиатурой (отпускание клавиши паузу не
 * обрывает), чтобы одно перетаскивание не давало десяток запросов. Диапазон —
 * ±30 % от значения справочника, сжатый границами `min`/`max` (у шкалы премии
 * их задают правила справочника: потолок выше нормы, расценка на потолке не
 * ниже расценки на норме). Значение ручки не пишется ни в черновик, ни в
 * справочники — это пробное число на время страницы.
 */
import { useEffect, useRef, useState } from "react";
import { amount } from "../format";

/** Пауза после последнего шага клавиатурой, после которой значение уходит наружу. */
export const WHAT_IF_SETTLE_MS = 250;
/** Ширина диапазона бегунка в долях от значения справочника. */
export const WHAT_IF_SPAN = 0.3;

/** Шаг бегунка: «круглое» число около 1/60 диапазона (1, 2, 5 × 10ⁿ). */
export function niceStep(range: number): number {
  if (!(range > 0)) return 1;
  const raw = range / 60;
  const power = Math.pow(10, Math.floor(Math.log10(raw)));
  const unit = raw / power;
  const factor = unit <= 1 ? 1 : unit <= 2 ? 2 : unit <= 5 ? 5 : 10;
  return factor * power;
}

/** Округление к шагу без «хвостов» двоичной арифметики. */
export function snap(value: number, step: number): number {
  const digits = Math.max(0, -Math.floor(Math.log10(step)) + 1);
  return Number((Math.round(value / step) * step).toFixed(digits));
}

/** Диапазон ±30 % от значения справочника, сжатый внешними границами. */
export function whatIfRange(base: number, min?: number, max?: number): { min: number; max: number; step: number } {
  const step = niceStep(base * WHAT_IF_SPAN * 2);
  let low = snap(base * (1 - WHAT_IF_SPAN), step);
  let high = snap(base * (1 + WHAT_IF_SPAN), step);
  if (low <= 0) low = step;
  if (min !== undefined) low = Math.max(low, min);
  if (max !== undefined) high = Math.min(high, max);
  if (high < low) high = low;
  return { min: low, max: high, step };
}

/** Эффект +10 % к ручке на цену метра с ФОТ: половина размаха между плечами −10 % и +10 %. */
export function effectText(deltaRubPerM: number): string {
  const half = deltaRubPerM / 2;
  if (Math.abs(half) < 0.005) return "+10 %: цену не меняет";
  return `+10 %: ${half > 0 ? "+" : "−"}${amount(Math.abs(half), 2)} ₽/м`;
}

export function formatKnobValue(value: number, unit: string): string {
  const digits = Math.abs(value) >= 100 ? 0 : Math.abs(value) >= 10 ? 1 : 2;
  const text = unit === "×" ? `×${amount(value, 2)}` : `${amount(value, digits)} ${unit}`;
  return text.trim();
}

export type WhatIfSliderProps = {
  code: string;
  label: string;
  unit: string;
  /** Значение справочника (или параметра) — база диапазона. */
  base: number;
  /** Пробное значение; null — значение справочника. */
  value: number | null;
  /** Внешние границы (правила справочника у шкалы премии). */
  min?: number;
  max?: number;
  /** Эффект ±10 % на цену метра с ФОТ, ₽/м; undefined — не считалось. */
  deltaRubPerM?: number | null;
  /** Ручка не действует в этом режиме (шкала премии при ставках). */
  inactive?: boolean;
  disabled?: boolean;
  /** Новое пробное значение либо null — вернуть значение справочника. */
  onChange: (value: number | null) => void;
};

export function WhatIfSlider({
  code,
  label,
  unit,
  base,
  value,
  min,
  max,
  deltaRubPerM,
  inactive,
  disabled,
  onChange,
}: WhatIfSliderProps) {
  const committed = value ?? base;
  const [pending, setPending] = useState<number | null>(null);
  const timer = useRef<number | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const holding = useRef(false);

  useEffect(() => {
    setPending(null);
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  }, [value, base]);

  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    },
    [],
  );

  function clearTimer() {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  }

  function commit(next: number) {
    clearTimer();
    if (next === committed) {
      setPending(null);
      return;
    }
    onChangeRef.current(next === base ? null : next);
  }

  function handleMove(raw: string) {
    const next = Number(raw);
    if (!Number.isFinite(next)) return;
    setPending(next);
    clearTimer();
    if (!holding.current) timer.current = window.setTimeout(() => commit(next), WHAT_IF_SETTLE_MS);
  }

  function hold() {
    holding.current = true;
    clearTimer();
  }

  function release() {
    holding.current = false;
    if (pending !== null) commit(pending);
  }

  function reset() {
    clearTimer();
    setPending(null);
    onChangeRef.current(null);
  }

  const range = whatIfRange(base, min, max);
  const shown = pending ?? committed;
  const sliderValue = Math.min(range.max, Math.max(range.min, shown));
  const changed = value !== null && value !== base;
  const effect = deltaRubPerM === undefined || deltaRubPerM === null ? null : effectText(deltaRubPerM);

  return (
    <div className={`what-if-knob${changed ? " is-changed" : ""}${inactive ? " is-inactive" : ""}`} data-knob={code}>
      <div className="what-if-knob-head">
        <span className="what-if-knob-label">{label}</span>
        {effect && <span className="what-if-knob-effect">{effect}</span>}
      </div>
      <div className="what-if-knob-row">
        <input
          type="range"
          min={range.min}
          max={range.max}
          step={range.step}
          value={sliderValue}
          disabled={disabled}
          aria-label={label}
          aria-valuetext={formatKnobValue(shown, unit)}
          onChange={(event) => handleMove(event.target.value)}
          onPointerDown={hold}
          onPointerUp={release}
          onPointerCancel={release}
          onBlur={release}
        />
        <output className="what-if-knob-value">{formatKnobValue(shown, unit)}</output>
      </div>
      <div className="what-if-knob-caption">
        <span>справочник {formatKnobValue(base, unit)}</span>
        {changed && (
          <button type="button" className="link-button" disabled={disabled} onClick={reset}>
            Вернуть
          </button>
        )}
      </div>
    </div>
  );
}
