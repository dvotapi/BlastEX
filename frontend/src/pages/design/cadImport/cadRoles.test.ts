import { describe, expect, it } from "vitest";
import { ORIGIN_TITLES, ROLE_COLORS, roleColor } from "./cadRoles";

const ALL_ROLES = [
  "block_contour",
  "design_line",
  "crest_top",
  "crest_bottom",
  "feature_line",
  "contour_line",
  "spot_heights",
  "situation",
  "ignore",
  "crests_by_z",
] as const;

describe("cadRoles", () => {
  it("у каждой роли свой цвет", () => {
    for (const role of ALL_ROLES) expect(ROLE_COLORS[role]).toMatch(/^#[0-9a-f]{6}$/);
    expect(new Set(ALL_ROLES.filter((role) => role !== "crests_by_z").map((role) => ROLE_COLORS[role])).size).toBe(9);
    expect(roleColor("no_such_role")).toBe(ROLE_COLORS.situation);
  });

  it("у каждого происхождения есть пояснение", () => {
    expect(Object.keys(ORIGIN_TITLES).sort()).toEqual(["auto", "manual", "template", "z"]);
  });
});
