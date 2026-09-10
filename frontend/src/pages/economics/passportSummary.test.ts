import { describe, expect, it } from "vitest";

import { passportCreatedAtLabel, passportMetrics, passportRows } from "./passportSummary";

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
  it("пять показателей в порядке чтения", () => {
    const shown = passportMetrics(PHYSICAL).map((m) => `${m.label}: ${plain(m.value)} ${m.unit}`);

    expect(shown).toEqual([
      "Объём блока: 30 000 м³",
      "Погонаж бурения: 2 420 п.м.",
      "Скважины: 220 шт",
      "С одной скважины: 11,0 м",
      "Средний расход ВВ: 12,2 кг/м",
    ]);
  });

  it("выход с одной скважины — погонаж на число скважин, с одним знаком", () => {
    expect(passportMetrics({ drilling_m: 2500, holes: 220 })[3].value).toBe("11,4");
  });

  it("без скважин выход — прочерк, а не бесконечность", () => {
    expect(passportMetrics({ drilling_m: 2420, holes: 0 })[3].value).toBe("—");
    expect(passportMetrics({ drilling_m: 2420 })[3].value).toBe("—");
  });

  it("средний расход ВВ — масса на погонаж, с одним знаком", () => {
    expect(passportMetrics({ explosive_kg: 33000, drilling_m: 2079 })[4].value).toBe("15,9");
    expect(passportMetrics({ explosive_kg: 33000, drilling_m: 2079 })[4].unit).toBe("кг/м");
  });

  it("при нулевом или отсутствующем погонаже средний расход ВВ — прочерк", () => {
    expect(passportMetrics({ explosive_kg: 33000, drilling_m: 0 })[4].value).toBe("—");
    expect(passportMetrics({ explosive_kg: 33000 })[4].value).toBe("—");
    expect(passportMetrics({ drilling_m: 2079 })[4].value).toBe("—");
  });

  it("отсутствующая величина — прочерк", () => {
    expect(passportMetrics({})[0].value).toBe("—");
    expect(passportMetrics({ rock_volume_m3: "abc" })[0].value).toBe("—");
    expect(passportMetrics({ holes: "" })[2].value).toBe("—");
    expect(passportMetrics({ holes: "  " })[2].value).toBe("—");
  });
});

describe("дата паспорта", () => {
  it("короткая подпись днём, месяцем словом и годом — без времени", () => {
    // Полдень UTC, чтобы дата не съезжала на соседние сутки в любом часовом поясе теста.
    expect(passportCreatedAtLabel("2026-09-05T12:00:00Z")).toMatch(/^Паспорт от \d{1,2} \S+ 2026 г\.$/);
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

  it("пустой паспорт даёт пустую таблицу", () => {
    expect(passportRows({}, {})).toEqual([]);
  });

  it("порядок всех шести строк — по паспорту", () => {
    const rows = passportRows(PHYSICAL, {});

    expect(rows.map((row) => row.key)).toEqual([
      "rock_volume_m3",
      "drilling_m",
      "holes",
      "explosive_kg",
      "downhole_nsi",
      "surface_nsi",
    ]);
    expect(rows.slice(3).map((row) => row.label)).toEqual(["Масса ВВ", "Скважинные НСИ", "Поверхностные НСИ"]);
    expect(rows.slice(3).map((row) => row.unit)).toEqual(["кг", "шт", "шт"]);
  });

  it("нечисловое значение в строке таблицы — прочерк", () => {
    expect(passportRows({ explosive_kg: "abc" }, {})[0].value).toBe("—");
  });
});
