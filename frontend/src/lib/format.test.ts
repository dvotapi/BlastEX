import { afterEach, describe, expect, it, vi } from "vitest";
import { ruDate, ruDateTime } from "./format";

describe("ruDate", () => {
  it("дата ISO — по-русски, время отбрасывается", () => {
    expect(ruDate("2026-09-01")).toBe("01.09.2026");
    expect(ruDate("2026-10-02T19:08:10+00:00")).toBe("02.10.2026");
  });

  it("без даты — прочерк", () => {
    expect(ruDate(null)).toBe("—");
    expect(ruDate("")).toBe("—");
    expect(ruDate("не дата")).toBe("—");
  });
});

describe("ruDateTime", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("время сервера (UTC) — в часовом поясе пользователя: ночная загрузка попадает в свой день", () => {
    vi.stubEnv("TZ", "Asia/Yekaterinburg");
    expect(ruDateTime("2026-10-02T19:08:10+00:00")).toBe("03.10.2026 00:08");
    expect(ruDateTime("2026-10-03T03:31:14.5+00:00")).toBe("03.10.2026 08:31");
  });

  it("без времени — прочерк", () => {
    expect(ruDateTime(null)).toBe("—");
    expect(ruDateTime("")).toBe("—");
    expect(ruDateTime("не дата")).toBe("—");
  });
});
