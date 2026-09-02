/**
 * Русская форма существительного по числу: 1 станок, 2 станка, 5 станков.
 * Интерфейс справочников считает записи, изменения и станки, поэтому форма
 * нужна везде, где число подставляется в текст.
 */
export function plural(count: number, forms: [string, string, string]): string {
  const absolute = Math.abs(Math.trunc(count)) % 100;
  const last = absolute % 10;
  if (absolute > 10 && absolute < 20) return forms[2];
  if (last > 1 && last < 5) return forms[1];
  if (last === 1) return forms[0];
  return forms[2];
}
