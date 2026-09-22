/**
 * Блок `kuzram` в настройках листа «Расчёт»: настройки модели подбора q и
 * фактические взрывы для подбора C(A). Модуль чистый — ни запросов, ни React.
 *
 * Умолчания и границы — в `kuzramContract.json`, копии констант
 * `simulation/fragmentation/cunningham.py` и схем `api/schemas/blast.py`:
 * совпадение проверяет `tests/test_kuzram_frontend_contract.py`. Формул модели
 * здесь нет — только чтение сохранённого, проверка ввода и подпись у кнопки.
 */
import contract from "./kuzramContract.json";
import { trimmed } from "./kuzramFormat";
import type { KuzRamFactInput, KuzRamSettings, RockFactorMethod, StrengthExponent } from "../../../types";

/** Строка фактического взрыва; `null` — ячейка ещё не заполнена. */
export type KuzRamFact = { crown_mm: number | null; q_kg_m3: number | null; oversize_pct: number | null };

/** Блок в настройках листа: настройки модели и фактические взрывы. */
export type KuzRamBlock = KuzRamSettings & { facts: KuzRamFact[] };

export type NumericSetting = keyof typeof contract.bounds;
export type FactField = keyof KuzRamFact;

export const KUZRAM_DEFAULTS: KuzRamSettings = {
  ...contract.defaults,
  rock_factor_method: contract.defaults.rock_factor_method as RockFactorMethod,
  strength_exponent: contract.defaults.strength_exponent as StrengthExponent,
};
export const ROCK_FACTOR_METHODS = contract.rock_factor_methods as RockFactorMethod[];
export const JOINT_CONDITIONS: number[] = contract.joint_conditions;
export const JOINT_ANGLES: number[] = contract.joint_angles;
export const STRENGTH_EXPONENTS = contract.strength_exponents as StrengthExponent[];
export const MAX_FACTS: number = contract.max_facts;
export const FACT_FIELDS: FactField[] = ["crown_mm", "q_kg_m3", "oversize_pct"];

/**
 * Выше этого W/d (ЛНС к диаметру скважины) окно предупреждает: Каннингем
 * (2005) рекомендует 25–35. Ниже 25 молчим — для крепких пород это обычная
 * сетка (габбро-диабаз: 20–23,5 на коронках 110–250 мм). Подбор q порог не
 * ограничивает. Решение владельца от 21.09.2026.
 */
export const BURDEN_TO_DIAMETER_WARN_ABOVE = 35;

/** Подписи числовых настроек — как в сообщениях сервера (`NUMERIC_BOUNDS`). */
export const NUMERIC_LABELS: Record<NumericSetting, string> = {
  rock_factor_manual: "Фактор породы A",
  rock_factor_correction: "Поправка C(A)",
  drill_deviation_m: "Отклонение бурения σ, м",
  uniformity_correction: "Поправка C(n)",
  q_max_kg_m3: "Верхняя граница перебора q, кг/м³",
};

/** Подписи ячеек факта: название для ошибок и полей ввода, единица для ошибок. */
export const FACT_LABELS: Record<FactField, { label: string; unit: string }> = {
  crown_mm: { label: "Коронка", unit: " мм" },
  q_kg_m3: { label: "Фактический q", unit: " кг/м³" },
  oversize_pct: { label: "Фактический негабарит", unit: " %" },
};

export function numericBounds(field: NumericSetting): { min: number; max: number } {
  const [min, max] = contract.bounds[field];
  return { min, max };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function numberSetting(value: unknown, field: NumericSetting): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return KUZRAM_DEFAULTS[field];
  const { min, max } = numericBounds(field);
  return Math.min(max, Math.max(min, value));
}

function oneOf<T>(value: unknown, options: readonly T[], fallback: T): T {
  return options.find((option) => option === value) ?? fallback;
}

