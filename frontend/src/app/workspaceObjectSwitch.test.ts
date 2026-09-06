import { describe, expect, it } from "vitest";
import { isLatestObjectRequest, shouldRollbackOnError } from "./workspaceObjectSwitch";

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
