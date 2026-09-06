import { describe, expect, it } from "vitest";
import { nextSavedAfterWrite, pendingAfterSaveError, shouldReportSaveStatus } from "./useCalcInputsAutosave";
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

  it("возвращает упавшую запись, если очередь пуста и новее ничего не выдавалось", () => {
    expect(pendingAfterSaveError(null, failed, 1, 1)).toBe(failed);
  });

  it("не трогает более новую запись, поставленную в очередь, пока шло сохранение", () => {
    const newer = { objectName: "Карьер-1", inputs: collectCalcInputs(sheet({ benchHeightM: 13 })) };
    expect(pendingAfterSaveError(newer, failed, 1, 2)).toBe(newer);
  });

  it("не восстанавливает старый снимок, если таймер уже забрал более новую правку в очередь", () => {
    // seq=1 (failed) ещё летел, когда отложенный таймер обнулил pendingRef и
    // поставил в очередь seq=2 — она сама покрывает несохранённое. Если бы
    // здесь вернулась `failed`, следующий flush() дописал бы её поверх уже
    // сохранённых (или ожидающих своей очереди) свежих данных.
    expect(pendingAfterSaveError(null, failed, 1, 2)).toBeNull();
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

describe("nextSavedAfterWrite", () => {
  const older = collectCalcInputs(sheet({ benchHeightM: 10 }));
  const newer = collectCalcInputs(sheet({ benchHeightM: 20 }));

  it("применяет запись, если она последняя из выданных очередью", () => {
    const current = { objectName: "Карьер-1", inputs: older };
    const result = nextSavedAfterWrite(current, { objectName: "Карьер-1", inputs: newer, seq: 2 }, 2);
    expect(result).toEqual({ objectName: "Карьер-1", inputs: newer });
  });

  it("игнорирует ответ записи, обогнанной более новой в очереди (более старый PUT не затирает savedRef)", () => {
    // seq=1 ушёл на сервер раньше seq=2, но пока он летел, в очередь встала
    // ещё одна запись (seq=2) и уже сохранила своё значение — ответ на seq=1
    // не должен откатить savedRef назад.
    const current = { objectName: "Карьер-1", inputs: newer };
    const result = nextSavedAfterWrite(current, { objectName: "Карьер-1", inputs: older, seq: 1 }, 2);
    expect(result).toBe(current);
  });

  it("не трогает savedRef, если объект уже сменился на другой", () => {
    const current = { objectName: "Карьер-2", inputs: null };
    const result = nextSavedAfterWrite(current, { objectName: "Карьер-1", inputs: older, seq: 1 }, 1);
    expect(result).toBe(current);
  });

  it("принимает первую запись, когда savedRef ещё пуст", () => {
    const result = nextSavedAfterWrite(null, { objectName: "Карьер-1", inputs: older, seq: 1 }, 1);
    expect(result).toBeNull();
  });
});
