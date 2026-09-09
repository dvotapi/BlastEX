import type { ValueOrigin } from "../../types/blockEconomics";

/** Подписи и подсказки для бейджа происхождения величины. */
export const ORIGIN_LABELS: Record<Exclude<ValueOrigin, "">, { label: string; title: string }> = {
  PASSPORT: { label: "Паспорт", title: "Величина из технического паспорта" },
  CALC: { label: "Расчёт", title: "Посчитано моделью себестоимости" },
  REFERENCE: { label: "Справочник", title: "Из опубликованной ревизии справочников" },
  NORM: { label: "Норматив", title: "Норматив справочника, не изменялся" },
  MANUAL: { label: "Ручной", title: "Введено на вкладке" },
};
