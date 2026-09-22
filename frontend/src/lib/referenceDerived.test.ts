import { describe, expect, it } from "vitest";
import { derivedHints, shiftHours, vatRate, type DerivedContext } from "./referenceDerived";

function context(sections: DerivedContext["sections"]): DerivedContext {
  return { sections };
}

const RATES = {
  code: "ORG_RATES_DEFAULT",
  name: "Ставки организации",
  is_active: true,
  payload: { vat_rate: "0.20", shift_hours: "11" },
};

describe("подсказки должности", () => {
  const ctx = context({
    organization_rates: [RATES],
    labor_rates: [
      {
        code: "RATE_BLASTER",
        name: "Взрывник",
        is_active: true,
        payload: { position_code: "POSITION_BLASTER", fixed_monthly_rub: "55000" },
      },
    ],
  });

  it("считает оклад и смены на один взрыв по нормативу", () => {
    const hints = derivedHints(
      "positions",
      "POSITION_BLASTER",
      { norm_shifts_per_month: "21", norm_operations_per_month: "10" },
      ctx,
    );
    expect(hints).toHaveLength(1);
    expect(hints[0].label).toBe("На один взрыв по нормативу");
    expect(hints[0].value.replace(/\s/g, " ")).toBe("5 500 ₽ · 2,1 смены");
  });

  it("без норматива операций подсказки нет", () => {
    expect(derivedHints("positions", "POSITION_BLASTER", { norm_shifts_per_month: "21" }, ctx)).toEqual([]);
  });
});

describe("подсказки условия бурения", () => {
  const ctx = context({
    organization_rates: [RATES],
    equipment_types: [
      {
        code: "JK830",
        name: "JK 830-3",
        is_active: true,
        payload: { kind: "DRILL_RIG", norm_shifts_per_month: "40" },
      },
    ],
  });

  it("коммерческая скорость = техническая × производительные часы смены", () => {
    const hints = derivedHints(
      "drilling_conditions",
      "JK830_GRANITE",
      { equipment_type_code: "JK830", tech_speed_m_per_h: "12", unproductive_h_per_shift: "1" },
      ctx,
    );
    expect(hints[0].label).toBe("Коммерческая скорость");
    expect(hints[0].value.replace(/\s/g, " ")).toBe("120 м/смену · 4 800 м/мес");
  });

  it("без станка в справочнике остаётся только скорость за смену", () => {
    const hints = derivedHints(
      "drilling_conditions",
      "X",
      { equipment_type_code: "UNKNOWN", tech_speed_m_per_h: "10", unproductive_h_per_shift: "1" },
      ctx,
    );
    expect(hints[0].value.replace(/\s/g, " ")).toBe("100 м/смену");
  });
});

describe("подсказки шкалы сдельной премии", () => {
  const ctx = context({});
  const curve = {
    scale_type: "CURVE_POWER",
    norm_per_shift: "115.3846",
    rate_norm: "45",
    ceiling_per_shift: "184.6154",
    rate_ceiling: "168.66",
  };

  it("степенная кривая: γ и премия за смену на норме и потолке", () => {
    const hints = derivedHints("labor_rates", "RATE_DRILLER", curve, ctx);
    expect(hints.map((hint) => hint.label)).toEqual(["Показатель кривой γ", "Премия за смену: норма · потолок"]);
    expect(hints[0].value).toBe("2,811");
    expect(hints[1].value.replace(/\s/g, " ")).toBe("5 192,31 ₽ · 12 000,05 ₽");
  });

  it("линейная кривая: трапеция между узлами, без γ", () => {
    const hints = derivedHints("labor_rates", "RATE_DRILLER", { ...curve, scale_type: "CURVE_LINEAR" }, ctx);
    expect(hints).toHaveLength(1);
    // 12 588,23 × 13 смен = 163 647 ₽ — эталон линейной кривой при 2 400 м (решения, §7).
    expect(hints[0].value.replace(/\s/g, " ")).toBe("5 192,31 ₽ · 12 588,23 ₽");
  });

  it("без полного набора узлов, у ступеней и у несогласованной кривой подсказки нет", () => {
    expect(derivedHints("labor_rates", "R", { ...curve, rate_ceiling: "" }, ctx)).toEqual([]);
    expect(derivedHints("labor_rates", "R", { scale_type: "STEP", tiers: [] }, ctx)).toEqual([]);
    expect(derivedHints("labor_rates", "R", { ...curve, ceiling_per_shift: "100" }, ctx)).toEqual([]);
  });
});

describe("ставки организации", () => {
  it("НДС и часы смены берутся из активной записи", () => {
    const ctx = context({ organization_rates: [RATES] });
    expect(vatRate(ctx)).toBe(0.2);
    expect(shiftHours(ctx)).toBe(11);
  });

  it("без записи используются значения по умолчанию", () => {
    const ctx = context({});
    expect(vatRate(ctx)).toBe(0.2);
    expect(shiftHours(ctx)).toBe(11);
  });
});
