import { describe, expect, it } from "vitest";

import { drillingBreakdown } from "./drillingRows";
import type { BlockEconomics } from "../../types/blockEconomics";

const economics = (values: Record<string, string>, lines: BlockEconomics["lines"] = []) =>
  ({
    natural: {
      values,
      lineage: { drilling_condition: "drilling_conditions.COND_GRANITE (станок + порода)", rig_shifts: "2420 м / 120 м/см" },
      warnings: [],
    },
    lines,
  }) as unknown as BlockEconomics;

const drillingLine = (code: string, amount: number) =>
  ({ cost_item_code: code, cost_item_name: code, operation_code: "PRODUCTION_DRILLING", layer: "variable", amount_rub: amount, formula: "" }) as BlockEconomics["lines"][number];

describe("разложение бурения", () => {
  it("собирает норму, цену метра и строки бурения из результата", () => {
    const result = drillingBreakdown(
      economics(
        {
          drilling_m: "2420", drilling_tech_speed_m_per_h: "12", v_commercial_m_per_shift: "120",
          rig_shifts: "20.17", drilling_variable_rub_per_m: "300", drilling_fixed_rub_per_m: "50",
          drilling_rub_per_m: "350",
        },
        [drillingLine("DRILL_TOOLING", 100), { ...drillingLine("SZM_FUEL", 5), operation_code: "BULK_CHARGING_SZM" }],
      ),
    );
    expect(result).not.toBeNull();
    expect(result!.conditionSource).toContain("COND_GRANITE");
    expect(result!.perMetre).toEqual({ variable: 300, fixed: 50, total: 350 });
    expect(result!.norms.map((row) => row.label)).toEqual([
      "Техническая скорость", "Коммерческая скорость", "Смены станка на блок",
    ]);
    expect(result!.norms[2].source).toBe("2420 м / 120 м/см");
    expect(result!.lines.map((line) => line.cost_item_code)).toEqual(["DRILL_TOOLING"]);
  });

  it("возвращает null, когда бурение не посчитано", () => {
    expect(drillingBreakdown(economics({ drilling_m: "2420" }))).toBeNull();
    expect(drillingBreakdown(economics({ drilling_m: "0", v_commercial_m_per_shift: "120" }))).toBeNull();
  });

  it("не показывает нулевые нормы: обсадки нет — строки нет", () => {
    const result = drillingBreakdown(
      economics({ drilling_m: "10", v_commercial_m_per_shift: "100", drilling_casing_m: "0", drilling_fuel_l: "40" }),
    );
    expect(result!.norms.map((row) => row.label)).toEqual(["Коммерческая скорость", "ДТ на бурение"]);
  });
});
