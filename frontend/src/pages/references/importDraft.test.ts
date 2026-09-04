import { describe, expect, it } from "vitest";
import { mergeImportedSections } from "./importDraft";
import type { EconomicsReferenceItem } from "../../types/economics";

function item(code: string): EconomicsReferenceItem {
  return { code, name: code, payload: {}, is_active: true, valid_from: null, valid_to: null, source: "", comment: "", revision: 1 };
}

describe("mergeImportedSections", () => {
  it("заменяет разделы из файла и не трогает остальные", () => {
    let n = 0;
    const draft = {
      sites: [{ ...item("OLD"), row_id: "r1" }],
      rocks: [{ ...item("ROCK"), row_id: "r2" }],
    };
    const result = mergeImportedSections(draft, { sites: [item("NEW_A"), item("NEW_B")] }, () => `id-${++n}`);
    expect(result.replaced).toEqual(["sites"]);
    expect(result.draft.sites.map((row) => row.code)).toEqual(["NEW_A", "NEW_B"]);
    expect(result.draft.sites.map((row) => row.row_id)).toEqual(["id-1", "id-2"]);
    expect(result.draft.rocks).toBe(draft.rocks);
  });

  it("пустой раздел файла очищает раздел черновика", () => {
    const draft = { sites: [{ ...item("OLD"), row_id: "r1" }] };
    const result = mergeImportedSections(draft, { sites: [] }, () => "x");
    expect(result.draft.sites).toEqual([]);
    expect(result.replaced).toEqual(["sites"]);
  });
});
