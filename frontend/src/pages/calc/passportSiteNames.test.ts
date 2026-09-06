import { describe, expect, it } from "vitest";
import { distinctRevisionIds, revisionsToFetch, siteNameFor } from "./passportSiteNames";
import type { TechnicalPassport } from "../../types/blockEconomics";

function passport(overrides: Partial<TechnicalPassport> = {}): TechnicalPassport {
  return {
    id: "passport-1",
    organization_id: "org-1",
    site_code: "SITE_A",
    object_name: "Блок 1200 м³",
    version_no: 1,
    previous_passport_id: null,
    reference_revision_id: "rev-1",
    formula_version: "v1",
    input_snapshot: {},
    selected_variant: {},
    block_snapshot: {},
    physical: {},
    lineage: {},
    created_at: "2026-01-01T00:00:00Z",
    created_by: "user-1",
    ...overrides,
  };
}

describe("distinctRevisionIds", () => {
  it("возвращает уникальные ревизии без дублей", () => {
    const passports = [
      passport({ id: "p1", reference_revision_id: "rev-1" }),
      passport({ id: "p2", reference_revision_id: "rev-2" }),
      passport({ id: "p3", reference_revision_id: "rev-1" }),
    ];
    expect(distinctRevisionIds(passports)).toEqual(["rev-1", "rev-2"]);
  });

  it("пропускает паспорта без ревизии", () => {
    const passports = [passport({ id: "p1", reference_revision_id: "" })];
    expect(distinctRevisionIds(passports)).toEqual([]);
  });
});

describe("siteNameFor", () => {
  it("переименованный объект: старый паспорт показывает имя своей ревизии", () => {
    const oldPassport = passport({ site_code: "SITE_A", reference_revision_id: "rev-old" });
    const namesByRevision = { "rev-old": { SITE_A: "Карьер Северный (старое имя)" } };
    const currentNames = { SITE_A: "Карьер Северный" };
    expect(siteNameFor(oldPassport, namesByRevision, currentNames)).toBe(
      "Карьер Северный (старое имя)",
    );
  });

  it("неизвестная ревизия — берём имя из текущего снимка", () => {
    const item = passport({ site_code: "SITE_A", reference_revision_id: "rev-missing" });
    const namesByRevision = {};
    const currentNames = { SITE_A: "Карьер Северный" };
    expect(siteNameFor(item, namesByRevision, currentNames)).toBe("Карьер Северный");
  });

  it("имени нет нигде — выводим код объекта", () => {
    const item = passport({ site_code: "SITE_B", reference_revision_id: "rev-missing" });
    expect(siteNameFor(item, {}, {})).toBe("SITE_B");
  });
});

describe("revisionsToFetch", () => {
  it("пропускает текущую ревизию — она уже загружена отдельно", () => {
    const passports = [passport({ reference_revision_id: "rev-current" })];
    expect(revisionsToFetch(passports, {}, new Set(), "rev-current")).toEqual([]);
  });

  it("пропускает уже известные ревизии, включая запомненные как недоступные", () => {
    const passports = [
      passport({ id: "p1", reference_revision_id: "rev-known" }),
      passport({ id: "p2", reference_revision_id: "rev-unavailable" }),
    ];
    const known = { "rev-known": { SITE_A: "Карьер" }, "rev-unavailable": {} };
    expect(revisionsToFetch(passports, known, new Set(), "rev-current")).toEqual([]);
  });

  it("пропускает ревизии, запрос которых уже отправлен и ещё не завершился", () => {
    const passports = [passport({ reference_revision_id: "rev-pending" })];
    const pending = new Set(["rev-pending"]);
    expect(revisionsToFetch(passports, {}, pending, "rev-current")).toEqual([]);
  });

  it("возвращает недостающие ревизии без дублей", () => {
    const passports = [
      passport({ id: "p1", reference_revision_id: "rev-a" }),
      passport({ id: "p2", reference_revision_id: "rev-b" }),
      passport({ id: "p3", reference_revision_id: "rev-a" }),
    ];
    expect(revisionsToFetch(passports, {}, new Set(), "rev-current")).toEqual(["rev-a", "rev-b"]);
  });

  it("паспорт без ревизии не запрашивается", () => {
    const passports = [passport({ reference_revision_id: "" })];
    expect(revisionsToFetch(passports, {}, new Set(), "rev-current")).toEqual([]);
  });
});
