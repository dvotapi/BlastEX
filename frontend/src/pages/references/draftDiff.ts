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
 * а без них публикация удалений оказывалась заблокирована. `numericKeys`
 * отдаёт числовые поля раздела по каталогу схем.
 */
export function countDraftChanges(
  draft: DraftSections,
  publishedByCode: Map<string, EconomicsReferenceItem>,
  numericKeys: (section: string) => ReadonlySet<string>,
): DraftDiff {
  const changed = new Set<string>();
  const kept = new Set<string>();
  for (const [section, rows] of Object.entries(draft)) {
    // Числовые поля своя у каждого раздела: сравнение «0021» и «21» зависит
    // от того, число это поле по схеме или текст.
    const numeric = numericKeys(section);
    for (const row of rows) {
      const key = `${section}::${row.code}`;
      const published = publishedByCode.get(key);
      if (published) kept.add(key);
      if (!published || fingerprint(published, numeric) !== fingerprint(row, numeric)) changed.add(row.row_id);
    }
  }
  const removed = [...publishedByCode.keys()].filter((key) => !kept.has(key));
  return { changed, removed };
}
