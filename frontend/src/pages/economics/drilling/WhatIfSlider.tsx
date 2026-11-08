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

/**
 * Диапазон ±30 % от значения справочника, сжатый внешними границами. Ручка может
 * задать свой шаг и размах (`options`): сумма трала на блок двигается по 20 000 ₽
 * в пределах от шага до двойной суммы.
 */
export function whatIfRange(
  base: number,
  min?: number,
  max?: number,
  options: { step?: number | null; span?: number | null } = {},
): { min: number; max: number; step: number } {
  const span = options.span && options.span > 0 ? options.span : WHAT_IF_SPAN;
  const step = options.step && options.step > 0 ? options.step : niceStep(base * span * 2);
  let low = snap(base * (1 - span), step);
  let high = snap(base * (1 + span), step);
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
  /** Эффект самой сильной ручки списка, ₽/м (половина размаха): масштаб полоски. */
  barScale?: number;
  /** Свой шаг и размах бегунка (доля от значения в каждую сторону). */
  step?: number | null;
  span?: number | null;
  /** Подпись под названием: что ещё двигает ручка (темп машиниста у скорости). */
  sub?: string;
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
  barScale,
  sub,
  step,
  span,
  onChange,
}: WhatIfSliderProps) {
  const committed = value ?? base;
  const [pending, setPending] = useState<number | null>(null);
  const timer = useRef<number | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const holding = useRef(false);

  // Новое пробное значение или база снаружи — недосказанное движение
  // снимается. Только при смене, не на монтировании: бегунки появляются с
  // ответом сервера, и движение до выполнения эффектов монтирования иначе
  // стиралось бы вместе с таймером.
  const external = useRef({ value, base });
  useEffect(() => {
    if (external.current.value === value && external.current.base === base) return;
    external.current = { value, base };
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

  const range = whatIfRange(base, min, max, { step, span });
  const shown = pending ?? committed;
  const sliderValue = Math.min(range.max, Math.max(range.min, shown));
  const changed = value !== null && value !== base;
  const effect = deltaRubPerM === undefined || deltaRubPerM === null ? null : effectText(deltaRubPerM);

  return (
    <div
      className={`what-if-knob what-if-row${changed ? " is-changed" : ""}${inactive ? " is-inactive" : ""}`}
      data-knob={code}
      title={`справочник ${formatKnobValue(base, unit)}`}
    >
      <span className="what-if-knob-label">
        {label}
        {sub && <small className="what-if-knob-sub">{sub}</small>}
      </span>
      <EffectCell effect={effect} deltaRubPerM={deltaRubPerM} barScale={barScale} />
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
      {changed ? (
        <button type="button" className="link-button what-if-knob-reset" disabled={disabled} onClick={reset}>
          Вернуть
        </button>
      ) : (
        <span className="what-if-knob-reset" aria-hidden="true" />
      )}
    </div>
  );
}

/**
 * Ячейка эффекта: текст «+10 %: …» и под ним полоска от середины — вправо цена
 * растёт, влево падает; длина полосы — доля от самой сильной ручки списка.
 */
export function EffectCell({
  effect,
  deltaRubPerM,
  barScale,
}: {
  effect: string | null;
  deltaRubPerM?: number | null;
  barScale?: number;
}) {
  const half = deltaRubPerM === undefined || deltaRubPerM === null ? 0 : deltaRubPerM / 2;
  const share = barScale && barScale > 0 ? Math.min(1, Math.abs(half) / barScale) : 0;
  return (
    <span className="what-if-knob-effect">
      {effect}
      {effect && barScale ? (
        <span className="what-if-bar" aria-hidden="true">
          <i
            className={half > 0 ? "is-up" : "is-down"}
            style={{ width: `${share * 50}%`, left: half > 0 ? "50%" : `${50 - share * 50}%` }}
          />
        </span>
      ) : null}
    </span>
  );
}
