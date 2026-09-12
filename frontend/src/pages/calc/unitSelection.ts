/**
 * Выбор производственного юнита в шапке листа «Расчёт». Юнит — фильтр списка
 * объектов, а не отдельный контекст расчёта: объект сам знает свой юнит
 * (`production_unit_code` записи справочника), лист хранит только последний
 * выбор, чтобы восстановить фильтр для объекта без юнита.
 *
 * Модуль чистый — ни запросов, ни React.
 */

export type UnitOption = { code: string; name: string };
export type ObjectOption = { id?: string; name: string; production_unit_code?: string | null };

/** Юнит объекта по имени; `""` — у объекта юнита нет или объект неизвестен. */
export function objectUnitCode(objects: ObjectOption[], objectName: string): string {
  return objects.find((item) => item.name === objectName)?.production_unit_code ?? "";
}

/**
 * Объекты для списка в шапке. Объекты без юнита видны при любом фильтре —
 * иначе их нельзя было бы выбрать вовсе. Текущий объект виден всегда: список
 * без выбранного значения `<select>` показал бы чужое имя.
 */
export function filterObjectsByUnit<T extends ObjectOption>(objects: T[], unitCode: string, currentObjectName: string): T[] {
  if (!unitCode) return objects;
  return objects.filter(
    (item) => !item.production_unit_code || item.production_unit_code === unitCode || item.name === currentObjectName,
  );
}

/** Код, которого нет среди действующих юнитов ревизии, сбрасывается: иначе
 * закрытый юнит спрятал бы объекты, а выбрать «все» было бы нечем. */
export function knownUnitCode(units: UnitOption[], code: string): string {
  return units.some((unit) => unit.code === code) ? code : "";
}

/**
 * Юнит для только что загруженного листа объекта. Юнит самого объекта важнее
 * всего. Для объекта без юнита: при переходе из шапки (`carried` — фильтр,
 * действовавший в момент выбора) фильтр не должен прыгать, поэтому остаётся
 * он; при открытии листа (`carried === null`) — последний сохранённый выбор.
 */
export function unitForLoadedSheet(
  objects: ObjectOption[],
  objectName: string,
  carried: string | null,
  stored: string,
): string {
  return objectUnitCode(objects, objectName) || (carried ?? stored);
}
