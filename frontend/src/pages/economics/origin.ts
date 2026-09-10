import type { CrewMemberInput, ValueOrigin } from "../../types/blockEconomics";

/** Подписи и подсказки для бейджа происхождения величины. */
export const ORIGIN_LABELS: Record<Exclude<ValueOrigin, "">, { label: string; title: string }> = {
  PASSPORT: { label: "Паспорт", title: "Величина из технического паспорта" },
  CALC: { label: "Расчёт", title: "Посчитано моделью себестоимости" },
  REFERENCE: { label: "Справочник", title: "Из опубликованной ревизии справочников" },
  NORM: { label: "Норматив", title: "Норматив справочника, не изменялся" },
  MANUAL: { label: "Ручной", title: "Введено на вкладке" },
};

/**
 * Происхождение записи бригады: «Норматив», пока запись совпадает с шаблоном
 * пакета (та же должность, та же численность, смены не заданы вручную) —
 * «Ручной», как только сметчик поправил любое из этих полей.
 */
export function crewOrigin(member: CrewMemberInput, template: CrewMemberInput | undefined): ValueOrigin {
  if (!template) return "MANUAL";
  if (template.position_code !== member.position_code) return "MANUAL";
  if (Number(template.headcount) !== Number(member.headcount)) return "MANUAL";
  if (member.shifts_per_block !== null) return "MANUAL";
  return "NORM";
}
