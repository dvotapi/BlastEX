/**
 * Русские подписи значений перечислений.
 *
 * Схема отдаёт коды (`DIRECT`, `PER_SHIFT`), а сметчику нужно слово. Это
 * оформление, а не знание о полях: неизвестный код показывается как есть,
 * поэтому новое значение в схеме не ломает форму.
 */
const ENUM_LABELS: Record<string, string> = {
  // Персонал
  DIRECT: "Прямой",
  INDIRECT: "Косвенный",
  rock_volume_m3: "Объём породы, м³",
  explosive_kg: "Масса ВВ, кг",
  drilling_m: "Бурение, п.м.",
  holes: "Скважины, шт",
  GROSS: "До НДФЛ",
  NET: "На руки",
  // Техника
  DRILL_RIG: "Буровой станок",
  SZM: "СЗМ",
  HAZMAT_TRUCK: "Транспорт ВМ",
  LIGHT_VEHICLE: "Лёгкий транспорт",
  TRACTOR: "Трактор",
  PER_SHIFT: "По сменам",
  MONTHLY_BUDGET: "Месячный бюджет",
  // Контрагенты
  CUSTOMER: "Заказчик",
  SUPPLIER: "Поставщик",
  SUBCONTRACTOR: "Субподрядчик",
  // Материалы
  BULK: "Бестарное ВВ",
  CARTRIDGE: "Патронированное ВВ",
  NSI: "Средства инициирования",
  NONE: "Без класса хранения",
  DIRECT_TO_SITE: "Напрямую на объект",
  FROM_WAREHOUSE: "Со склада ВМ",
  // Затраты юнита и рынок
  FACILITY: "Инфраструктура",
  INDIRECT_LABOR: "Косвенный персонал",
  INSURANCE: "Страхование",
  PPE: "СИЗ",
  OTHER: "Прочее",
  BLOCK: "На блок",
  M3: "На м³",
  TON: "На тонну",
  UNIT: "На юнит",
  ORGANIZATION: "На организацию",
};

export function enumLabel(value: string): string {
  return ENUM_LABELS[value] ?? value;
}

/**
 * Подписи ключей внутри свободных объектов (состав пакета работ, нормы
 * потребления). У таких элементов нет схемы, поэтому имя ключа — единственное,
 * что о них известно; неизвестный ключ показывается как есть.
 */
const KEY_LABELS: Record<string, string> = {
  operation_code: "Операция",
  optional: "Необязательная",
  material_code: "Материал",
  position_code: "Должность",
  headcount: "Численность",
  quantity: "Количество",
  unit: "Единица",
  rate: "Норма",
};

export function keyLabel(key: string): string {
  return KEY_LABELS[key] ?? key;
}
