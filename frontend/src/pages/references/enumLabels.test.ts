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

describe("подписи форматов файла выноса GNSS", () => {
  it("коды форматов подписаны по-русски", () => {
    expect(enumLabel("PNEZD_CSV")).toBe("CSV: точка, север, восток, отметка, описание");
    expect(enumLabel("DXF_POINTS")).toBe("DXF: точки и номера скважин");
  });
});

describe("подписи групп пород для воздушной волны", () => {
  it("группы по взрываемости подписаны по-русски", () => {
    expect(enumLabel("IX_PLUS")).toBe("IX группа и выше");
    expect(enumLabel("V_MINUS")).toBe("V группа и ниже");
  });
});

describe("подписи уведомления о массовом взрыве", () => {
  it("способ и основание подписаны по-русски", () => {
    expect(enumLabel("PHONEGRAM")).toBe("Телефонограмма");
    expect(enumLabel("CUSTOMER_RULES")).toBe("Регламент заказчика");
  });
});
