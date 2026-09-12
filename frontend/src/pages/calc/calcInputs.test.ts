import { describe, expect, it } from "vitest";
import {
  AUTOSAVE_DELAY_MS,
  applyCalcInputs,
  calcInputsEqual,
  collectCalcInputs,
  defaultCalcSheet,
  isOptimizationResultStale,
  nextAutosaveAction,
  panelInputsEqual,
  type CalcInputsCatalogs,
  type PanelInputs,
  type SheetState,
} from "./calcInputs";

const CATALOGS: CalcInputsCatalogs = {
  rocks: ["Гранит", "Известняк"],
  explosiveKeys: ["ПВВ Гранулит-РП", "ПЭВВ ЭВЕРСИН Э-100"],
  crowns: [110, 127, 152],
  nsiLengthOptions: [6, 8, 10, 12],
  detonatorDelayOptions: [250, 500, 1000],
};

function panel(overrides: Partial<PanelInputs> = {}): PanelInputs {
  return {
    explosive_key: "ПВВ Гранулит-РП",
    undercharge_m: 3.1,
    intermediate_detonators_per_hole: 1,
    nsi_per_hole: 1,
    nsi_length_1_m: 12,
    nsi_length_2_m: 6,
    detonator_delay_ms: 500,
    ...overrides,
  };
}

function sheet(overrides: Partial<SheetState> = {}): SheetState {
  return {
    rockName: "Известняк",
    explosiveKey: "ПЭВВ ЭВЕРСИН Э-100",
    lumpSizeMm: 500,
    benchHeightM: 12,
    overdrillM: 1.5,
    oversizeCoeff: 1.08,
    spacingCoeff: 1.3,
    oversizeThresholdPct: 4,
    selectedCrownsMm: [110, 152],
    selectedCrownMm: 152,
    blockVolumeM3: 42_000,
    additionalHolesPct: 2.5,
    productionUnitCode: "UNIT_PERM",
    panels: {
      left: panel(),
      right: panel({ explosive_key: "ПЭВВ ЭВЕРСИН Э-100", undercharge_m: 2, nsi_per_hole: 2 }),
    },
    ...overrides,
  };
}

