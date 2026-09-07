/** Номенклатура блока: какие роли показывать, что подписывать под выбором. */
import type { MaterialOption, TechnicalPassport } from "../../types/blockEconomics";

export type NomenclatureRole = {
  role: string;
  label: string;
  /** Драйвер паспорта, из которого берётся количество; null — задаётся вручную. */
  driver: string | null;
  hint: string;
};

/** Порядок ролей повторяет порядок сборки заряда: ВВ, боевик, сеть, инициирование. */
export const NOMENCLATURE_ROLES: NomenclatureRole[] = [
  { role: "EXPLOSIVE", label: "Основное ВВ", driver: "explosive_kg", hint: "масса заряда из паспорта" },
  {
    role: "BOOSTER",
    label: "Промежуточные детонаторы",
    driver: "intermediate_detonators",
    hint: "боевики из паспорта",
  },
  { role: "NSI_DOWNHOLE", label: "Скважинные НСИ", driver: "downhole_nsi", hint: "по числу скважин" },
  { role: "NSI_SURFACE", label: "Поверхностные НСИ", driver: "surface_nsi", hint: "из схемы монтажа" },
  { role: "NSI_START", label: "Стартовые НСИ", driver: "start_nsi", hint: "из схемы монтажа" },
  {
    role: "DETONATOR_ELECTRIC",
    label: "Электродетонаторы",
    driver: null,
    hint: "количество задаётся вручную",
  },
];

/** Количество позиции в блоке по паспорту; для ручных ролей — null. */
export function roleQuantity(role: NomenclatureRole, passport: TechnicalPassport | null): number | null {
  if (!role.driver) return null;
  const raw = passport?.physical?.[role.driver];
  return raw === undefined ? 0 : Number(raw);
}

/**
 * Роль показывается, когда позиция в блоке есть. Стартовых устройств нет —
 * нечего и выбирать: лишний пустой список сметчик прочтёт как незаполненное место.
 */
export function isRoleVisible(role: NomenclatureRole, passport: TechnicalPassport | null): boolean {
  const quantity = roleQuantity(role, passport);
  return quantity === null || quantity > 0;
}

const RUBLES = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Подпись под выбором: цена за единицу либо подсказка, откуда возьмётся количество. */
export function optionCaption(option: MaterialOption | undefined, role: NomenclatureRole): string {
  if (!option) return role.hint;
  if (option.price_rub <= 0) return "нет цены в справочнике";
  return `${RUBLES.format(option.price_rub)} ₽${option.unit ? ` за ${unitLabel(option.unit)}` : ""}`;
}

const UNIT_LABELS: Record<string, string> = { KG: "кг", PIECE: "шт", M: "м", T: "т", L: "л" };

export function unitLabel(unit: string): string {
  return UNIT_LABELS[unit] ?? unit.toLowerCase();
}
