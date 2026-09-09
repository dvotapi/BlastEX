/**
 * Раздел «Постоянные и общепроизводственные расходы»: то, что не относится
 * ни к одному другому разделу конструктора (см. правило `groupOf` в
 * `estimateModel.ts`) — только строки модели, без редактирования на вкладке.
 */
import { EstimateLine } from "../estimate/EstimateLine";
import { lineNumber } from "../estimateModel";
import { lineShare } from "./lineHelpers";
import type { SectionEditorProps } from "./types";

export function FixedCostsSection({ group, economics, volume }: SectionEditorProps) {
  if (group.lines.length === 0) {
    return <p className="page-caption">Постоянных и общепроизводственных расходов в расчёте пока нет.</p>;
  }
  return (
    <>
      {group.lines.map((line, index) => (
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
      ))}
    </>
  );
}
