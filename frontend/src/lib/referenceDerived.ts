/**
 * Вычисляемые подсказки формы справочников.
 *
 * Формулы продублированы из модели экономики (`cost/model/`) ради понятной
 * формы: сметчик видит, во что превращается введённый норматив. Источник
 * истины — расчёт на сервере, здесь только подсказка.
 */
import { formatNumber, parseNumber } from "../pages/references/schemaFields";

export type DerivedRecord = {
  code: string;
  name: string;
  payload: Record<string, unknown>;
  is_active: boolean;
};

export type DerivedContext = {
  sections: Record<string, DerivedRecord[]>;
};

export type DerivedHint = {
  label: string;
  value: string;
};

const DEFAULT_SHIFT_HOURS = 11;
const DEFAULT_VAT_RATE = 0.2;

function records(context: DerivedContext, section: string): DerivedRecord[] {
  return context.sections[section] ?? [];
}

function findByCode(context: DerivedContext, section: string, code: unknown): DerivedRecord | undefined {
  if (typeof code !== "string" || !code) return undefined;
  return records(context, section).find((record) => record.code === code);
}

function firstActive(context: DerivedContext, section: string): DerivedRecord | undefined {
  return records(context, section).find((record) => record.is_active) ?? records(context, section)[0];
}

/** Ставка НДС организации: нужна переключателю «ввести с НДС». */
export function vatRate(context: DerivedContext): number {
  const rates = firstActive(context, "organization_rates");
  const value = parseNumber(rates?.payload?.vat_rate);
  return value === null ? DEFAULT_VAT_RATE : value;
}

export function shiftHours(context: DerivedContext): number {
  const rates = firstActive(context, "organization_rates");
  const value = parseNumber(rates?.payload?.shift_hours);
  return value === null || value <= 0 ? DEFAULT_SHIFT_HOURS : value;
}

function positionHints(
  code: string,
  payload: Record<string, unknown>,
  context: DerivedContext,
): DerivedHint[] {
  const shiftsPerMonth = parseNumber(payload.norm_shifts_per_month);
  const operationsPerMonth = parseNumber(payload.norm_operations_per_month);
  if (!operationsPerMonth) return [];

  // Оклад хранится в «Ставках персонала»: должность задаёт нормативы, ставка —
  // деньги. Для подсказки берём ставку без уточнения по условию бурения.
  const rate = records(context, "labor_rates").find(
    (item) => item.payload.position_code === code && !item.payload.condition_code,
  );
  const monthly = parseNumber(rate?.payload?.fixed_monthly_rub);

  const parts: string[] = [];
  if (monthly !== null) parts.push(`${formatNumber(monthly / operationsPerMonth)} ₽`);
  if (shiftsPerMonth !== null) parts.push(`${formatNumber(shiftsPerMonth / operationsPerMonth)} смены`);
  if (!parts.length) return [];
  return [{ label: "На один взрыв по нормативу", value: parts.join(" · ") }];
}

function drillingConditionHints(
  payload: Record<string, unknown>,
  context: DerivedContext,
): DerivedHint[] {
  const techSpeed = parseNumber(payload.tech_speed_m_per_h);
  if (techSpeed === null) return [];
  const unproductive = parseNumber(payload.unproductive_h_per_shift) ?? 0;
  const productiveHours = Math.max(shiftHours(context) - unproductive, 0);
  const perShift = techSpeed * productiveHours;

  const rig = findByCode(context, "equipment_types", payload.equipment_type_code);
  const shiftsPerMonth = parseNumber(rig?.payload?.norm_shifts_per_month);

  const parts = [`${formatNumber(perShift)} м/смену`];
  if (shiftsPerMonth !== null) parts.push(`${formatNumber(perShift * shiftsPerMonth)} м/мес`);
  return [{ label: "Коммерческая скорость", value: parts.join(" · ") }];
}

export function derivedHints(
  section: string,
  code: string,
  payload: Record<string, unknown>,
  context: DerivedContext,
): DerivedHint[] {
  if (section === "positions") return positionHints(code, payload, context);
  if (section === "drilling_conditions") return drillingConditionHints(payload, context);
  return [];
}
