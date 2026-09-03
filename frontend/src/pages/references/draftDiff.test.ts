import { describe, expect, it } from "vitest";
import { countDraftChanges } from "./draftDiff";
import type { DraftSections } from "./importDraft";
import type { EconomicsReferenceItem } from "../../types/economics";

function item(code: string, payload: Record<string, unknown> = {}): EconomicsReferenceItem {
  return {
    code,
    name: code,
    payload,
    is_active: true,
    valid_from: null,
    valid_to: null,
    source: "",
    comment: "",
    revision: 1,
  };
}

function published(entries: Array<[string, EconomicsReferenceItem]>) {
  return new Map(entries);
}

describe("countDraftChanges", () => {
  const draft: DraftSections = {
    sites: [{ ...item("SITE_A"), row_id: "r1" }],
    rocks: [{ ...item("ROCK_A"), row_id: "r2" }],
  };

  it("не находит изменений в черновике, совпадающем с ревизией", () => {
    const diff = countDraftChanges(draft, published([
      ["sites::SITE_A", item("SITE_A")],
      ["rocks::ROCK_A", item("ROCK_A")],
    ]));
    expect(diff.changed.size).toBe(0);
    expect(diff.removed).toEqual([]);
  });

  it("считает изменённые и добавленные строки", () => {
    const diff = countDraftChanges(draft, published([["sites::SITE_A", item("SITE_A", { a: 1 })]]));
    expect([...diff.changed].sort()).toEqual(["r1", "r2"]);
    expect(diff.removed).toEqual([]);
  });

  it("не видит различий там, где отличается только запись числа", () => {
    const diff = countDraftChanges(
      { sites: [{ ...item("SITE_A", { a: "0.10" }), row_id: "r1" }] },
      published([["sites::SITE_A", item("SITE_A", { a: 0.1 })]]),
    );
    expect(diff.changed.size).toBe(0);
  });

  it("находит записи ревизии, которых больше нет в черновике", () => {
    const diff = countDraftChanges(draft, published([
      ["sites::SITE_A", item("SITE_A")],
      ["sites::SITE_B", item("SITE_B")],
      ["rocks::ROCK_A", item("ROCK_A")],
      ["rocks::ROCK_B", item("ROCK_B")],
    ]));
    expect(diff.changed.size).toBe(0);
    expect(diff.removed.sort()).toEqual(["rocks::ROCK_B", "sites::SITE_B"]);
  });
});
