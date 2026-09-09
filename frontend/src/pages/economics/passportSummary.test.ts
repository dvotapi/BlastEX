import { describe, expect, it } from "vitest";

import { passportMetrics, passportRows } from "./passportSummary";

/** Неразрывный пробел тысяч — обычным, чтобы ожидание читалось глазами. */
const plain = (text: string) => text.replace(/\u00a0/g, " ");

const PHYSICAL = {
  rock_volume_m3: 30000,
  drilling_m: "2420",
  holes: 220,
  explosive_kg: 29554.55,
  downhole_nsi: 220,
  surface_nsi: 220,
};

describe("плашки паспорта", () => {
  it("четыре показателя в порядке чтения", () => {
    const shown = passportMetrics(PHYSICAL).map((m) => `${m.label}: ${plain(m.value)} ${m.unit}`);

    expect(shown).toEqual([
      "Объём блока: 30 000 м³",
      "Погонаж бурения: 2 420 п.м.",
      "Скважины: 220 шт",
      "С одной скважины: 11,0 м",
    ]);
  });

  it("выход с одной скважины — погонаж на число скважин, с одним знаком", () => {
    expect(passportMetrics({ drilling_m: 2500, holes: 220 })[3].value).toBe("11,4");
  });

  it("без скважин выход — прочерк, а не бесконечность", () => {
    expect(passportMetrics({ drilling_m: 2420, holes: 0 })[3].value).toBe("—");
    expect(passportMetrics({ drilling_m: 2420 })[3].value).toBe("—");
  });

  it("отсутствующая величина — прочерк", () => {
    expect(passportMetrics({})[0].value).toBe("—");
    expect(passportMetrics({ rock_volume_m3: "abc" })[0].value).toBe("—");
    expect(passportMetrics({ holes: "" })[2].value).toBe("—");
  });
});

describe("полная таблица паспорта", () => {
  it("показывает только посчитанные величины, источник — из lineage или «технический расчёт»", () => {
    const rows = passportRows(
      { rock_volume_m3: 30000, holes: 220 },
      { holes: "BlastGeometry.block.total_holes" },
    );

    expect(rows.map((row) => row.key)).toEqual(["rock_volume_m3", "holes"]);
    expect(plain(rows[0].value)).toBe("30 000");
    expect(rows[0].source).toBe("технический расчёт");
    expect(rows[1].source).toBe("BlastGeometry.block.total_holes");
  });
});
