import { describe, expect, it } from "vitest";
import {
  completeFacts,
  defaultKuzramBlock,
  factCellError,
  KUZRAM_DEFAULTS,
  kuzramSettingsOf,
  outdatedHint,
  MAX_FACTS,
  parseDecimal,
  readKuzramBlock,
  sameSettings,
  settingError,
  settingsCaption,
} from "./kuzramSettings";

describe("readKuzramBlock", () => {
  it("без блока — умолчания и пустые факты", () => {
    expect(defaultKuzramBlock()).toEqual({ ...KUZRAM_DEFAULTS, facts: [] });
    expect(readKuzramBlock(undefined)).toEqual(defaultKuzramBlock());
    expect(readKuzramBlock("мусор")).toEqual(defaultKuzramBlock());
  });

  it("числа обрезаются по границам, неизвестные варианты — умолчание", () => {
    const block = readKuzramBlock({
      rock_factor_method: "как в коде",
      rock_factor_manual: 100,
      joint_condition: 3,
      joint_angle: 30,
      rock_factor_correction: 0.01,
      strength_exponent: "19/30",
      drill_deviation_m: -1,
      uniformity_correction: "2",
      q_max_kg_m3: 1.5,
    });
    expect(block).toEqual({
      rock_factor_method: "rmd50",
      rock_factor_manual: 30,
      joint_condition: 1,
      joint_angle: 30,
      rock_factor_correction: 0.1,
      strength_exponent: "19/30",
      drill_deviation_m: 0,
      uniformity_correction: 1,
      q_max_kg_m3: 1.5,
      facts: [],
    });
  });

  it("незаполненные строки фактов хранятся, мусор в ячейке — пусто, не больше 50 строк", () => {
    const rows = Array.from({ length: 60 }, (_, index) => ({
      crown_mm: 152,
      q_kg_m3: index === 0 ? null : 1.2,
      oversize_pct: "6",
    }));
    const block = readKuzramBlock({ facts: rows });
    expect(block.facts).toHaveLength(MAX_FACTS);
    expect(block.facts[0]).toEqual({ crown_mm: 152, q_kg_m3: null, oversize_pct: null });
    expect(readKuzramBlock({ facts: [null] }).facts).toEqual([{ crown_mm: null, q_kg_m3: null, oversize_pct: null }]);
  });
});

describe("kuzramSettingsOf", () => {
  it("отрезает факты: схема API запрещает лишние поля", () => {
    const block = {
      ...defaultKuzramBlock(),
      rock_factor_correction: 1.2,
      facts: [{ crown_mm: 152, q_kg_m3: 1.2, oversize_pct: 6 }],
    };
    const settings = kuzramSettingsOf(block);
    expect(settings).toEqual({ ...KUZRAM_DEFAULTS, rock_factor_correction: 1.2 });
    expect(Object.keys(settings)).not.toContain("facts");
  });
});

