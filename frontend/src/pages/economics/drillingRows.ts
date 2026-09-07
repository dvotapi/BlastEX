/**
 * Разложение стоимости метра бурения из результата расчёта.
 *
 * Модель уже пишет скорость, смены и цену метра в натуральные величины, а
 * статьи бурения — в строки затрат. Экран собирает их, а не считает заново:
 * одна цифра в двух местах не разъедется.
 */
import type { BlockCostLine, BlockEconomics } from "../../types/blockEconomics";

export const DRILLING_OPERATION = "PRODUCTION_DRILLING";

export type BreakdownRow = { label: string; value: number; unit: string; source: string };

export type DrillingBreakdown = {
  /** Откуда взята норма: «drilling_conditions.COND_GRANITE (станок + порода)». */
  conditionSource: string;
  norms: BreakdownRow[];
  perMetre: { variable: number; fixed: number; total: number };
  lines: BlockCostLine[];
  drillingM: number;
};

const NORM_ROWS: Array<{ key: string; label: string; unit: string }> = [
  { key: "drilling_tech_speed_m_per_h", label: "Техническая скорость", unit: "м/ч" },
  { key: "v_commercial_m_per_shift", label: "Коммерческая скорость", unit: "м/см" },
  { key: "rig_shifts", label: "Смены станка на блок", unit: "см" },
  { key: "rig_maintenance_shifts", label: "Смены ТОиР", unit: "см" },
  { key: "rig_plan_shifts", label: "Плановые смены в месяц", unit: "см" },
  { key: "rig_plan_metres", label: "Плановый погонаж в месяц", unit: "м" },
  { key: "drilling_bit_pcs", label: "Коронки", unit: "шт" },
  { key: "drilling_hammer_pcs", label: "ППУ", unit: "шт" },
  { key: "drilling_rods_pcs", label: "Штанги и переводники", unit: "шт" },
  { key: "drilling_casing_m", label: "Обсадка", unit: "м" },
  { key: "drilling_fuel_l", label: "ДТ на бурение", unit: "л" },
];

const number = (raw: string | number | undefined) => (raw === undefined ? 0 : Number(raw));

/**
 * Null — бурения в расчёте нет: пакет без бурения, нулевой погонаж или
 * ненайденная норма. Субподряд — тоже null: метр там куплен по ставке, а не
 * разложен на смены и оснастку.
 */
export function drillingBreakdown(economics: BlockEconomics): DrillingBreakdown | null {
  const values = economics.natural.values;
  const drillingM = number(values.drilling_m);
  const speed = number(values.v_commercial_m_per_shift);
  if (drillingM <= 0 || speed <= 0) return null;

  const norms = NORM_ROWS.filter((row) => values[row.key] !== undefined && number(values[row.key]) > 0).map(
    (row) => ({
      label: row.label,
      value: number(values[row.key]),
      unit: row.unit,
      source: economics.natural.lineage[row.key] ?? "",
    }),
  );
  return {
    conditionSource: economics.natural.lineage.drilling_condition ?? "",
    norms,
    perMetre: {
      variable: number(values.drilling_variable_rub_per_m),
      fixed: number(values.drilling_fixed_rub_per_m),
      total: number(values.drilling_rub_per_m),
    },
    lines: economics.lines.filter((line) => line.operation_code === DRILLING_OPERATION),
    drillingM,
  };
}
