/**
 * Раздел «Постоянные и общепроизводственные расходы»: то, что не относится
 * ни к одному другому разделу конструктора (см. правило `groupOf` в
 * `estimateModel.ts`).
 *
 * Здесь же задаётся плановый объём юнита. Постоянные затраты юнита модель
 * делит именно на него, и без него они на блок не распределяются вовсе —
 * расчёт молча выходит заниженным, а предупреждение об этом видно только на
 * вкладке «Ресурсы». Поле стоит там, куда эти деньги и падают.
 */
import { NumericInput } from "../NumericInput";
import { EstimateLine } from "../estimate/EstimateLine";
import { lineNumber } from "../estimateModel";
import { amount as formatAmount } from "../format";
import { lineShare } from "./lineHelpers";
import type { SectionEditorProps } from "./types";

export function FixedCostsSection({ group, params, economics, volume, canEdit, onChange }: SectionEditorProps) {
  const planMissing = !params.unit_plan_volume_m3 || Number(params.unit_plan_volume_m3) <= 0;

  return (
    <>
      <div className="estimate-card unit-plan-card">
        <label className="unit-plan-field">
          Плановый объём юнита, м³
          {canEdit ? (
            <NumericInput
              value={params.unit_plan_volume_m3}
              min={0}
              step={1000}
              ariaLabel="Плановый объём юнита, м³"
              onChange={(value) => onChange({ unit_plan_volume_m3: value ?? "0" })}
            />
          ) : (
            <b>{formatAmount(Number(params.unit_plan_volume_m3 || 0))}</b>
          )}
        </label>
        <p className="unit-plan-note">
          {planMissing
            ? "Пока объём не задан, постоянные затраты юнита не распределяются на блок — себестоимость занижена."
            : "На этот объём делятся постоянные затраты юнита: аренда, охрана, содержание склада ВМ."}
        </p>
      </div>
      {group.lines.length === 0 ? (
        <div className="estimate-section-empty">
          <p className="page-caption">Постоянных и общепроизводственных расходов в расчёте пока нет.</p>
        </div>
      ) : (
        group.lines.map((line, index) => (
          <EstimateLine
            key={line.cost_item_code}
            number={lineNumber(group, index)}
            name={line.cost_item_name}
            origin={line.price_origin || line.quantity_origin}
            quantity={line.quantity}
            unit={line.unit}
            price={line.unit_price_rub}
            amount={line.amount_rub}
            volume={volume}
            share={lineShare(line, economics)}
            formula={line.formula}
          />
        ))
      )}
    </>
  );
}
