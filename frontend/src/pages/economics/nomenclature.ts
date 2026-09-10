/** Номенклатура блока: какие роли показывать, что подписывать под выбором. */
import type { MaterialOption, TechnicalPassport } from "../../types/blockEconomics";

export type NomenclatureRole = {
  role: string;
  label: string;
  /** Драйвер паспорта, из которого берётся количество; null — задаётся вручную. */
  driver: string | null;
  hint: string;
  /**
   * Код статьи затрат (`cost/model/materials.py`, `Role.cost_item_code`) —
   * стабильный машинный ключ для сопоставления со строкой сметы. `label`
   * для этого не годится: бэкендовый `line.role_label` — подпись для
   * предупреждений (нижний регистр, другие формулировки), а не идентификатор.
   */
  costItemCode: string;
};

/** Порядок ролей повторяет порядок сборки заряда: ВВ, боевик, сеть, инициирование. */
export const NOMENCLATURE_ROLES: NomenclatureRole[] = [
  {
    role: "EXPLOSIVE",
    label: "Основное ВВ",
    driver: "explosive_kg",
    hint: "масса заряда из паспорта",
    costItemCode: "MATERIAL_EXPLOSIVE",
  },
  {
    role: "BOOSTER",
    label: "Промежуточные детонаторы",
    driver: "intermediate_detonators",
    hint: "боевики из паспорта",
    costItemCode: "MATERIAL_BOOSTER",
  },
  {
    role: "NSI_DOWNHOLE",
    label: "Скважинные НСИ",
    driver: "downhole_nsi",
    hint: "по числу скважин",
    costItemCode: "MATERIAL_NSI_DOWNHOLE",
  },
  {
    role: "NSI_SURFACE",
    label: "Поверхностные НСИ",
    driver: "surface_nsi",
    hint: "из схемы монтажа",
    costItemCode: "MATERIAL_NSI_SURFACE",
  },
  {
    role: "NSI_START",
    label: "Стартовые НСИ",
    driver: "start_nsi",
    hint: "из схемы монтажа",
    costItemCode: "MATERIAL_NSI_START",
  },
  {
    role: "DETONATOR_ELECTRIC",
    label: "Электродетонаторы",
    driver: null,
    hint: "количество задаётся вручную",
    costItemCode: "MATERIAL_DETONATOR",
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

const QUANTITY = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 });

/**
 * Подпись под выбором: цена за единицу и количество на блок в единицах цены,
 * либо подсказка, откуда возьмётся количество. Количество приходит с сервера
 * тем же правилом, что и в строке сметы — иначе боевики показались бы
 * штуками при цене за килограмм.
 */
export function optionCaption(
  option: MaterialOption | undefined,
  role: NomenclatureRole,
  optionCount = 1,
): string {
  if (!option) return optionCount === 0 ? "в справочнике нет таких позиций" : role.hint;
  if (option.price_rub <= 0) return "нет цены в справочнике";
  const price = `${RUBLES.format(option.price_rub)} ₽ за ${option.unit}`;
  if (option.quantity === null) return price;
  const quantity = `${QUANTITY.format(option.quantity)} ${option.unit} на блок`;
  return option.quantity_label ? `${price} · ${quantity} (${option.quantity_label})` : `${price} · ${quantity}`;
}
