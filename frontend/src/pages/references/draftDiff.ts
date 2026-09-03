import type { EconomicsReferenceItem } from "../../types/economics";
import { fingerprint } from "./fingerprint";
import type { DraftSections } from "./importDraft";

export type DraftDiff = {
  /** `row_id` строк черновика, которых нет в ревизии или которые изменены. */
  changed: Set<string>;
  /** Ключи `раздел::код` записей ревизии, которых в черновике не осталось. */
  removed: string[];
};

/**
 * Различия черновика и опубликованной ревизии.
 *
 * Удаления считаем отдельно: обход одних только строк черновика их не видит,
 * а без них публикация удалений оказывалась заблокирована.
 */
export function countDraftChanges(
  draft: DraftSections,
  publishedByCode: Map<string, EconomicsReferenceItem>,
): DraftDiff {
  const changed = new Set<string>();
  const kept = new Set<string>();
  for (const [section, rows] of Object.entries(draft)) {
    for (const row of rows) {
      const key = `${section}::${row.code}`;
      const published = publishedByCode.get(key);
      if (published) kept.add(key);
      if (!published || fingerprint(published) !== fingerprint(row)) changed.add(row.row_id);
    }
  }
  const removed = [...publishedByCode.keys()].filter((key) => !kept.has(key));
  return { changed, removed };
}
