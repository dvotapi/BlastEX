import type { PublicDelta, PublicDeltaEntry, PublicLinkRequest } from "../../types/economics";
import type { DraftSections } from "./importDraft";
import { plural } from "../../lib/plural";

/**
 * Записи разницы с журналом project1 применяются в черновик по коду: запись с
 * тем же кодом заменяется целиком на `entry.item` с сохранением `row_id`, а
 * запись с новым кодом добавляется в конец раздела (раздел создаётся, если его
 * в черновике не было). Функция не знает полей payload — сервер уже прислал
 * готовую запись справочника.
 *
 * `kind` на решение не влияет: смысл имеет только наличие кода в черновике —
 * `new` для кода, который пользователь успел завести руками, честнее применить
 * как замену, чем создать дубль кода и уронить публикацию.
 */
export function applyDeltaEntries(
  draft: DraftSections,
  entries: PublicDeltaEntry[],
  makeRowId: () => string,
): { draft: DraftSections; applied: number } {
  if (!entries.length) return { draft, applied: 0 };
  const next: DraftSections = { ...draft };
  let applied = 0;
  for (const entry of entries) {
    const rows = next[entry.section] ?? [];
    const index = rows.findIndex((row) => row.code === entry.code);
    if (index < 0) {
      next[entry.section] = [...rows, { ...entry.item, row_id: makeRowId() }];
    } else {
      next[entry.section] = rows.map((row, position) =>
        position === index ? { ...entry.item, row_id: row.row_id } : row,
      );
    }
    applied += 1;
  }
  return { draft: next, applied };
}

/**
 * Подпись плашки: «Из project1: 3 новые, 1 изменённая». Нулевые счётчики
 * опускаются — «0 деактивированных» ничего не сообщает, а читать мешает.
 * Если ноль везде, подписи нет вовсе: расхождений с журналом не осталось.
 */
export function deltaSummary(counts: PublicDelta["counts"]): string {
  const parts: string[] = [];
  if (counts.new) parts.push(`${counts.new} ${plural(counts.new, ["новая", "новые", "новых"])}`);
  if (counts.changed)
    parts.push(`${counts.changed} ${plural(counts.changed, ["изменённая", "изменённые", "изменённых"])}`);
  if (counts.deactivated)
    parts.push(
      `${counts.deactivated} ${plural(counts.deactivated, ["деактивированная", "деактивированные", "деактивированных"])}`,
    );
  if (!parts.length) return "";
  return `Из project1: ${parts.join(", ")}`;
}

/**
 * Значение поля в тексте изменения. JSON пользователю не показывается:
 * список и объект называются по-русски с числом элементов, логическое —
 * «да»/«нет», пустое — прочерком.
 */
export function fieldValueText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "да" : "нет";
  if (Array.isArray(value)) return `список (${value.length})`;
  if (typeof value === "object") return "объект";
  return String(value);
}

/**
 * Связь, выбранная в черновике и ещё не опубликованная. Хранится по `row_id`
 * записи, а не по коду: код правится в форме, и связь должна идти за записью,
 * а не оставаться на прежнем коде.
 */
export type PendingLink = {
  row_id: string;
  section: string;
  public_table: string;
  public_id: number;
};

/**
 * Ожидающие связи в виде запроса к серверу: код берётся из черновика на момент
 * отправки. Связь без записи в черновике (запись удалили или раздел заменили
 * файлом) отбрасывается — связывать нечего; запись без кода тоже: пустой код
 * сервер не примет, а пользователь ещё её заполняет.
 */
export function resolvePendingLinks(
  draft: DraftSections,
  pending: PendingLink[],
): PublicLinkRequest[] {
  const resolved: PublicLinkRequest[] = [];
  for (const link of pending) {
    const row = (draft[link.section] ?? []).find((item) => item.row_id === link.row_id);
    if (!row || !row.code) continue;
    resolved.push({
      section: link.section,
      code: row.code,
      public_table: link.public_table,
      public_id: link.public_id,
    });
  }
  return resolved;
}

/**
 * Добавляет связи к уже выбранным, снимая прежние по обоим ключам: у строки
 * журнала и у записи справочника связь ровно одна, иначе публикация упёрлась
 * бы в уникальность `public_links`.
 */
export function mergePendingLinks(current: PendingLink[], added: PendingLink[]): PendingLink[] {
  if (!added.length) return current;
  const rows = new Set(added.map((link) => `${link.public_table}#${link.public_id}`));
  const records = new Set(added.map((link) => `${link.section}::${link.row_id}`));
  const kept = current.filter(
    (link) =>
      !rows.has(`${link.public_table}#${link.public_id}`) &&
      !records.has(`${link.section}::${link.row_id}`),
  );
  return [...kept, ...added];
}

/**
 * Строка опубликованной ревизии: код, под которым она загружена в черновик.
 * Нужна, чтобы отличить переименование записи от её исчезновения — `row_id`
 * у строки ревизии стабилен, а код правится в форме.
 */
export type PublishedRow = {
  row_id: string;
  section: string;
  code: string;
};

/** Строки черновика, каким он загружен из опубликованной ревизии. */
export function publishedRows(draft: DraftSections): PublishedRow[] {
  return Object.entries(draft).flatMap(([section, rows]) =>
    rows.map((row) => ({ row_id: row.row_id, section, code: row.code })),
  );
}

/**
 * Связи, которые надо перенести на новый код переименованных записей.
 *
 * Сохранённая связь хранится по коду, а код правится в форме. Без переноса
 * публикация считала бы запись со старым кодом исчезнувшей: у разделов с
 * уникальным ключом переименованная запись выглядела бы несвязанной и не
 * прошла бы проверку, а у объектов её строку в журнале погасили бы и завели
 * дубль под новым кодом.
 *
 * Строка ревизии, которой в черновике уже нет (запись удалили или раздел
 * заменили файлом), связь не переносит — она действительно исчезла.
 */
export function renamedLinks(
  stored: PublicLinkRequest[],
  published: PublishedRow[],
  draft: DraftSections,
): PendingLink[] {
  if (!stored.length) return [];
  const byCode = new Map(stored.map((link) => [`${link.section}::${link.code}`, link]));
  const renamed: PendingLink[] = [];
  for (const row of published) {
    const link = byCode.get(`${row.section}::${row.code}`);
    if (!link) continue;
    const current = (draft[row.section] ?? []).find((item) => item.row_id === row.row_id);
    if (!current || !current.code || current.code === row.code) continue;
    renamed.push({
      row_id: row.row_id,
      section: row.section,
      public_table: link.public_table,
      public_id: link.public_id,
    });
  }
  return renamed;
}
