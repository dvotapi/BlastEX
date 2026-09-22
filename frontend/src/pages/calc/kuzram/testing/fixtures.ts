import type { BlastOptimizeResponse, BlastVariant } from "../../../../types";
import response from "./optimizeGabbro.json";

/**
 * Ответ `/blast/optimize` сервера PR 1 для тестов окна Kuz-Ram: габбро-диабаз,
 * ЭВЕРСИН Э-100, кусок 400 мм, порог 5 %, коронки 110, 152 и 250 мм, верхняя
 * граница q 1,5 — у коронки 250 мм порог не достигнут обеими моделями.
 */
export const OPTIMIZE_GABBRO = response as unknown as BlastOptimizeResponse;

/** Вариант коронки из фикстуры — глубокая копия, её можно менять в тесте. */
export function gabbroVariant(crownMm: 110 | 152 | 250, overrides: Partial<BlastVariant> = {}): BlastVariant {
  const found = OPTIMIZE_GABBRO.variants.find((variant) => variant.crown_mm === crownMm);
  if (!found) throw new Error(`В фикстуре нет коронки ${crownMm} мм`);
  return { ...(JSON.parse(JSON.stringify(found)) as BlastVariant), ...overrides };
}