describe("проверка ввода", () => {
  it("parseDecimal понимает запятую; пусто и мусор — null", () => {
    expect(parseDecimal("1,15")).toBe(1.15);
    expect(parseDecimal(" 2 ")).toBe(2);
    expect(parseDecimal("")).toBeNull();
    expect(parseDecimal("abc")).toBeNull();
  });

  it("settingError — тексты как у сервера", () => {
    expect(settingError("rock_factor_correction", 1.15)).toBeNull();
    expect(settingError("rock_factor_correction", 20)).toBe("Поправка C(A) — от 0,1 до 10.");
    expect(settingError("q_max_kg_m3", 0.4)).toBe("Верхняя граница перебора q, кг/м³ — от 0,5 до 5.");
    expect(settingError("drill_deviation_m", null)).toBe("Введите число.");
  });

  it("factCellError — границы схемы факта, пустая ячейка не ошибка", () => {
    expect(factCellError("crown_mm", null)).toBeNull();
    expect(factCellError("crown_mm", 152)).toBeNull();
    expect(factCellError("crown_mm", 20)).toBeNull();
    expect(factCellError("crown_mm", 19)).toBe("Коронка — от 20 до 1000 мм.");
    expect(factCellError("crown_mm", 1001)).toBe("Коронка — от 20 до 1000 мм.");
    expect(factCellError("q_kg_m3", 10)).toBeNull();
    expect(factCellError("q_kg_m3", 11)).toBe("Фактический q — больше 0 и не больше 10 кг/м³.");
    expect(factCellError("oversize_pct", 100)).toBe("Фактический негабарит — больше 0 и меньше 100 %.");
  });

  it("completeFacts — только заполненные строки в границах, с номерами строк", () => {
    const facts = [
      { crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 },
      { crown_mm: 165, q_kg_m3: null, oversize_pct: 7 },
      { crown_mm: 130, q_kg_m3: 1.2, oversize_pct: 120 },
      { crown_mm: 110, q_kg_m3: 1.1, oversize_pct: 6 },
    ];
    expect(completeFacts(facts)).toEqual([
      { index: 0, fact: { crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 } },
      { index: 3, fact: { crown_mm: 110, q_kg_m3: 1.1, oversize_pct: 6 } },
    ]);
  });
});

describe("outdatedHint", () => {
  it("совет к пометке «по прежним настройкам»: ошибка, недостающее на листе, иначе — пересчитать", () => {
    const nothing = { crowns: false, rock: false, explosive: false };
    // Ошибка может быть любой (сеть, сервер) — совет не винит настройки, а ведёт к сообщению.
    expect(outdatedHint("Не удалось выполнить запрос.", { ...nothing, crowns: true })).toBe(
      "по текущим расчёт не прошёл — причина в сообщении об ошибке.",
    );
    expect(outdatedHint("", { ...nothing, crowns: true })).toBe(
      "на листе нечего считать — выберите коронки и нажмите «Рассчитать варианты».",
    );
    expect(outdatedHint("", { ...nothing, rock: true })).toBe(
      "на листе нечего считать — выберите породу и нажмите «Рассчитать варианты».",
    );
    expect(outdatedHint("", { ...nothing, explosive: true })).toBe(
      "на листе нечего считать — выберите ВВ и нажмите «Рассчитать варианты».",
    );
    expect(outdatedHint("", { crowns: true, rock: true, explosive: true })).toBe(
      "на листе нечего считать — выберите коронки, породу, ВВ и нажмите «Рассчитать варианты».",
    );
    expect(outdatedHint("", nothing)).toBe("пересчитайте их кнопкой «Рассчитать варианты» на листе.");
  });
});

describe("settingsCaption", () => {
  it("на умолчаниях пусто", () => {
    expect(settingsCaption(KUZRAM_DEFAULTS)).toBe("");
    expect(sameSettings(KUZRAM_DEFAULTS, { ...KUZRAM_DEFAULTS })).toBe(true);
    expect(sameSettings(KUZRAM_DEFAULTS, { ...KUZRAM_DEFAULTS, joint_angle: 40 })).toBe(false);
  });

  it("кратко перечисляет отличия", () => {
    expect(
      settingsCaption({ ...KUZRAM_DEFAULTS, rock_factor_method: "joint_factor", rock_factor_correction: 1.15 }),
    ).toBe("JF · C(A) 1,15");
    expect(settingsCaption({ ...KUZRAM_DEFAULTS, rock_factor_method: "rmd10" })).toBe("RMD 10");
    expect(
      settingsCaption({
        ...KUZRAM_DEFAULTS,
        rock_factor_method: "manual",
        rock_factor_manual: 7.5,
        strength_exponent: "19/30",
        drill_deviation_m: 0.3,
        uniformity_correction: 0.9,
        q_max_kg_m3: 3,
      }),
    ).toBe("A 7,5 · 19/30 · σ 0,3 м · C(n) 0,9 · q до 3");
  });
});
