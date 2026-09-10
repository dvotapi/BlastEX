import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * У каждого класса вкладки «Экономика блока» должно быть правило в стилях.
 *
 * Вкладка накопила полтора десятка классов, которые существовали только в
 * разметке: `drilling-volume`, `equipment-role-shifts`, `link-button` и
 * другие. Их не было видно ни в тестах (jsdom не считает раскладку), ни в
 * типах, ни в обзоре — а на экране их содержимое сваливалось в 32-пиксельную
 * колонку и наезжало на соседние. Этот тест ловит такое при первом же
 * появлении.
 *
 * Проверяются только классы этой вкладки: остальное приложение живёт по
 * прежним правилам, и разбирать его целиком — отдельная работа.
 */

// `fileURLToPath`, а не `.pathname`: путь проекта содержит кириллицу,
// и в URL она приезжает в процентной записи.
const SRC = fileURLToPath(new URL("../../", import.meta.url));
const PAGE_DIR = join(SRC, "pages/economics");
const STYLE_FILES = [join(SRC, "styles.css"), join(SRC, "styles/economics.css")];

/** Дубликаты iCloud (« 2.tsx») — не часть проекта, как и в конфиге vitest. */
const isDuplicate = (name: string) => / [23]\.[a-z]+$/.test(name) || / [23]$/.test(name);

function collectFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    if (isDuplicate(entry.name)) return [];
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return collectFiles(path);
    return entry.name.endsWith(".tsx") && !entry.name.endsWith(".test.tsx") ? [path] : [];
  });
}

/** Классы из литералов `className="…"` и `` className={`…`} ``. */
function classNamesIn(source: string): Set<string> {
  const found = new Set<string>();
  for (const match of source.matchAll(/className=(?:"([^"]*)"|\{`([^`]*)`\})/g)) {
    const literal = match[1] ?? match[2] ?? "";
    // В шаблонной строке подстановки `${...}` дают классы по условию —
    // их имена берутся из соседних литералов, а сам кусок пропускается.
    for (const token of literal.replace(/\$\{[^}]*\}/g, " ").split(/\s+/)) {
      if (token) found.add(token);
    }
  }
  return found;
}

describe("стили вкладки «Экономика блока»", () => {
  it("каждый класс разметки имеет хотя бы одно правило", () => {
    const css = STYLE_FILES.map((file) => readFileSync(file, "utf8")).join("\n");
    const used = new Set<string>();
    for (const file of collectFiles(PAGE_DIR)) {
      for (const name of classNamesIn(readFileSync(file, "utf8"))) used.add(name);
    }

    const orphans = [...used].filter((name) => !css.includes(`.${name}`)).sort();

    expect(orphans).toEqual([]);
  });
});
