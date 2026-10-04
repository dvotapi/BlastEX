// История отмены принадлежит одному паспорту: открытие другого паспорта,
// нового, ревизии или переход статуса её сбрасывают, ответ сохранения того же
// паспорта — нет (аудит замечаний Codex к PR #34, BDX-026).
import { describe, expect, it } from "vitest";
import { emptyDesign, type BlastDesign } from "../../types/design";
import { designReducer, initDesignState, type DesignState } from "./designReducer";

function passport(extra: Partial<BlastDesign> = {}): BlastDesign {
  return { ...emptyDesign(), design_id: "a", name: "Блок A", revision: 2, updated_at: "2026-10-01T10:00:00Z", ...extra };
}

function edited(state: DesignState, ...names: string[]): DesignState {
  return names.reduce((current, name) => designReducer(current, { type: "SET_NAME", name }), state);
}

describe("LOAD сбрасывает историю отмены", () => {
  it("открыть другой паспорт: Ctrl+Z не возвращает прежний", () => {
    const withEdits = edited(initDesignState(passport()), "Блок A, правка 1", "Блок A, правка 2");
    const loaded = designReducer(withEdits, { type: "LOAD", design: passport({ design_id: "b", name: "Блок B" }) });

    expect(loaded.past).toEqual([]);
    const undone = designReducer(loaded, { type: "UNDO" });
    expect(undone.present.design_id).toBe("b");
    expect(undone.present.name).toBe("Блок B");
  });

  it("стек повтора тоже очищается", () => {
    const undone = designReducer(edited(initDesignState(passport()), "Блок A, правка"), { type: "UNDO" });
    expect(undone.future).toHaveLength(1);

    const loaded = designReducer(undone, { type: "LOAD", design: passport({ design_id: "b" }) });
    expect(loaded.future).toEqual([]);
    expect(designReducer(loaded, { type: "REDO" }).present.design_id).toBe("b");
  });

  it("новый паспорт поверх несохранённого — тоже другой документ, хотя design_id у обоих пустой", () => {
    const unsaved = edited(initDesignState(emptyDesign()), "Черновик без сохранения");
    const fresh = designReducer(unsaved, { type: "LOAD", design: emptyDesign() });

    expect(fresh.past).toEqual([]);
    expect(designReducer(fresh, { type: "UNDO" }).present.name).toBe("Новый паспорт");
  });

  it("тот же паспорт с сервера после смены статуса: отмена не возвращает черновик", () => {
    const draft = edited(initDesignState(passport()), "Блок A, правка");
    const inReview = designReducer(draft, { type: "LOAD", design: passport({ lifecycle_status: "in_review" }) });

    expect(inReview.past).toEqual([]);
    expect(designReducer(inReview, { type: "UNDO" }).present.lifecycle_status).toBe("in_review");
  });
});

describe("SAVED — ответ сохранения того же паспорта", () => {
  it("история правок остаётся: после сохранения правку можно отменить", () => {
    const withEdits = edited(initDesignState(passport()), "Блок A, правка 1", "Блок A, правка 2");
    const saved = designReducer(withEdits, {
      type: "SAVED",
      design: passport({ name: "Блок A, правка 2", revision: 3, updated_at: "2026-10-04T12:00:00Z" }),
    });

    expect(saved.past).toHaveLength(2);
    const undone = designReducer(saved, { type: "UNDO" });
    expect(undone.present.name).toBe("Блок A, правка 1");
  });

  it("отмена не возвращает служебные поля паспорта до сохранения", () => {
    const withEdit = edited(initDesignState(passport()), "Блок A, правка");
    const saved = designReducer(withEdit, {
      type: "SAVED",
      design: passport({ name: "Блок A, правка", revision: 3, updated_at: "2026-10-04T12:00:00Z", designed_sha256: "f00d" }),
    });

    const undone = designReducer(saved, { type: "UNDO" });
    expect(undone.present).toMatchObject({ name: "Блок A", revision: 3, updated_at: "2026-10-04T12:00:00Z", designed_sha256: "f00d" });
    const redone = designReducer(undone, { type: "REDO" });
    expect(redone.present).toMatchObject({ name: "Блок A, правка", revision: 3, designed_sha256: "f00d" });
  });

  it("первое сохранение нового паспорта: отмена не стирает design_id (иначе «Сохранить» создаст копию)", () => {
    const unsaved = edited(initDesignState(emptyDesign()), "Блок 7");
    const created = designReducer(unsaved, {
      type: "SAVED",
      design: { ...emptyDesign(), design_id: "d-7", name: "Блок 7", revision: 1, designed_sha256: "c0de" },
    });

    const undone = designReducer(created, { type: "UNDO" });
    expect(undone.present.name).toBe("Новый паспорт");
    expect(undone.present.design_id).toBe("d-7");
    expect(undone.present.revision).toBe(1);
  });
});

describe("saved — паспорт, как он лежит на сервере", () => {
  it("LOAD и SAVED запоминают версию сервера, правки и отмена — нет", () => {
    const loaded = designReducer(initDesignState(emptyDesign()), { type: "LOAD", design: passport() });
    expect(loaded.saved).toBe(loaded.present);

    const withEdit = edited(loaded, "Блок A, правка");
    expect(withEdit.saved).toBe(loaded.saved);
    expect(designReducer(withEdit, { type: "UNDO" }).saved).toBe(loaded.saved);

    const saved = designReducer(withEdit, { type: "SAVED", design: passport({ name: "Блок A, правка", revision: 3 }) });
    expect(saved.saved).toBe(saved.present);
  });
});

describe("ответ на действие с паспортом, который уже закрыт", () => {
  it("сохранение A пришло после открытия B — ответ отбрасывается, история B не получает design_id A", () => {
    const a = designReducer(initDesignState(emptyDesign()), { type: "LOAD", design: passport() });
    const base = a.saved;
    const b = edited(designReducer(a, { type: "LOAD", design: passport({ design_id: "b", name: "Блок B" }) }), "Блок B, правка");

    const late = designReducer(b, { type: "SAVED", design: passport({ revision: 3 }), base });

    expect(late).toBe(b);
    expect(designReducer(late, { type: "UNDO" }).present.design_id).toBe("b");
  });

  it("смена статуса A пришла после открытия B — B остаётся на экране", () => {
    const a = designReducer(initDesignState(emptyDesign()), { type: "LOAD", design: passport() });
    const b = designReducer(a, { type: "LOAD", design: passport({ design_id: "b" }) });

    const late = designReducer(b, { type: "LOAD", design: passport({ lifecycle_status: "in_review" }), base: a.saved });
    expect(late.present.design_id).toBe("b");
  });

  it("ответ на действие с открытым паспортом применяется", () => {
    const a = edited(designReducer(initDesignState(emptyDesign()), { type: "LOAD", design: passport() }), "Блок A, правка");
    const saved = designReducer(a, { type: "SAVED", design: passport({ name: "Блок A, правка", revision: 3 }), base: a.saved });
    expect(saved.present.revision).toBe(3);
  });
});
