/**
 * Бегунок плановых смен станка в месяц.
 *
 * Постоянные затраты станка (амортизация, страховка, ТОиР и запчасти по
 * возрасту) модель делит на плановые смены месяца, поэтому загрузка станка
 * прямо меняет цену метра: больше смен — дешевле метр. Бегунок нужен, чтобы
 * эту зависимость было видно движением, а не вводом чисел.
 *
 * Значение — `rig_plan_shifts` черновика: пусто — норматив типа станка из
 * справочника (`defaults.parameters.rig_plan_shifts`). Пересчёт блока идёт по
 * черновику с задержкой, но черновик не должен меняться на каждый пиксель:
 * движение держится в локальном состоянии и уходит наружу один раз — по
 * отпусканию ползунка, а при шагах клавиатурой — после короткой паузы
 * (отпускание клавиши паузу не обрывает, иначе каждый шаг — отдельный патч).
 */
import { useEffect, useRef, useState } from "react";
import { plural } from "../../../lib/plural";
import type { Numeric } from "../../../types/blockEconomics";
import { money } from "../format";

export const RIG_PLAN_SHIFTS_MIN = 10;
export const RIG_PLAN_SHIFTS_MAX = 60;
/** Пауза после последнего шага клавиатурой, после которой значение уходит в черновик. */
export const RIG_PLAN_SHIFTS_SETTLE_MS = 250;

const SHIFT_FORMS: [string, string, string] = ["смена", "смены", "смен"];

/** Число параметра; пусто, нечисло и 0 («считать по нормативу») — null. */
export function shiftsNumber(value: Numeric | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export type RigPlanShiftsSliderProps = {
  /** `rig_plan_shifts` черновика; null — норматив. */
  value: Numeric | null;
  /** Норматив типа станка (`defaults.parameters.rig_plan_shifts`). */
  norm: Numeric | null;
  /** Стоимость 1 п.м. из текущего расчёта — эффект загрузки виден рядом. */
  rubPerM?: Numeric;
  /** Пересчёт по новому черновику ещё не пришёл: показанная цена — прежняя. */
  rubPerMStale?: boolean;
  disabled?: boolean;
  /** Новое значение смен строкой либо null — сброс к нормативу. */
  onChange: (value: string | null) => void;
};

export function RigPlanShiftsSlider({ value, norm, rubPerM, rubPerMStale, disabled, onChange }: RigPlanShiftsSliderProps) {
  const normNumber = shiftsNumber(norm);
  const committed = shiftsNumber(value) ?? normNumber;
  // Движение ползунка до того, как значение ушло в черновик.
  const [pending, setPending] = useState<number | null>(null);
  const timer = useRef<number | null>(null);
  // Отложенная отправка зовёт обработчик того рендера, в котором сработает,
  // а не того, где начался шаг: иначе патч уйдёт в черновик, активный 250 мс назад.
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  // Черновик принял значение (или сменился снаружи) — показываем его, а
  // незавершённый шаг к прежнему черновику не отправляем.
  useEffect(() => {
    setPending(null);
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  }, [value, norm]);

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
    onChangeRef.current(String(next));
  }

  function handleMove(raw: string) {
    const next = Number(raw);
    if (!Number.isFinite(next)) return;
    setPending(next);
    clearTimer();
    timer.current = window.setTimeout(() => commit(next), RIG_PLAN_SHIFTS_SETTLE_MS);
  }

  function flush() {
    if (pending !== null) commit(pending);
  }

  function reset() {
    clearTimer();
    setPending(null);
    onChangeRef.current(null);
  }

  const shown = pending ?? committed;
  const sliderValue = Math.min(RIG_PLAN_SHIFTS_MAX, Math.max(RIG_PLAN_SHIFTS_MIN, shown ?? RIG_PLAN_SHIFTS_MIN));
  const atNorm = shiftsNumber(value) === null || (normNumber !== null && shiftsNumber(value) === normNumber);
  const shownText = shown === null ? "—" : `${shown} ${plural(shown, SHIFT_FORMS)}`;
  const normText = normNumber === null ? "норматив не задан" : `норматив ${normNumber}`;

  return (
    <div className="rig-shifts">
      <div className="rig-shifts-row">
        <input
          type="range"
          min={RIG_PLAN_SHIFTS_MIN}
          max={RIG_PLAN_SHIFTS_MAX}
          step={1}
          value={sliderValue}
          disabled={disabled}
          aria-label="Плановые смены станка в месяц"
          aria-valuetext={shownText}
          onChange={(event) => handleMove(event.target.value)}
          onPointerUp={flush}
          onBlur={flush}
        />
        <output className="rig-shifts-value">{shownText}</output>
      </div>
      <div className="rig-shifts-caption">
        <span>{normText}</span>
        {normNumber !== null && (
          <button type="button" className="link-button" disabled={disabled || atNorm} onClick={reset}>
            Сбросить к нормативу
          </button>
        )}
        {rubPerM !== undefined && (
          <span className={rubPerMStale ? "rig-shifts-effect is-stale" : "rig-shifts-effect"}>
            Стоимость 1 п.м.: <b>{money(Number(rubPerM))} ₽/м</b>
            {rubPerMStale && <span className="rig-shifts-stale"> считается…</span>}
          </span>
        )}
      </div>
    </div>
  );
}
