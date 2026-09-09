import { amount } from "./format";
import type { Numeric } from "../../types/blockEconomics";

/**
 * Что из паспорта видно на вкладке «Экономика блока»: четыре плашки над
 * сметой и полная таблица под раскрывашкой. Геометрию посчитал технический
 * паспорт, здесь её только показывают.
 */

/** Показатель плашки: подпись, значение русской записью, единица. */
export type PassportMetric = { key: string; label: string; value: string; unit: string };

/** Строка полной таблицы: то же плюс источник величины в паспорте. */
export type PassportRow = PassportMetric & { source: string };

/** Драйверы паспорта в порядке чтения: ключ `physical`, подпись, единица. */
const GEOMETRY_ROWS: [string, string, string][] = [
  ["rock_volume_m3", "Объём блока", "м³"],
  ["drilling_m", "Погонаж бурения", "п.м."],
  ["holes", "Скважины", "шт"],
  ["explosive_kg", "Масса ВВ", "кг"],
  ["downhole_nsi", "Скважинные НСИ", "шт"],
  ["surface_nsi", "Поверхностные НСИ", "шт"],
];

const NO_VALUE = "—";
const TECHNICAL_SOURCE = "технический расчёт";

/** Величина паспорта числом; пусто, пробелы или не число — null, не NaN. */
function numberOf(physical: Record<string, Numeric>, key: string): number | null {
  const raw = physical[key];
  if (raw === undefined || raw === null || (typeof raw === "string" && raw.trim() === "")) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

const shown = (value: number | null) => (value === null ? NO_VALUE : amount(value));

/** Строка `GEOMETRY_ROWS` по ключу драйвера — плашка не повторяет её подпись и единицу своими словами. */
const rowByKey = (key: string) => GEOMETRY_ROWS.find(([rowKey]) => rowKey === key)!;

/** Плашка из строки `GEOMETRY_ROWS`: подпись и единица — оттуда, значение — посчитанное. */
function metricFromRow(key: string, value: number | null): PassportMetric {
  const [, label, unit] = rowByKey(key);
  return { key, label, unit, value: shown(value) };
}

/**
 * Пять плашек полосы паспорта. Выход метров с одной скважины и средний
 * расход ВВ паспорт не хранит — это погонаж на число скважин и масса ВВ на
 * погонаж соответственно; без знаменателя показывать нечего: прочерк, а не
 * Infinity.
 */
export function passportMetrics(physical: Record<string, Numeric>): PassportMetric[] {
  const drilling = numberOf(physical, "drilling_m");
  const holes = numberOf(physical, "holes");
  const explosive = numberOf(physical, "explosive_kg");
  const perHole = drilling !== null && holes !== null && holes > 0 ? drilling / holes : null;
  const explosiveRate = drilling !== null && explosive !== null && drilling > 0 ? explosive / drilling : null;
  return [
    metricFromRow("rock_volume_m3", numberOf(physical, "rock_volume_m3")),
    metricFromRow("drilling_m", drilling),
    metricFromRow("holes", holes),
    {
      key: "meters_per_hole",
      label: "С одной скважины",
      value: perHole === null ? NO_VALUE : amount(perHole, 1),
      unit: "м",
    },
    {
      key: "explosive_rate",
      label: "Средний расход ВВ",
      value: explosiveRate === null ? NO_VALUE : amount(explosiveRate, 1),
      unit: "кг/м",
    },
  ];
}

/**
 * Подпись даты паспорта для полосы шапки: «Паспорт от 5 сентября 2026 г.».
 * Дата — не число паспорта (`physical`), а поле `TechnicalPassport.created_at`,
 * поэтому подпись живёт отдельной функцией, а не шестой плашкой
 * `passportMetrics`: у плашек общая форма «значение + единица», у даты её нет.
 */
export function passportCreatedAtLabel(createdAt: string): string {
  const date = new Date(createdAt);
  const formatted = date.toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
  return `Паспорт от ${formatted}`;
}

/** Полная таблица паспорта: только те величины, которые паспорт посчитал. */
export function passportRows(
  physical: Record<string, Numeric>,
  lineage: Record<string, string>,
): PassportRow[] {
  return GEOMETRY_ROWS.filter(([key]) => physical[key] !== undefined).map(([key, label, unit]) => ({
    key,
    label,
    unit,
    value: shown(numberOf(physical, key)),
    source: lineage[key] ?? TECHNICAL_SOURCE,
  }));
}
