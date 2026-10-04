// Параметры раскладки, правила зарядов и ВВ живут в формах страницы отдельно
// от документа. После открытия, перехода статуса и ревизии формы берутся из
// паспорта, а паспорт с замороженной проектной частью уходит на сервер как
// хранится — иначе «Сохранить» факта бурения падает на FrozenDesignError
// (аудит замечаний Codex к PR #34, BDX-026).
import { describe, expect, it } from "vitest";
import { DEFAULT_CHARGE_RULES, DEFAULT_PATTERN_PARAMS, emptyDesign, type BlastDesign } from "../../types/design";
import { designReducer, initDesignState, type DesignState } from "./designReducer";
import { designWithParams, hasUnsavedChanges, paramsFromDesign, type DesignParams } from "./designParams";

function passport(extra: Partial<BlastDesign> = {}): BlastDesign {
  return {
    ...emptyDesign(),
    design_id: "a",
    pattern_params: { ...DEFAULT_PATTERN_PARAMS, spacing_a_m: 6, burden_b_m: 5 },
    charge_rules: { ...DEFAULT_CHARGE_RULES, stemming_k: 24 },
    explosive_key: "ГРАНУЛИТ-РП",
    ...extra,
  };
}

const EDITED: DesignParams = {
  patternParams: { ...DEFAULT_PATTERN_PARAMS, spacing_a_m: 7, burden_b_m: 6 },
  chargeRules: { ...DEFAULT_CHARGE_RULES, stemming_k: 30 },
  explosiveKey: "ЭВЕРСИН",
};

describe("paramsFromDesign", () => {
  it("формы — из паспорта", () => {
    const params = paramsFromDesign(passport(), "ЭВЕРСИН");

    expect(params.patternParams).toMatchObject({ spacing_a_m: 6, burden_b_m: 5 });
    expect(params.chargeRules.stemming_k).toBe(24);
    expect(params.explosiveKey).toBe("ГРАНУЛИТ-РП");
  });

  it("чего нет в паспорте — умолчание, а не значение прежнего паспорта", () => {
    const params = paramsFromDesign(passport({ pattern_params: { spacing_a_m: 6 }, charge_rules: {} }), "ЭВЕРСИН");

    expect(params.patternParams).toEqual({ ...DEFAULT_PATTERN_PARAMS, spacing_a_m: 6 });
    expect(params.chargeRules).toEqual(DEFAULT_CHARGE_RULES);
  });

  it("паспорт без ВВ оставляет выбранное в форме", () => {
    expect(paramsFromDesign(passport({ explosive_key: "" }), "ЭВЕРСИН").explosiveKey).toBe("ЭВЕРСИН");
  });
});

describe("designWithParams", () => {
  it("черновик уходит с формами страницы", () => {
    const payload = designWithParams(passport(), EDITED, false);

    expect(payload.pattern_params).toEqual(EDITED.patternParams);
    expect(payload.charge_rules).toEqual(EDITED.chargeRules);
    expect(payload.explosive_key).toBe("ЭВЕРСИН");
  });

  it("утверждённый паспорт уходит с проектной частью как хранится, даже если формы разошлись", () => {
    const approved = passport({ lifecycle_status: "approved" });
    const payload = designWithParams(approved, EDITED, true);

    expect(payload.pattern_params).toBe(approved.pattern_params);
    expect(payload.charge_rules).toBe(approved.charge_rules);
    expect(payload.explosive_key).toBe("ГРАНУЛИТ-РП");
  });

  it("утверждённый паспорт без части ключей не дополняется умолчаниями", () => {
    const old = passport({ lifecycle_status: "approved", pattern_params: { spacing_a_m: 6, burden_b_m: 5 }, charge_rules: {}, explosive_key: "" });
    const payload = designWithParams(old, paramsFromDesign(old, "ЭВЕРСИН"), true);

    expect(payload.pattern_params).toEqual({ spacing_a_m: 6, burden_b_m: 5 });
    expect(payload.charge_rules).toEqual({});
    expect(payload.explosive_key).toBe("");
  });
});

describe("hasUnsavedChanges — переход статуса только у сохранённого паспорта", () => {
  function opened(design: BlastDesign): DesignState {
    return designReducer(initDesignState(emptyDesign()), { type: "LOAD", design });
  }

  it("только что открытый паспорт с формами из него — правок нет", () => {
    const state = opened(passport());
    expect(hasUnsavedChanges(state, paramsFromDesign(state.present, "ЭВЕРСИН"), false)).toBe(false);
  });

  it("правка документа — есть; отмена до сохранённого — снова нет", () => {
    const state = opened(passport());
    const params = paramsFromDesign(state.present, "ЭВЕРСИН");
    const withEdit = designReducer(state, { type: "SET_WATER_TABLE", water_table_z_m: 405 });

    expect(hasUnsavedChanges(withEdit, params, false)).toBe(true);
    expect(hasUnsavedChanges(designReducer(withEdit, { type: "UNDO" }), params, false)).toBe(false);
  });

  it("правка шага сетки в форме — есть", () => {
    const state = opened(passport());
    const params = paramsFromDesign(state.present, "ЭВЕРСИН");
    const edited = { ...params, patternParams: { ...params.patternParams, spacing_a_m: 6.5 } };

    expect(hasUnsavedChanges(state, edited, false)).toBe(true);
  });

  it("после ответа сохранения — нет", () => {
    const state = opened(passport());
    const params = { ...paramsFromDesign(state.present, "ЭВЕРСИН"), explosiveKey: "ЭВЕРСИН" };
    const withEdit = designReducer(state, { type: "SET_NAME", name: "Блок A, правка" });
    const echo = designWithParams(withEdit.present, params, false);

    const saved = designReducer(withEdit, { type: "SAVED", design: { ...echo, revision: 3 } });
    expect(hasUnsavedChanges(saved, params, false)).toBe(false);
  });

  it("умолчания форм поверх старого паспорта без части ключей и без ВВ — не правка", () => {
    const state = opened(passport({ pattern_params: { spacing_a_m: 6 }, charge_rules: {}, explosive_key: "" }));
    expect(hasUnsavedChanges(state, paramsFromDesign(state.present, "ЭВЕРСИН"), false)).toBe(false);
  });

  it("утверждённый паспорт: разошедшиеся формы не в счёт (на сервер не уйдут), несохранённый факт бурения — в счёт", () => {
    const state = opened(passport({ lifecycle_status: "approved" }));

    expect(hasUnsavedChanges(state, EDITED, true)).toBe(false);
    const withFact = designReducer(state, {
      type: "UPSERT_AS_DRILLED",
      hole: { design_hole_id: "h1" } as BlastDesign["as_drilled_holes"][number],
    });
    expect(hasUnsavedChanges(withFact, EDITED, true)).toBe(true);
  });
});
