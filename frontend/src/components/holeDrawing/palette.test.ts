import { describe, expect, it } from "vitest";
import { darken, explosiveColor } from "./palette";

describe("explosiveColor", () => {
  it("находит ВВ без учёта регистра: метка схемы приходит заглавными", () => {
    expect(explosiveColor("ГРАНУЛИТ-РП")).toBe("#efe3c4");
    expect(explosiveColor("ПВВ Гранулит-РП")).toBe("#efe3c4");
    expect(explosiveColor(undefined, "гранулит")).toBe("#efe3c4");
  });

  it("эмульсионное ВВ — своим цветом", () => {
    expect(explosiveColor("ЭВЕРСИН", "ПЭВВ ЭВЕРСИН Э-100")).toBe("#d0483c");
  });

  it("неизвестное ВВ — цвет по умолчанию", () => {
    expect(explosiveColor("Неизвестное")).toBe("#4472C4");
    expect(explosiveColor()).toBe("#4472C4");
  });
});

describe("darken", () => {
  it("затемняет каждый канал", () => {
    expect(darken("#efe3c4", 0.5)).toBe("#787262");
  });
});
