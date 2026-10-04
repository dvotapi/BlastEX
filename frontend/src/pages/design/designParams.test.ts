// Параметры раскладки, правила зарядов и ВВ живут в формах страницы отдельно
// от документа. После загрузки паспорта формы берутся из него; на сервер
// паспорт уходит с тем, что в его статусе можно править, а замороженные части
// — как хранятся. Иначе «Сохранить» факта бурения падает на FrozenDesignError
// (аудит замечаний Codex к PR #34, BDX-026).
import { describe, expect, it } from "vitest";
import { DEFAULT_CHARGE_RULES, DEFAULT_PATTERN_PARAMS, emptyDesign, type AsDrilledHole, type BlastDesign } from "../../types/design";
import { designReducer, initDesignState, type DesignAction, type DesignState } from "./designReducer";
import { designWithParams, hasUnsavedChanges, paramsFromDesign, type DesignParams } from "./designParams";

const DEFAULT_EXPLOSIVE = "ГРАНУЛИТ-РП";

function passport(extra: Partial<BlastDesign> = {}): BlastDesign {
  return {
    ...emptyDesign(),
    design_id: "a",
    holes: [{ id: "h1", enabled: true } as BlastDesign["holes"][number]],
    pattern_params: { ...DEFAULT_PATTERN_PARAMS, spacing_a_m: 6, burden_b_m: 5 },
    charge_rules: { ...DEFAULT_CHARGE_RULES, stemming_k: 24 },
    explosive_key: "ЭВЕРСИН",
    ...extra,
  };
}

const EDITED: DesignParams = {
  patternParams: { ...DEFAULT_PATTERN_PARAMS, spacing_a_m: 7, burden_b_m: 6 },
  chargeRules: { ...DEFAULT_CHARGE_RULES, stemming_k: 30 },
  explosiveKey: "АНФО",
};

const FACT = { design_hole_id: "h1" } as AsDrilledHole;

function opened(design: BlastDesign, ...actions: DesignAction[]): DesignState {
  return actions.reduce(designReducer, designReducer(initDesignState(emptyDesign()), { type: "LOAD", design }));
}

function formsOf(state: DesignState): DesignParams {
  return paramsFromDesign(state.saved, DEFAULT_EXPLOSIVE);
}

describe("paramsFromDesign", () => {
  it("формы — из паспорта", () => {
    const params = paramsFromDesign(passport(), DEFAULT_EXPLOSIVE);

    expect(params.patternParams).toMatchObject({ spacing_a_m: 6, burden_b_m: 5 });
    expect(params.chargeRules.stemming_k).toBe(24);
    expect(params.explosiveKey).toBe("ЭВЕРСИН");
  });

  it("чего нет в паспорте — умолчание, а не значение прежнего паспорта", () => {
    const params = paramsFromDesign(passport({ pattern_params: { spacing_a_m: 6 }, charge_rules: {}, explosive_key: "" }), DEFAULT_EXPLOSIVE);

    expect(params.patternParams).toEqual({ ...DEFAULT_PATTERN_PARAMS, spacing_a_m: 6 });
    expect(params.chargeRules).toEqual(DEFAULT_CHARGE_RULES);
    expect(params.explosiveKey).toBe(DEFAULT_EXPLOSIVE);
  });
});

describe("designWithParams", () => {
  it("черновик уходит с формами страницы", () => {
    const payload = designWithParams(opened(passport()), EDITED);

    expect(payload.pattern_params).toEqual(EDITED.patternParams);
    expect(payload.charge_rules).toEqual(EDITED.chargeRules);
    expect(payload.explosive_key).toBe("АНФО");
  });

  it("утверждённый паспорт: проектная часть как хранится, даже если формы разошлись", () => {
    const state = opened(passport({ lifecycle_status: "approved" }));
    const payload = designWithParams(state, EDITED);

    expect(payload.pattern_params).toEqual(state.saved.pattern_params);
    expect(payload.charge_rules).toEqual(state.saved.charge_rules);
    expect(payload.explosive_key).toBe("ЭВЕРСИН");
  });

  it("утверждённый паспорт без части ключей не дополняется умолчаниями", () => {
    const old = opened(passport({ lifecycle_status: "approved", pattern_params: { spacing_a_m: 6, burden_b_m: 5 }, charge_rules: {}, explosive_key: "" }));
    const payload = designWithParams(old, formsOf(old));

    expect(payload.pattern_params).toEqual({ spacing_a_m: 6, burden_b_m: 5 });
    expect(payload.charge_rules).toEqual({});
    expect(payload.explosive_key).toBe("");
  });

  it("утверждённый паспорт: факт бурения уходит, проскочившая правка проекта — нет", () => {
    const state = opened(
      passport({ lifecycle_status: "approved" }),
      { type: "SET_HOLES_ENABLED", ids: ["h1"], enabled: false },
      { type: "UPSERT_AS_DRILLED", hole: FACT },
    );
    const payload = designWithParams(state, formsOf(state));

    expect(payload.holes[0].enabled).toBe(true);
    expect(payload.as_drilled_holes).toEqual([FACT]);
  });

  it("на проверке правится только название: факт исполнения уходит как хранится", () => {
    const state = opened(passport({ lifecycle_status: "in_review" }), { type: "UPSERT_AS_DRILLED", hole: FACT }, { type: "SET_NAME", name: "Блок A, уточнено" });
    const payload = designWithParams(state, formsOf(state));

    expect(payload.as_drilled_holes).toEqual([]);
    expect(payload.name).toBe("Блок A, уточнено");
  });
});

