import { describe, expect, it } from "vitest";
import { enumLabel } from "./enumLabels";

describe("подписи перечислений методики ФОТ", () => {
  it("коды должностей и шкалы подписаны по-русски", () => {
    expect(enumLabel("PIECE_PROGRESSIVE")).toBe("Сдельно-прогрессивная");
    expect(enumLabel("NORMALIZED_METERS")).toBe("Приведённые метры бурения");
    expect(enumLabel("CURVE_POWER")).toBe("Степенная кривая");
    expect(enumLabel("SECTION_OUTPUT")).toBe("Выработка участка");
    expect(enumLabel("DRILLING_BLASTING")).toBe("Буровзрывной участок");
  });

  it("класс условий труда показывается как есть", () => {
    expect(enumLabel("3.2")).toBe("3.2");
  });
});
