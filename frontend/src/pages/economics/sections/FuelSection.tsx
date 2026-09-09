/**
 * Раздел «ГСМ»: только строки модели, ничего не редактируется — норму и
 * цену считает сама модель себестоимости по технике и её сменам.
 */
import { EstimateLine } from "../estimate/EstimateLine";
import { lineNumber } from "../estimateModel";
import { lineShare } from "./lineHelpers";
import type { SectionEditorProps } from "./types";

export function FuelSection({ group, economics, volume }: SectionEditorProps) {
  if (group.lines.length === 0) {
    return <p className="page-caption">Строк ГСМ пока нет — заполните параметры модели и технику блока.</p>;
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
