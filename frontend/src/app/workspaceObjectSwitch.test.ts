import { describe, expect, it } from "vitest";
import {
  isLatestObjectRequest,
  mergeWorkspaceAfterObjectSwitch,
  shouldRollbackOnError,
} from "./workspaceObjectSwitch";
import type { WorkspaceState } from "../types";

/** Минимальное состояние: слияние трогает только перечисленные поля. */
function workspace(overrides: {
  objectName: string;
  shiftsPerMonth: number;
  objects: string[];
  price: number;
  warnings: string[];
}): WorkspaceState {
  return {
    settings: { active_work_object_name: overrides.objectName },
    snapshot: { labor_shifts_per_month: overrides.shiftsPerMonth },
    references: { work_object_records: overrides.objects.map((name) => ({ name })) },
    drilling_price_per_m: overrides.price,
    warnings: overrides.warnings,
  } as unknown as WorkspaceState;
}

describe("isLatestObjectRequest", () => {
  it("разрешает применить ответ, если запрос всё ещё последний", () => {
    expect(isLatestObjectRequest(2, 2)).toBe(true);
  });

  it("отбрасывает ответ на устаревший запрос (A ответил позже B)", () => {
    // Пользователь выбрал A (requestId=1), затем B (requestId=2);
    // ответ на A пришёл вторым — его нужно игнорировать.
    expect(isLatestObjectRequest(1, 2)).toBe(false);
  });
});

describe("shouldRollbackOnError", () => {
  it("откатывает имя объекта при ошибке последнего запроса", () => {
    expect(shouldRollbackOnError(2, 2, "Карьер А")).toBe(true);
  });

  it("не откатывает ошибку устаревшего запроса", () => {
    expect(shouldRollbackOnError(1, 2, "Карьер А")).toBe(false);
  });

  it("не откатывает, если предыдущего имени не было (состояние ещё не загрузилось)", () => {
    expect(shouldRollbackOnError(1, 1, undefined)).toBe(false);
  });
});

describe("mergeWorkspaceAfterObjectSwitch", () => {
  const prev = workspace({
    objectName: "Карьер А",
    shiftsPerMonth: 9,
    objects: ["Карьер А"],
    price: 100,
    warnings: ["старое предупреждение"],
  });
  const next = workspace({
    objectName: "Карьер Б",
    shiftsPerMonth: 5,
    objects: ["Карьер А", "Карьер Б"],
    price: 200,
    warnings: ["новое предупреждение"],
  });

  it("оставляет локальный снимок: несохранённые правки «Бурения» и «ФОТ» не теряются", () => {
    const merged = mergeWorkspaceAfterObjectSwitch(prev, next);
    expect(merged.snapshot).toBe(prev.snapshot);
  });

  it("берёт из ответа настройки, справочники, предупреждения и цену бурения", () => {
    const merged = mergeWorkspaceAfterObjectSwitch(prev, next);
    expect(merged.settings.active_work_object_name).toBe("Карьер Б");
    expect(merged.references).toBe(next.references);
    expect(merged.warnings).toBe(next.warnings);
    expect(merged.drilling_price_per_m).toBe(200);
  });

  it("не меняет исходные состояния", () => {
    mergeWorkspaceAfterObjectSwitch(prev, next);
    expect(prev.settings.active_work_object_name).toBe("Карьер А");
    expect(next.snapshot).not.toBe(prev.snapshot);
  });
});
