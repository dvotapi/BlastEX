/**
 * Источник ФОТ экипажа бурения на странице «Бурение»: переключатель «Ставки /
 * Методика ФОТ» рядом с бегунком загрузки станка и, при методике, свёрнутая
 * строка разбивки с долей экипажа в марже (`PayrollBreakdown`). Это тот же
 * параметр черновика (`payroll_source`), что видит смета: переключатель меняет
 * блок, а не отдельный расчёт. Скорость и цена метра здесь не повторяются —
 * они в панели «Что двигает цену метра» и в шапке.
 */
import { useId } from "react";
import { PayrollBreakdown } from "../PayrollBreakdown";
import type { BlockEconomics, ModelParameters } from "../../../types/blockEconomics";

export type DrillingPayrollPanelProps = {
  params: ModelParameters;
  /** null — расчёт ещё не пришёл. */
  economics: BlockEconomics | null;
  canEdit: boolean;
  onChange: (patch: Partial<ModelParameters>) => void;
};

const METHOD_NOT_APPLIED = ["Методика ФОТ не применена", "ФОТ экипажа бурения посчитан по ставкам"];

/** Переключатель источника ФОТ с короткой строкой состояния под ним. */
export function DrillingPayrollSource({ params, economics, canEdit, onChange }: DrillingPayrollPanelProps) {
  const sourceName = `payroll_source-${useId()}`;
  const subcontracted = params.drilling_executor === "SUBCONTRACTOR";
  const payroll = economics?.payroll ?? null;
  const methodology = params.payroll_source === "PAYROLL";
  // Причина видна, только если её несёт текущий ответ: сразу после
  // переключения ответ ещё посчитан по ставкам и текста про методику нет.
  const reason =
    economics?.warnings.find((text) => METHOD_NOT_APPLIED.some((prefix) => text.startsWith(prefix))) ?? "";

  let note = "";
  if (subcontracted) note = "Бурение на субподряде: ФОТ экипажа считает подрядчик. Сохранённый выбор не применяется";
  else if (methodology && payroll === null) note = reason || "Расчёт выполняется…";
  else if (!methodology) note = "Оклад или ставка должности за смену, взносы и суточные; ночных, праздничных и межвахты нет.";
  else note = "Оклад, ночные, праздничные, межвахта, премия, РК и северная, взносы и резервы отпусков.";

  return (
    <fieldset
      className={subcontracted ? "labor-source drilling-payroll-source labor-source-inactive" : "labor-source drilling-payroll-source"}
      disabled={!canEdit || subcontracted}
      aria-label="Источник ФОТ экипажа"
    >
      <legend>ФОТ экипажа</legend>
      <label>
        <input
          type="radio"
          name={sourceName}
          value="RATES"
          checked={params.payroll_source === "RATES"}
          onChange={() => onChange({ payroll_source: "RATES" })}
        />
        Ставки
      </label>
      <label>
        <input
          type="radio"
          name={sourceName}
          value="PAYROLL"
          checked={methodology}
          onChange={() => onChange({ payroll_source: "PAYROLL" })}
        />
        Методика ФОТ
      </label>
      <p className="labor-source-note">{note}</p>
    </fieldset>
  );
}

/** Свёрнутая разбивка ФОТ по методике — только когда методика применилась. */
export function DrillingPayrollBreakdown({ params, economics }: Pick<DrillingPayrollPanelProps, "params" | "economics">) {
  const payroll = economics?.payroll ?? null;
  if (!payroll || params.payroll_source !== "PAYROLL" || params.drilling_executor === "SUBCONTRACTOR") return null;
  return (
    <div className="drilling-payroll-breakdown">
      <PayrollBreakdown payroll={payroll} showPrice={false} />
    </div>
  );
}
