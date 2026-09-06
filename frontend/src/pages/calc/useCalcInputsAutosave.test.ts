import { describe, expect, it } from "vitest";
import { pendingAfterSaveError, shouldReportSaveStatus } from "./useCalcInputsAutosave";
import { collectCalcInputs } from "./calcInputs";
import type { PanelInputs, SheetState } from "./calcInputs";

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
    panels: { left: panel(), right: panel() },
    ...overrides,
  };
}

describe("pendingAfterSaveError", () => {
  const failed = { objectName: "Карьер-1", inputs: collectCalcInputs(sheet()) };

  it("возвращает упавшую запись, если очередь пуста", () => {
    expect(pendingAfterSaveError(null, failed)).toBe(failed);
  });

  it("не трогает более новую запись, поставленную в очередь, пока шло сохранение", () => {
    const newer = { objectName: "Карьер-1", inputs: collectCalcInputs(sheet({ benchHeightM: 13 })) };
    expect(pendingAfterSaveError(newer, failed)).toBe(newer);
  });
});

describe("shouldReportSaveStatus", () => {
  it("показывает статус записи текущего объекта", () => {
    expect(shouldReportSaveStatus("Карьер-1", "Карьер-1")).toBe(true);
  });

  it("молчит про дозапись прошлого объекта: полоса уже показывает новый", () => {
    // `flush()` при смене объекта дописывает настройки прошлого объекта —
    // «сохранение…»/«сохранено» рядом с новым объектом ввели бы в заблуждение.
    expect(shouldReportSaveStatus("Карьер-1", "Карьер-2")).toBe(false);
  });
});
