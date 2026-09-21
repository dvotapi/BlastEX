/**
 * Формат чисел окна «Модель Kuz-Ram» и таблицы вариантов листа. Только показ:
 * формул модели здесь нет, все величины приходят с сервера.
 */
import { ruNumber } from "../../../lib/format";
import contract from "./kuzramContract.json";

type Decimal = "," | ".";

/** Нижняя граница перебора q новой модели — меньшие значения модель не проверяет. */
export const Q_MIN_KG_M3: number = contract.q_min_kg_m3;

/** Перебор «до исправления» начинается с 0,30 (`Blast.py::optimize_blast_legacy`). */
export const LEGACY_Q_MIN_KG_M3 = 0.3;

function fixed(value: number, digits: number, decimal: Decimal): string {
  return decimal === "," ? ruNumber(value, digits) : value.toFixed(digits);
}

/** Число без лишних нулей и без разделителя тысяч: 1,127; 2; 0,5. */
export function trimmed(value: number, maxDigits = 3): string {
  return value.toLocaleString("ru-RU", { maximumFractionDigits: maxDigits, useGrouping: false });
}

/**
 * q с двумя знаками. На нижней границе перебора — «≤ 0,10»: порог выполнен
 * уже там, а меньшие q модель не проверяла.
 */
export function formatQ(q: number, decimal: Decimal = ",", floor = Q_MIN_KG_M3): string {
  const text = fixed(q, 2, decimal);
  return q <= floor + 1e-9 ? `≤ ${text}` : text;
}

/**
 * Негабарит с `digits` знаками. Если порог не достигнут, а округление дало
 * порог или меньше (на верхней границе q: 5,004 % → «5,00» при пороге 5 %),
 * показываем «> 5» — иначе цифра спорит со значком «!».
 */
export function formatOversize(
  pct: number,
  reached: boolean,
  thresholdPct: number,
  digits = 2,
  decimal: Decimal = ",",
): string {
  if (!reached && Number(pct.toFixed(digits)) <= thresholdPct) {
    return `> ${decimal === "," ? trimmed(thresholdPct) : String(thresholdPct)}`;
  }
  return fixed(pct, digits, decimal);
}

/** Разница q новой модели относительно «до исправления»: «−6 %», «+8 %», «0 %». */
export function qDeltaText(newQ: number, legacyQ: number): string {
  const delta = Math.round(((newQ - legacyQ) / legacyQ) * 100);
  if (delta === 0) return "0 %";
  return `${delta > 0 ? "+" : "−"}${Math.abs(delta)} %`;
}

/** Сетка a × b в метрах: «4,42 × 3,54». */
export function gridText(aM: number, bM: number): string {
  return `${ruNumber(aM, 2)} × ${ruNumber(bM, 2)}`;
}
