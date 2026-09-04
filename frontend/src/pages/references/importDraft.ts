import type { EconomicsReferenceItem } from "../../types/economics";
import type { DraftItem } from "./RecordForm";

export type DraftSections = Record<string, DraftItem[]>;

/**
 * Разделы из файла заменяют одноимённые разделы черновика целиком; разделы,
 * которых в файле нет, остаются как были. Страница не знает полей записей —
 * только код и состав разделов.
 */
export function mergeImportedSections(
  draft: DraftSections,
  imported: Record<string, EconomicsReferenceItem[]>,
  makeRowId: () => string,
): { draft: DraftSections; replaced: string[] } {
  const next: DraftSections = { ...draft };
  const replaced: string[] = [];
  for (const [section, items] of Object.entries(imported)) {
    next[section] = items.map((item) => ({ ...item, row_id: makeRowId() }));
    replaced.push(section);
  }
  return { draft: next, replaced };
}
