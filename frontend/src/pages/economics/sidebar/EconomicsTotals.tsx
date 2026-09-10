/**
 * Ключевые итоги блока — четыре плашки под лестницей формирования цены.
 *
 * Числа те же, что в `PriceFormation`: себестоимость и цена без НДС в
 * рублях на блок, цена без НДС и с НДС в ₽/м³ — самые частые вопросы
 * сметчика, вынесенные из лестницы для беглого взгляда.
 */
import { money } from "../format";
import type { BlockEconomics } from "../../../types/blockEconomics";

export function EconomicsTotals({ economics }: { economics: BlockEconomics }) {
  const markup = economics.markup;
  const prices = economics.price_per_m3;

  const tiles = [
    { label: "Себестоимость, ₽", value: money(markup.full_cost_rub ?? 0, 0) },
    { label: "Цена без НДС, ₽", value: money(markup.price_rub ?? 0, 0) },
    { label: "Цена без НДС, ₽/м³", value: money(prices.with_margin) },
    { label: "Цена с НДС, ₽/м³", value: money(prices.with_vat) },
  ];

  return (
    <section className="panel economics-totals-panel">
      <header>
        <b>Ключевые показатели блока</b>
      </header>
      <div className="economics-totals">
        {tiles.map((tile) => (
          <div className="economics-totals-tile" key={tile.label}>
            <span>{tile.label}</span>
            <b>{tile.value}</b>
          </div>
        ))}
      </div>
    </section>
  );
}
