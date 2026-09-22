import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * Стили окна «Модель Kuz-Ram» завязаны на атрибуты разметки: строки таблицы
 * сравнения кликабельны (`tabIndex`), выбранную отмечает `aria-current`
 * (`KuzRamComparison.tsx`). Селекторы по прежнему `aria-selected` оставили бы
 * строки без курсора, подсветки и выделения — классы в cssCoverage это не ловит.
 * Сверяем селекторы и нужное свойство правила, а не форматирование файла.
 */
describe("kuzram.css", () => {
  it("строки сравнения: кликабельные — по tabindex, выбранная — по aria-current", () => {
    const css = readFileSync(new URL("../../../styles/kuzram.css", import.meta.url), "utf8");
    expect(css).toMatch(/\.kuzram-table\s+tbody\s+tr\[tabindex\]\s*\{[^}]*cursor\s*:\s*pointer/);
    expect(css).toMatch(/\.kuzram-table\s+tbody\s+tr\[tabindex\]:hover\s*\{[^}]*background/);
    expect(css).toMatch(/\.kuzram-table\s+tbody\s+tr\[aria-current="true"\]\s*\{[^}]*background/);
    expect(css).not.toMatch(/tr\[aria-selected/);
  });
});
