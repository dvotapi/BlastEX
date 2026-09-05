import { describe, expect, it } from "vitest";
import {
  applyDeltaEntries,
  deltaSummary,
  fieldValueText,
  mergePendingLinks,
  publishedRows,
  renamedLinks,
  resolvePendingLinks,
} from "./publicDelta";
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

  it("нулевые счётчики опускает", () => {
    expect(deltaSummary({ new: 3, changed: 0, deactivated: 0 })).toBe("Из project1: 3 новые");
    expect(deltaSummary({ new: 0, changed: 0, deactivated: 2 })).toBe(
      "Из project1: 2 деактивированные",
    );
  });

  it("без расхождений подписи нет", () => {
    expect(deltaSummary({ new: 0, changed: 0, deactivated: 0 })).toBe("");
  });
});

describe("fieldValueText", () => {
  it("пустое значение читается прочерком", () => {
    expect(fieldValueText(null)).toBe("—");
    expect(fieldValueText(undefined)).toBe("—");
    expect(fieldValueText("")).toBe("—");
  });

  it("логическое значение — да или нет", () => {
    expect(fieldValueText(true)).toBe("да");
    expect(fieldValueText(false)).toBe("нет");
  });

  it("список и объект называются по-русски, а не JSON-ом", () => {
    expect(fieldValueText([1, 2, 3])).toBe("список (3)");
    expect(fieldValueText([])).toBe("список (0)");
    expect(fieldValueText({ a: 1 })).toBe("объект");
  });

  it("числа и строки показываются как есть", () => {
    expect(fieldValueText(220)).toBe("220");
    expect(fieldValueText("ЛОМ")).toBe("ЛОМ");
  });
});

describe("resolvePendingLinks", () => {
  const link = { row_id: "r1", section: "sites", public_table: "sites", public_id: 7 };

  it("берёт код из черновика — переименование записи уводит связь за собой", () => {
    const draft = { sites: [{ ...item("SITE_ЛОМ"), row_id: "r1" }] };
    expect(resolvePendingLinks(draft, [link])).toEqual([
      { section: "sites", code: "SITE_ЛОМ", public_table: "sites", public_id: 7 },
    ]);

    const renamed = { sites: [{ ...item("SITE_НОВЫЙ"), row_id: "r1" }] };
    expect(resolvePendingLinks(renamed, [link])[0].code).toBe("SITE_НОВЫЙ");
  });

  it("связь удалённой записи отбрасывается", () => {
    expect(resolvePendingLinks({ sites: [] }, [link])).toEqual([]);
    expect(resolvePendingLinks({}, [link])).toEqual([]);
  });

  it("запись с пустым кодом ещё не связывается", () => {
    const draft = { sites: [{ ...item(""), row_id: "r1" }] };
    expect(resolvePendingLinks(draft, [link])).toEqual([]);
  });

  it("несколько связей сохраняют порядок", () => {
    const draft = {
      sites: [{ ...item("SITE_A"), row_id: "r1" }],
      rocks: [{ ...item("ROCK_B"), row_id: "r2" }],
    };
    const resolved = resolvePendingLinks(draft, [
      link,
      { row_id: "r2", section: "rocks", public_table: "rock_types", public_id: 3 },
    ]);
    expect(resolved.map((entry) => entry.code)).toEqual(["SITE_A", "ROCK_B"]);
  });
});

describe("mergePendingLinks", () => {
  const first = { row_id: "r1", section: "sites", public_table: "sites", public_id: 7 };

  it("одна строка журнала не может быть связана дважды", () => {
    const moved = { row_id: "r2", section: "sites", public_table: "sites", public_id: 7 };
    expect(mergePendingLinks([first], [moved])).toEqual([moved]);
  });

  it("у записи справочника остаётся одна связь", () => {
    const other = { row_id: "r1", section: "sites", public_table: "sites", public_id: 9 };
    expect(mergePendingLinks([first], [other])).toEqual([other]);
  });

  it("связи разных записей копятся", () => {
    const second = { row_id: "r2", section: "rocks", public_table: "rock_types", public_id: 1 };
    expect(mergePendingLinks([first], [second])).toEqual([first, second]);
    expect(mergePendingLinks([first], [])).toEqual([first]);
  });
});

describe("renamedLinks", () => {
  const stored = [{ section: "sites", code: "SITE_ЛОМ", public_table: "sites", public_id: 7 }];
  const published = [{ row_id: "r1", section: "sites", code: "SITE_ЛОМ" }];

  it("переименованная запись уводит сохранённую связь на новый код", () => {
    const draft = { sites: [{ ...item("SITE_НОВЫЙ"), row_id: "r1" }] };
    expect(renamedLinks(stored, published, draft)).toEqual([
      { row_id: "r1", section: "sites", public_table: "sites", public_id: 7 },
    ]);
  });

  it("код не менялся — переносить нечего", () => {
    const draft = { sites: [{ ...item("SITE_ЛОМ"), row_id: "r1" }] };
    expect(renamedLinks(stored, published, draft)).toEqual([]);
  });

  it("запись без сохранённой связи не даёт связи", () => {
    const draft = { sites: [{ ...item("SITE_ДРУГОЙ"), row_id: "r2" }] };
    const rows = [{ row_id: "r2", section: "sites", code: "SITE_ИНОЙ" }];
    expect(renamedLinks(stored, rows, draft)).toEqual([]);
  });

  it("исчезнувшая или обнулённая запись связь не переносит", () => {
    expect(renamedLinks(stored, published, { sites: [] })).toEqual([]);
    expect(renamedLinks(stored, published, { sites: [{ ...item(""), row_id: "r1" }] })).toEqual([]);
  });
});

describe("publishedRows", () => {
  it("перечисляет строки ревизии разделами и кодами", () => {
    const draft = {
      sites: [{ ...item("SITE_A"), row_id: "r1" }],
      rocks: [{ ...item("ROCK_B"), row_id: "r2" }],
    };
    expect(publishedRows(draft)).toEqual([
      { row_id: "r1", section: "sites", code: "SITE_A" },
      { row_id: "r2", section: "rocks", code: "ROCK_B" },
    ]);
  });
});
