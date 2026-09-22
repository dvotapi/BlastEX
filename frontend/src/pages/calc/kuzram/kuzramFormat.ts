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

/** Перебор «до исправления» заканчивается на 1,50 (`Blast.py::optimize_blast_legacy`). */
export const LEGACY_Q_MAX_KG_M3 = 1.5;

/**
 * Заголовок значка «!» у q «до исправления»: там граница перебора
 * фиксирована и от окна настроек Kuz-Ram не зависит — совет поднять её
 * там (умолчание у `ThresholdFlag`) был бы неверным.
 */
export const LEGACY_THRESHOLD_TITLE =
  `Порог негабарита не достигнут: q на верхней границе прежнего перебора (${ruNumber(LEGACY_Q_MAX_KG_M3, 2)} кг/м³).`;

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

/** Чего на листе нет для расчёта вариантов («Рассчитать варианты» без этого недоступна). */
export type MissingForCalculation = { crowns: boolean; rock: boolean; explosive: boolean };

/**
 * Совет к пометке «варианты — по прежним настройкам модели» — один и тот же на
 * листе и в окне. Расчёт упал — ведём к сообщению об ошибке: причина бывает
 * любой (сеть, сервер, настройки), а сообщения сервера сами говорят, что менять.
 * Нечего считать — выбрать недостающее; иначе — пересчитать.
 */
export function outdatedHint(error: string, missing: MissingForCalculation): string {
  if (error) return "по текущим расчёт не прошёл — причина в сообщении об ошибке.";
  const items = [missing.crowns && "коронки", missing.rock && "породу", missing.explosive && "ВВ"].filter(Boolean);
  if (items.length) return `на листе нечего считать — выберите ${items.join(", ")} и нажмите «Рассчитать варианты».`;
  return "пересчитайте их кнопкой «Рассчитать варианты» на листе.";
}

/** Сетка a × b в метрах: «4,42 × 3,54». */
export function gridText(aM: number, bM: number): string {
  return `${ruNumber(aM, 2)} × ${ruNumber(bM, 2)}`;
}