describe("collectCalcInputs / applyCalcInputs", () => {
  it("возвращает лист в исходном виде после сохранения и загрузки", () => {
    const original = sheet();
    const restored = applyCalcInputs(collectCalcInputs(original), CATALOGS);
    expect(restored).toEqual(original);
  });

  it("помечает настройки версией 1", () => {
    expect(collectCalcInputs(sheet()).version).toBe(1);
  });

  it("хранит выбранный юнит под тем же ключом, что и остальные поля листа", () => {
    expect(collectCalcInputs(sheet()).production_unit_code).toBe("UNIT_PERM");
  });

  it("настройки, сохранённые до появления юнита, открываются без фильтра", () => {
    const { production_unit_code: _dropped, ...legacy } = collectCalcInputs(sheet());
    expect(applyCalcInputs(legacy, CATALOGS)?.productionUnitCode).toBe("");
  });

  it("не принимает юнит не строкой", () => {
    const raw = { ...collectCalcInputs(sheet()), production_unit_code: 42 };
    expect(applyCalcInputs(raw, CATALOGS)?.productionUnitCode).toBe("");
  });

  it("подменяет чужие породу, ВВ и диаметр первыми доступными", () => {
    const foreign = collectCalcInputs(
      sheet({
        rockName: "Мрамор",
        explosiveKey: "Эмульсия из другой команды",
        selectedCrownsMm: [89, 216],
        selectedCrownMm: 216,
        panels: { left: panel({ explosive_key: "Чужое ВВ" }), right: panel() },
      }),
    );
    const restored = applyCalcInputs(foreign, CATALOGS);
    expect(restored?.rockName).toBe("Гранит");
    expect(restored?.explosiveKey).toBe("ПВВ Гранулит-РП");
    expect(restored?.selectedCrownsMm).toEqual([110]);
    expect(restored?.selectedCrownMm).toBeNull();
    expect(restored?.panels.left.explosive_key).toBe("ПВВ Гранулит-РП");
  });

  it("оставляет только известные диаметры и сбрасывает выбранный, если он не в наборе", () => {
    const raw = collectCalcInputs(sheet({ selectedCrownsMm: [110, 999], selectedCrownMm: 999 }));
    const restored = applyCalcInputs(raw, CATALOGS);
    expect(restored?.selectedCrownsMm).toEqual([110]);
    expect(restored?.selectedCrownMm).toBeNull();
  });

  it("обрезает числа по границам полей", () => {
    const raw = {
      ...collectCalcInputs(sheet()),
      lump_size_mm: 5_000,
      bench_height_m: 1,
      overdrill_m: 40,
      oversize_coeff: 3,
      spacing_coeff: 0.1,
      oversize_threshold_pct: 90,
      block_volume_m3: 10,
      additional_holes_pct: 300,
    };
    const restored = applyCalcInputs(raw, CATALOGS);
    expect(restored?.lumpSizeMm).toBe(1200);
    expect(restored?.benchHeightM).toBe(5);
    expect(restored?.overdrillM).toBe(3);
    expect(restored?.oversizeCoeff).toBe(1.15);
    expect(restored?.spacingCoeff).toBe(1);
    expect(restored?.oversizeThresholdPct).toBe(15);
    expect(restored?.blockVolumeM3).toBe(1000);
    expect(restored?.additionalHolesPct).toBe(20);
  });

  it("обрезает недозаряд по глубине скважины", () => {
    const raw = { ...collectCalcInputs(sheet({ benchHeightM: 10, overdrillM: 1 })), panels: { left: panel({ undercharge_m: 99 }), right: panel({ undercharge_m: -5 }) } };
    const restored = applyCalcInputs(raw, CATALOGS);
    expect(restored?.panels.left.undercharge_m).toBe(10.5);
    expect(restored?.panels.right.undercharge_m).toBe(0);
  });

  it("восстанавливает поля панели, если в сохранённом значении мусор", () => {
    const raw = {
      ...collectCalcInputs(sheet()),
      panels: {
        left: { explosive_key: "ПВВ Гранулит-РП", intermediate_detonators_per_hole: 7, nsi_per_hole: "два", nsi_length_1_m: -1, detonator_delay_ms: null },
        right: panel(),
      },
    };
    const restored = applyCalcInputs(raw, CATALOGS);
    expect(restored?.panels.left.intermediate_detonators_per_hole).toBe(1);
    expect(restored?.panels.left.nsi_per_hole).toBe(1);
    // -1 и null — не числа из списка опций, а не просто "неположительные":
    // подменяются первым доступным вариантом, как порода/ВВ/диаметр.
    expect(restored?.panels.left.nsi_length_1_m).toBe(CATALOGS.nsiLengthOptions[0]);
    expect(restored?.panels.left.detonator_delay_ms).toBe(CATALOGS.detonatorDelayOptions[0]);
  });

  it("подменяет длину НСИ и замедление ДШ, которых нет в списке опций, первым доступным", () => {
    const raw = {
      ...collectCalcInputs(sheet()),
      panels: {
        left: panel({ nsi_length_1_m: 99, nsi_length_2_m: 77, detonator_delay_ms: 999 }),
        right: panel(),
      },
    };
    const restored = applyCalcInputs(raw, CATALOGS);
    expect(restored?.panels.left.nsi_length_1_m).toBe(CATALOGS.nsiLengthOptions[0]);
    expect(restored?.panels.left.nsi_length_2_m).toBe(CATALOGS.nsiLengthOptions[0]);
    expect(restored?.panels.left.detonator_delay_ms).toBe(CATALOGS.detonatorDelayOptions[0]);
  });

  it("сортирует выбранные диаметры по возрастанию, как toggleCrown", () => {
    const raw = collectCalcInputs(sheet({ selectedCrownsMm: [152, 110], selectedCrownMm: 110 }));
    const restored = applyCalcInputs(raw, CATALOGS);
    expect(restored?.selectedCrownsMm).toEqual([110, 152]);
  });

  it.each([
    ["null", null],
    ["строка", "настройки"],
    ["число", 17],
    ["массив", [1, 2, 3]],
    ["пустой объект", {}],
    ["чужая версия", { version: 2, rock_name: "Гранит", panels: { left: {}, right: {} } }],
    ["без панелей", { version: 1, rock_name: "Гранит" }],
    ["одна панель", { version: 1, rock_name: "Гранит", panels: { left: {} } }],
  ])("не принимает %s", (_label, raw) => {
    expect(applyCalcInputs(raw, CATALOGS)).toBeNull();
  });
});

