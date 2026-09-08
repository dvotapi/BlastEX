import type { BlockEconomics } from "../../types/blockEconomics";

const money = (value: number, digits = 2) =>
  value.toLocaleString("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits });

/**
 * Две цены блока: маржинальная — пол, ниже которого блок убыточен сам по
 * себе; полная — с распределённой долей юнита. Разница — коридор для торга.
 */
export function PricePanel({ economics }: { economics: BlockEconomics }) {
  const prices = economics.price_per_m3;
  const gap = prices.full - prices.marginal;
  return (
    <section className="panel price-panel">
      <header><b>Цена блока</b><span>{money(economics.block_volume_m3, 0)} м³</span></header>
      <div className="price-panel-main">
        <div>
          <span>Маржинальная себестоимость</span>
          <strong>{money(prices.marginal)}</strong>
          <small>₽/м³ — переменные и прямые затраты блока</small>
        </div>
        <div>
          <span>Полная себестоимость</span>
          <strong>{money(prices.full)}</strong>
          <small>₽/м³ — с долей постоянных затрат юнита</small>
        </div>
      </div>
      <div className="price-panel-secondary">
        <div>
          <span>С ОХР и рентабельностью</span>
          <b>{money(prices.with_margin)} ₽/м³</b>
        </div>
        <div>
          <span>С НДС</span>
          <b>{money(prices.with_vat)} ₽/м³</b>
        </div>
        <div>
          <span>Коридор для торга</span>
          <b>{money(gap)} ₽/м³</b>
        </div>
        <div>
          <span>Цена блока без НДС</span>
          <b>{money(economics.markup.price_rub ?? 0, 0)} ₽</b>
        </div>
      </div>
    </section>
  );
}
