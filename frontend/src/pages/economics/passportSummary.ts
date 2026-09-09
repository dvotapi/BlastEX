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
 * Четыре плашки полосы паспорта. Выход метров с одной скважины паспорт не
 * хранит — это погонаж на число скважин; без скважин показывать нечего:
 * прочерк, а не Infinity.
 */
export function passportMetrics(physical: Record<string, Numeric>): PassportMetric[] {
  const drilling = numberOf(physical, "drilling_m");
  const holes = numberOf(physical, "holes");
  const perHole = drilling !== null && holes !== null && holes > 0 ? drilling / holes : null;
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
  ];
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
