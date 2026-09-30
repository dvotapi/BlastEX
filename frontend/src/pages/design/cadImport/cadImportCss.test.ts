import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * У каждого класса окна «Импорт чертежа» есть правило в стилях: jsdom не
 * считает раскладку, и класс без правила на экране ничем не выдаёт себя
 * (так было на вкладке «Экономика блока», см. `cssCoverage.test.ts`).
 */
const SRC = fileURLToPath(new URL("../../../", import.meta.url));
const DIR = join(SRC, "pages/design/cadImport");
const STYLE_FILES = [join(SRC, "styles.css"), join(SRC, "styles/cadImport.css")];

function classNamesIn(source: string): Set<string> {
  const found = new Set<string>();
  for (const match of source.matchAll(/className=(?:"([^"]*)"|\{`([^`]*)`\})/g)) {
    const literal = match[1] ?? match[2] ?? "";
    for (const token of literal.replace(/\$\{[^}]*\}/g, " ").split(/\s+/)) {
      if (token) found.add(token);
    }
  }
  return found;
}

describe("стили окна «Импорт чертежа»", () => {
  it("каждый класс разметки имеет хотя бы одно правило", () => {
    const css = STYLE_FILES.map((file) => readFileSync(file, "utf8")).join("\n");
    const used = new Set<string>();
    for (const name of readdirSync(DIR)) {
      if (!name.endsWith(".tsx") || name.endsWith(".test.tsx")) continue;
      for (const token of classNamesIn(readFileSync(join(DIR, name), "utf8"))) used.add(token);
    }

    expect([...used].filter((name) => !css.includes(`.${name}`)).sort()).toEqual([]);
  });
});