function factCell(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function defaultKuzramBlock(): KuzRamBlock {
  return { ...KUZRAM_DEFAULTS, facts: [] };
}

/**
 * Сохранённый блок → блок листа. Блока нет (настройки до модели Kuz-Ram) —
 * умолчания; числа вне границ обрезаются, неизвестные варианты — умолчание.
 * Строки фактов хранятся и незаполненными, но не больше `MAX_FACTS`.
 */
export function readKuzramBlock(raw: unknown): KuzRamBlock {
  const source = isRecord(raw) ? raw : {};
  const facts = Array.isArray(source.facts) ? source.facts.slice(0, MAX_FACTS) : [];
  return {
    rock_factor_method: oneOf(source.rock_factor_method, ROCK_FACTOR_METHODS, KUZRAM_DEFAULTS.rock_factor_method),
    rock_factor_manual: numberSetting(source.rock_factor_manual, "rock_factor_manual"),
    joint_condition: oneOf(source.joint_condition, JOINT_CONDITIONS, KUZRAM_DEFAULTS.joint_condition),
    joint_angle: oneOf(source.joint_angle, JOINT_ANGLES, KUZRAM_DEFAULTS.joint_angle),
    rock_factor_correction: numberSetting(source.rock_factor_correction, "rock_factor_correction"),
    strength_exponent: oneOf(source.strength_exponent, STRENGTH_EXPONENTS, KUZRAM_DEFAULTS.strength_exponent),
    drill_deviation_m: numberSetting(source.drill_deviation_m, "drill_deviation_m"),
    uniformity_correction: numberSetting(source.uniformity_correction, "uniformity_correction"),
    q_max_kg_m3: numberSetting(source.q_max_kg_m3, "q_max_kg_m3"),
    facts: facts.map((row) => {
      const cells = isRecord(row) ? row : {};
      return {
        crown_mm: factCell(cells.crown_mm),
        q_kg_m3: factCell(cells.q_kg_m3),
        oversize_pct: factCell(cells.oversize_pct),
      };
    }),
  };
}

/**
 * Ровно девять настроек — то, что принимает API (`extra=forbid`). Блок с
 * фактами тоже подходит под тип `KuzRamSettings`, поэтому поля перечислены явно.
 */
export function kuzramSettingsOf(settings: KuzRamSettings): KuzRamSettings {
  return {
    rock_factor_method: settings.rock_factor_method,
    rock_factor_manual: settings.rock_factor_manual,
    joint_condition: settings.joint_condition,
    joint_angle: settings.joint_angle,
    rock_factor_correction: settings.rock_factor_correction,
    strength_exponent: settings.strength_exponent,
    drill_deviation_m: settings.drill_deviation_m,
    uniformity_correction: settings.uniformity_correction,
    q_max_kg_m3: settings.q_max_kg_m3,
  };
}

/** Копия блока для записи: строки фактов — новые объекты. */
export function copyKuzramBlock(block: KuzRamBlock): KuzRamBlock {
  return { ...kuzramSettingsOf(block), facts: block.facts.map((row) => ({ ...row })) };
}

export function sameSettings(a: KuzRamSettings, b: KuzRamSettings): boolean {
  const left = kuzramSettingsOf(a);
  const right = kuzramSettingsOf(b);
  return (Object.keys(left) as (keyof KuzRamSettings)[]).every((key) => left[key] === right[key]);
}

/** Подпись у кнопки окна: чем настройки отличаются от умолчаний («JF · C(A) 1,15»). */
export function settingsCaption(settings: KuzRamSettings): string {
  const defaults = KUZRAM_DEFAULTS;
  const parts: string[] = [];
  if (settings.rock_factor_method === "rmd10") parts.push("RMD 10");
  if (settings.rock_factor_method === "joint_factor") parts.push("JF");
  if (settings.rock_factor_method === "manual") parts.push(`A ${trimmed(settings.rock_factor_manual)}`);
  if (settings.rock_factor_correction !== defaults.rock_factor_correction) {
    parts.push(`C(A) ${trimmed(settings.rock_factor_correction)}`);
  }
  if (settings.strength_exponent !== defaults.strength_exponent) parts.push(settings.strength_exponent);
  if (settings.drill_deviation_m !== defaults.drill_deviation_m) parts.push(`σ ${trimmed(settings.drill_deviation_m)} м`);
  if (settings.uniformity_correction !== defaults.uniformity_correction) {
    parts.push(`C(n) ${trimmed(settings.uniformity_correction)}`);
  }
  if (settings.q_max_kg_m3 !== defaults.q_max_kg_m3) parts.push(`q до ${trimmed(settings.q_max_kg_m3)}`);
  return parts.join(" · ");
}

/** Число из поля ввода: запятая или точка; пусто и мусор — `null`. */
export function parseDecimal(text: string): number | null {
  const normalized = text.trim().replace(",", ".");
  if (!normalized) return null;
  const value = Number(normalized);
  return Number.isFinite(value) ? value : null;
}

/** Ошибка числовой настройки или `null`; тексты — как у сервера. */
export function settingError(field: NumericSetting, value: number | null): string | null {
  if (value === null) return "Введите число.";
  const { min, max } = numericBounds(field);
  if (value < min || value > max) return `${NUMERIC_LABELS[field]} — от ${trimmed(min)} до ${trimmed(max)}.`;
  return null;
}

/** Границы ячейки факта — как ограничения pydantic: `ge`/`gt` снизу, `le`/`lt` сверху. */
type FactBounds = { ge?: number; gt?: number; le?: number; lt?: number };

/** Ошибка ячейки факта по границам `KuzRamFactSchema`; пустая ячейка — не ошибка. */
export function factCellError(field: FactField, value: number | null): string | null {
  if (value === null) return null;
  const bounds: FactBounds = contract.fact_bounds[field];
  const lowOk = bounds.ge !== undefined ? value >= bounds.ge : value > (bounds.gt ?? -Infinity);
  const highOk = bounds.le !== undefined ? value <= bounds.le : value < (bounds.lt ?? Infinity);
  if (lowOk && highOk) return null;
  const { label, unit } = FACT_LABELS[field];
  // Коронка: «от 20 до 1000 мм» — как в сообщении сервера (`CrownMm`).
  if (bounds.ge !== undefined && bounds.le !== undefined) {
    return `${label} — от ${trimmed(bounds.ge)} до ${trimmed(bounds.le)}${unit}.`;
  }
  const high = bounds.le !== undefined ? `не больше ${trimmed(bounds.le)}` : `меньше ${trimmed(bounds.lt ?? Infinity)}`;
  return `${label} — больше ${trimmed(bounds.gt ?? 0)} и ${high}${unit}.`;
}

/** Строки, пригодные для подбора C(A): все три значения заполнены и в границах. */
export function completeFacts(facts: KuzRamFact[]): { index: number; fact: KuzRamFactInput }[] {
  const complete: { index: number; fact: KuzRamFactInput }[] = [];
  facts.forEach((row, index) => {
    const { crown_mm, q_kg_m3, oversize_pct } = row;
    if (crown_mm === null || q_kg_m3 === null || oversize_pct === null) return;
    if (FACT_FIELDS.some((field) => factCellError(field, row[field]) !== null)) return;
    complete.push({ index, fact: { crown_mm, q_kg_m3, oversize_pct } });
  });
  return complete;
}
