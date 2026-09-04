import type { PublicDelta, PublicDeltaEntry } from "../../types/economics";
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

/** Подпись плашки: «Из project1: 3 новые, 1 изменённая, 0 деактивированных». */
export function deltaSummary(counts: PublicDelta["counts"]): string {
  const parts = [
    `${counts.new} ${plural(counts.new, ["новая", "новые", "новых"])}`,
    `${counts.changed} ${plural(counts.changed, ["изменённая", "изменённые", "изменённых"])}`,
    `${counts.deactivated} ${plural(counts.deactivated, ["деактивированная", "деактивированные", "деактивированных"])}`,
  ];
  return `Из project1: ${parts.join(", ")}`;
}
