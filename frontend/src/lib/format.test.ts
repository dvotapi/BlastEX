import { describe, expect, it } from "vitest";
import { ruDate } from "./format";

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
