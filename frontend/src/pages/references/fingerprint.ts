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
 * Незаполненные поля приходят то пустой строкой, то отсутствуют вовсе, а
 * порядок ключей объекта ничего не значит. Числовую запись здесь не трогаем:
 * «0021» и «21» — разные значения, пока схема не сказала обратного.
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
  if (typeof value === "string") return value.trim();
  return value;
}

/**
 * Числовое поле: сервер возвращает его строкой, форма — числом.
 *
 * Без такого приведения круг «выгрузили — загрузили» помечал бы правкой
 * каждую запись.
 */
function normalizeNumber(value: unknown): unknown {
  if (typeof value !== "string") return normalize(value);
  const trimmed = value.trim();
  return NUMERIC.test(trimmed) ? Number(trimmed) : trimmed;
}

function normalizePayload(
  payload: Record<string, unknown> | undefined,
  numericKeys: ReadonlySet<string>,
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(payload ?? {})) {
    result[key] = numericKeys.has(key) ? normalizeNumber(value) : normalize(value);
  }
  return result;
}

/**
 * Отпечаток записи: сравнение с опубликованной версией без учёта формы
 * записи значений.
 *
 * `numericKeys` — числовые поля payload раздела по каталогу схем. Только их
 * текстовая запись считается равной числу; остальные поля (ИНН, инвентарный
 * номер) сравниваются посимвольно, иначе «0021» молча становилось бы «21» и
 * настоящая правка выглядела бы чистой.
 */
export function fingerprint(item: EconomicsReferenceItem, numericKeys: ReadonlySet<string>): string {
  return JSON.stringify(
    normalize({
      code: item.code,
      name: item.name,
      payload: normalizePayload(item.payload, numericKeys),
      is_active: item.is_active,
      valid_from: item.valid_from,
      valid_to: item.valid_to,
      source: item.source,
      comment: item.comment,
    }),
  );
}
