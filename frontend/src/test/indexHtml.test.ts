import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// Без doctype браузер рендерит приложение в quirks-режиме: таблицы не
// наследуют шрифт, строки без прямого текста теряют «распорку» родителя.
describe("frontend/index.html", () => {
  it("начинается с <!doctype html> — стандартный режим рендеринга", () => {
    const html = readFileSync(new URL("../../index.html", import.meta.url), "utf8");
    expect(html.trimStart().toLowerCase().startsWith("<!doctype html>")).toBe(true);
  });
});
