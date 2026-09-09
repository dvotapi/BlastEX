import { describe, expect, it } from "vitest";

import {
  MAX_VARIANTS,
  addVariant,
  duplicateVariant,
  makeVariant,
  patchVariant,
  removeVariant,
  renameVariant,
  type Variant,
} from "./variants";
import type { ModelParameters } from "../../types/blockEconomics";

function baseParameters(): ModelParameters {
  return {
    package_code: "DRILL_AND_BLAST",
    site_code: "SITE_MAIN",
    reference_revision_id: "",
    unit_plan_volume_m3: "600000",
    rig_code: "RIG_JK830",
    rig_plan_shifts: "40",
    szm_code: "SZM_12T",
    delivery_truck_code: "TRUCK_3T",
    emulsion_truck_code: null,
    machine_plan_shifts: {},
    crew: [],
    services: [],
    drilling_executor: "OWN",
    subcontract_rate_code: null,
    subcontract_rate_rub: null,
    nomenclature: {},
    electric_detonators_qty: "0",
    overhead_rate: null,
    target_margin_rate: null,
    vat_rate: null,
  };
}

function makeVariants(): Variant[] {
  return [makeVariant("Вариант 1", baseParameters())];
}

describe("варианты расчёта", () => {
  it("дублирует активный вариант с новым именем и своим набором параметров", () => {
    const [base] = makeVariants();
    const next = duplicateVariant([base], base.id);

    expect(next).toHaveLength(2);
    expect(next[1].name).toBe("Вариант 2");
    expect(next[1].id).not.toBe(base.id);
    expect(next[1].parameters).toEqual(base.parameters);
    expect(next[1].parameters).not.toBe(base.parameters);
  });

  it("не даёт больше четырёх", () => {
    const four = [1, 2, 3, 4].map((n) => ({ ...makeVariants()[0], id: `v${n}` }));
    expect(duplicateVariant(four, "v1")).toHaveLength(4);
  });

  it("неизвестный id ничего не меняет", () => {
    const [base] = makeVariants();
    expect(duplicateVariant([base], "missing")).toEqual([base]);
  });

  it("последний вариант не удаляется", () => {
    const [base] = makeVariants();
    expect(removeVariant([base], base.id)).toHaveLength(1);
  });

  it("удаляет один из нескольких", () => {
    const [base] = makeVariants();
    const withCopy = duplicateVariant([base], base.id);
    expect(removeVariant(withCopy, base.id).map((v) => v.id)).toEqual([withCopy[1].id]);
  });

  it("переименовывает по id, не трогая остальные", () => {
    const [base] = makeVariants();
    const withCopy = duplicateVariant([base], base.id);
    const renamed = renameVariant(withCopy, base.id, "БВР сухие");

    expect(renamed[0].name).toBe("БВР сухие");
    expect(renamed[1].name).toBe(withCopy[1].name);
  });

  it("правит параметры одного варианта, не задевая соседние", () => {
    const [base] = makeVariants();
    const withCopy = duplicateVariant([base], base.id);
    const patched = patchVariant(withCopy, base.id, { unit_plan_volume_m3: "400000" });

    expect(patched[0].parameters.unit_plan_volume_m3).toBe("400000");
    expect(patched[1].parameters).toEqual(base.parameters);
  });

  it("MAX_VARIANTS совпадает с пределом бэкенда", () => {
    expect(MAX_VARIANTS).toBe(4);
  });

  it("добавление сверх предела не растит список", () => {
    const four = [1, 2, 3, 4].map((n) => ({ ...makeVariants()[0], id: `v${n}` }));
    expect(addVariant(four, makeVariant("Пятый", baseParameters()))).toHaveLength(4);
  });
});
