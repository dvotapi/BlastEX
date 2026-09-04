import { describe, expect, it } from "vitest";
import { applyDeltaEntries, deltaSummary } from "./publicDelta";
import type { EconomicsReferenceItem, PublicDeltaEntry } from "../../types/economics";

function item(code: string, name = code): EconomicsReferenceItem {
  return {
    code,
    name,
    payload: {},
    is_active: true,
    valid_from: null,
    valid_to: null,
    source: "project1.public",
    comment: "",
    revision: 1,
  };
}

function entry(
  kind: PublicDeltaEntry["kind"],
  section: string,
  code: string,
  overrides: Partial<PublicDeltaEntry> = {},
): PublicDeltaEntry {
  return {
    kind,
    section,
    public_table: section,
    public_id: 1,
    code,
    name: code,
    item: item(code),
    changes: [],
    ...overrides,
  };
}

describe("applyDeltaEntries", () => {
  it("добавляет новую запись в раздел и считает применённые", () => {
    let n = 0;
    const draft = { sites: [{ ...item("SITE_LOM"), row_id: "r1" }] };
    const result = applyDeltaEntries(draft, [entry("new", "sites", "PUB_SITE_2")], () => `id-${++n}`);
    expect(result.applied).toBe(1);
    expect(result.draft.sites.map((row) => row.code)).toEqual(["SITE_LOM", "PUB_SITE_2"]);
    expect(result.draft.sites[1].row_id).toBe("id-1");
  });

  it("создаёт раздел, которого нет в черновике", () => {
    const result = applyDeltaEntries({}, [entry("new", "counterparties", "PUB_C_1")], () => "id-1");
    expect(result.applied).toBe(1);
    expect(result.draft.counterparties.map((row) => row.code)).toEqual(["PUB_C_1"]);
  });

  it("не дублирует запись, если код уже есть в разделе", () => {
    const draft = { sites: [{ ...item("SITE_LOM", "старое имя"), row_id: "r1" }] };
    const result = applyDeltaEntries(
      draft,
      [entry("new", "sites", "SITE_LOM", { item: item("SITE_LOM", "новое имя") })],
      () => "id-1",
    );
    expect(result.applied).toBe(1);
    expect(result.draft.sites).toHaveLength(1);
    expect(result.draft.sites[0].name).toBe("новое имя");
    expect(result.draft.sites[0].row_id).toBe("r1");
  });

  it("для changed заменяет запись и сохраняет row_id", () => {
    const draft = {
      sites: [
        { ...item("SITE_A"), row_id: "r1" },
        { ...item("SITE_LOM", "старое имя"), row_id: "r2" },
      ],
    };
    const changed = entry("changed", "sites", "SITE_LOM", {
      item: { ...item("SITE_LOM", "Ломоватский карьер"), payload: { mineral_type: "нерудные материалы" } },
      changes: [{ key: "payload.mineral_type", old: "иной", new: "нерудные материалы" }],
    });
    const result = applyDeltaEntries(draft, [changed], () => "id-новый");
    expect(result.applied).toBe(1);
    expect(result.draft.sites).toHaveLength(2);
    expect(result.draft.sites[1].row_id).toBe("r2");
    expect(result.draft.sites[1].name).toBe("Ломоватский карьер");
    expect(result.draft.sites[1].payload).toEqual({ mineral_type: "нерудные материалы" });
    expect(result.draft.sites[0]).toBe(draft.sites[0]);
  });

  it("для deactivated заменяет запись с тем же кодом", () => {
    const draft = { rocks: [{ ...item("ROCK"), row_id: "r1" }] };
    const gone = entry("deactivated", "rocks", "ROCK", { item: { ...item("ROCK"), is_active: false } });
    const result = applyDeltaEntries(draft, [gone], () => "id-1");
    expect(result.applied).toBe(1);
    expect(result.draft.rocks[0].is_active).toBe(false);
    expect(result.draft.rocks[0].row_id).toBe("r1");
  });

  it("changed без записи с таким кодом добавляет её как новую", () => {
    const result = applyDeltaEntries({ sites: [] }, [entry("changed", "sites", "SITE_LOM")], () => "id-1");
    expect(result.applied).toBe(1);
    expect(result.draft.sites.map((row) => row.code)).toEqual(["SITE_LOM"]);
    expect(result.draft.sites[0].row_id).toBe("id-1");
  });

  it("не трогает исходный черновик и разделы без записей разницы", () => {
    const draft = {
      sites: [{ ...item("SITE_LOM"), row_id: "r1" }],
      rocks: [{ ...item("ROCK"), row_id: "r2" }],
    };
    const result = applyDeltaEntries(draft, [entry("new", "sites", "PUB_SITE_2")], () => "id-1");
    expect(draft.sites).toHaveLength(1);
    expect(result.draft.rocks).toBe(draft.rocks);
  });

  it("пустой список записей ничего не меняет", () => {
    const draft = { sites: [{ ...item("SITE_LOM"), row_id: "r1" }] };
    const result = applyDeltaEntries(draft, [], () => "id-1");
    expect(result.applied).toBe(0);
    expect(result.draft.sites).toBe(draft.sites);
  });
});

describe("deltaSummary", () => {
  it("склоняет числа по-русски", () => {
    expect(deltaSummary({ new: 1, changed: 2, deactivated: 5 })).toBe(
      "Из project1: 1 новая, 2 изменённые, 5 деактивированных",
    );
  });

  it("нули тоже показывает — плашку прячет страница, а не текст", () => {
    expect(deltaSummary({ new: 0, changed: 0, deactivated: 0 })).toBe(
      "Из project1: 0 новых, 0 изменённых, 0 деактивированных",
    );
  });
});