describe("defaultCalcSheet", () => {
  it("берёт умолчания справочников и все диаметры", () => {
    const created = defaultCalcSheet(CATALOGS, { rockName: "Известняк", explosiveKey: "ПЭВВ ЭВЕРСИН Э-100" });
    expect(created.rockName).toBe("Известняк");
    expect(created.explosiveKey).toBe("ПЭВВ ЭВЕРСИН Э-100");
    expect(created.selectedCrownsMm).toEqual([110, 127, 152]);
    expect(created.selectedCrownMm).toBeNull();
    expect(created.panels.left.explosive_key).not.toBe(created.panels.right.explosive_key);
  });

  it("сам себя переживает после сохранения и загрузки", () => {
    const created = defaultCalcSheet(CATALOGS, { rockName: "Гранит", explosiveKey: "ПВВ Гранулит-РП" });
    expect(applyCalcInputs(collectCalcInputs(created), CATALOGS)).toEqual(created);
  });
});

describe("calcInputsEqual", () => {
  it("не зависит от порядка ключей", () => {
    const left = collectCalcInputs(sheet());
    const shuffled = JSON.parse(JSON.stringify({ panels: left.panels, version: left.version, rock_name: left.rock_name })) as Record<string, unknown>;
    for (const [key, value] of Object.entries(left)) {
      if (!(key in shuffled)) shuffled[key] = value;
    }
    expect(Object.keys(shuffled)).not.toEqual(Object.keys(left));
    expect(calcInputsEqual(left, shuffled as unknown as typeof left)).toBe(true);
  });

  it("видит отличие в поле панели", () => {
    const left = collectCalcInputs(sheet());
    const right = collectCalcInputs(sheet({ panels: { left: panel({ undercharge_m: 3.2 }), right: panel() } }));
    expect(calcInputsEqual(left, right)).toBe(false);
  });

  it("считает равными два отсутствующих значения и разными одно из двух", () => {
    expect(calcInputsEqual(null, null)).toBe(true);
    expect(calcInputsEqual(null, collectCalcInputs(sheet()))).toBe(false);
    expect(calcInputsEqual(collectCalcInputs(sheet()), null)).toBe(false);
  });
});

describe("panelInputsEqual", () => {
  it("сравнивает поля панели, а не ссылки", () => {
    expect(panelInputsEqual(panel(), panel())).toBe(true);
    expect(panelInputsEqual(panel(), panel({ detonator_delay_ms: 1000 }))).toBe(false);
  });
});

describe("nextAutosaveAction", () => {
  const current = collectCalcInputs(sheet());

  it("ничего не пишет, пока нечего сохранять", () => {
    expect(nextAutosaveAction(current, null, AUTOSAVE_DELAY_MS)).toBe("none");
    expect(nextAutosaveAction(current, current, AUTOSAVE_DELAY_MS)).toBe("none");
  });

  it("ждёт задержку после последнего изменения", () => {
    expect(nextAutosaveAction(null, current, 0)).toBe("wait");
    expect(nextAutosaveAction(null, current, AUTOSAVE_DELAY_MS - 1)).toBe("wait");
  });

  it("пишет, когда задержка вышла, а настройки отличаются от сохранённых", () => {
    expect(nextAutosaveAction(null, current, AUTOSAVE_DELAY_MS)).toBe("save");
    const changed = collectCalcInputs(sheet({ benchHeightM: 13 }));
    expect(nextAutosaveAction(current, changed, AUTOSAVE_DELAY_MS + 500)).toBe("save");
  });

  it("держит задержку в 800 мс", () => {
    expect(AUTOSAVE_DELAY_MS).toBe(800);
  });
});

describe("isOptimizationResultStale", () => {
  it("не устарел, если поколение и объект не менялись", () => {
    expect(isOptimizationResultStale(1, 1, "Карьер №1", "Карьер №1")).toBe(false);
  });

  it("устарел, если поколение выросло — пользователь поправил лист, пока шёл запрос", () => {
    expect(isOptimizationResultStale(1, 2, "Карьер №1", "Карьер №1")).toBe(true);
  });

  it("устарел, если сменился активный объект работ", () => {
    expect(isOptimizationResultStale(1, 1, "Карьер №1", "Карьер №2")).toBe(true);
  });

  it("устарел при обоих расхождениях сразу", () => {
    expect(isOptimizationResultStale(1, 3, "Карьер №1", "Карьер №2")).toBe(true);
  });
});
