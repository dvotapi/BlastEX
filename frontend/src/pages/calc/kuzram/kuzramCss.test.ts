import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * Стили окна «Модель Kuz-Ram» завязаны на атрибуты разметки: строки таблицы
 * сравнения кликабельны (`tabIndex`), выбранную отмечает `aria-current`
 * (`KuzRamComparison.tsx`). Селекторы по прежнему `aria-selected` оставили бы
 * строки без курсора, подсветки и выделения — классы в cssCoverage это не ловит.
 */
describe("kuzram.css", () => {
  it("строки сравнения: кликабельные — по tabindex, выбранная — по aria-current", () => {
    const css = readFileSync(new URL("../../../styles/kuzram.css", import.meta.url), "utf8");
    expect(css).toContain(".kuzram-table tbody tr[tabindex] { cursor:pointer; }");
    expect(css).toContain(".kuzram-table tbody tr[tabindex]:hover");
    expect(css).toContain('.kuzram-table tbody tr[aria-current="true"]');
    expect(css).not.toMatch(/tr\[aria-selected/);
  });
});