describe("hasUnsavedChanges — статус и ревизия берутся из сохранённой версии", () => {
  it("только что открытый паспорт с формами из него — правок нет", () => {
    const state = opened(passport());
    expect(hasUnsavedChanges(state, formsOf(state), DEFAULT_EXPLOSIVE)).toBe(false);
  });

  it("правка документа — есть; отмена до сохранённого — снова нет", () => {
    const state = opened(passport(), { type: "SET_WATER_TABLE", water_table_z_m: 405 });

    expect(hasUnsavedChanges(state, formsOf(state), DEFAULT_EXPLOSIVE)).toBe(true);
    expect(hasUnsavedChanges(designReducer(state, { type: "UNDO" }), formsOf(state), DEFAULT_EXPLOSIVE)).toBe(false);
  });

  it("правка шага сетки в форме — есть", () => {
    const state = opened(passport());
    const forms = formsOf(state);

    expect(hasUnsavedChanges(state, { ...forms, patternParams: { ...forms.patternParams, spacing_a_m: 6.5 } }, DEFAULT_EXPLOSIVE)).toBe(true);
  });

  it("после ответа сохранения — нет", () => {
    const withEdit = opened(passport(), { type: "SET_NAME", name: "Блок A, правка" });
    const forms = { ...formsOf(withEdit), explosiveKey: "АНФО" };
    const echo = designWithParams(withEdit, forms);

    const saved = designReducer(withEdit, { type: "SAVED", design: { ...echo, revision: 3 } });
    expect(hasUnsavedChanges(saved, forms, DEFAULT_EXPLOSIVE)).toBe(false);
  });

  it("умолчания форм поверх старого паспорта без части ключей и без ВВ — не правка", () => {
    const state = opened(passport({ pattern_params: { spacing_a_m: 6 }, charge_rules: {}, explosive_key: "" }));
    expect(hasUnsavedChanges(state, formsOf(state), DEFAULT_EXPLOSIVE)).toBe(false);
  });

  it("паспорт без ВВ: выбранное в форме вещество, отличное от умолчания, — правка", () => {
    const state = opened(passport({ explosive_key: "" }));
    expect(hasUnsavedChanges(state, { ...formsOf(state), explosiveKey: "АНФО" }, DEFAULT_EXPLOSIVE)).toBe(true);
  });

  it("утверждённый паспорт: разошедшиеся формы и проскочившая правка проекта не в счёт, несохранённый факт — в счёт", () => {
    const state = opened(passport({ lifecycle_status: "approved" }), { type: "SET_HOLES_ENABLED", ids: ["h1"], enabled: false });

    expect(hasUnsavedChanges(state, EDITED, DEFAULT_EXPLOSIVE)).toBe(false);
    const withFact = designReducer(state, { type: "UPSERT_AS_DRILLED", hole: FACT });
    expect(hasUnsavedChanges(withFact, EDITED, DEFAULT_EXPLOSIVE)).toBe(true);
  });

  it("закрытый паспорт: сохранить нечего, значит и несохранённого нет", () => {
    const state = opened(passport({ lifecycle_status: "closed" }), { type: "UPSERT_AS_DRILLED", hole: FACT }, { type: "SET_NAME", name: "другое" });
    expect(hasUnsavedChanges(state, EDITED, DEFAULT_EXPLOSIVE)).toBe(false);
  });
});
