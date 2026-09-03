import type { EconomicsReferenceItem } from "../../types/economics";

/** Текстовая запись числа: «1», «-2.5», «0.10». */
const NUMERIC = /^-?\d+(\.\d+)?$/;

function isEmpty(value: unknown): boolean {
  if (value === null || value === undefined || value === "") return true;
  if (Array.isArray(value)) return value.length === 0;
  return typeof value === "object" && Object.keys(value as object).length === 0;
}

/**
 * Приведение значения к сравнимому виду — без знания полей раздела.
 *
 * Сервер возвращает числа справочников строками, форма отдаёт их числами, а
 * незаполненные поля приходят то пустой строкой, то отсутствуют вовсе. Без
 * такой нормализации круг «выгрузили — загрузили» помечал бы правкой каждую
 * запись.
 */
function normalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(normalize);
  if (value && typeof value === "object") {
    const result: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, unknown>).sort(([left], [right]) =>
      left.localeCompare(right),
    )) {
      const normalized = normalize(item);
      if (!isEmpty(normalized)) result[key] = normalized;
    }
    return result;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (NUMERIC.test(trimmed)) return Number(trimmed);
    return trimmed;
  }
  return value;
}

/** Отпечаток записи: сравнение с опубликованной версией без учёта формы записи значений. */
export function fingerprint(item: EconomicsReferenceItem): string {
  return JSON.stringify(
    normalize({
      code: item.code,
      name: item.name,
      payload: item.payload,
      is_active: item.is_active,
      valid_from: item.valid_from,
      valid_to: item.valid_to,
      source: item.source,
      comment: item.comment,
    }),
  );
}
