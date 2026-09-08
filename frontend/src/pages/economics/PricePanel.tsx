import { money, percent } from "./format";
import type { BlockEconomics } from "../../types/blockEconomics";

/**
 * Итог блока лестницей бумажной сметы: полная себестоимость,
 * общехозяйственные расходы, себестоимость с ОХР, рентабельность, выручка.
 *
 * Подписи те же, что в выгрузке и сравнении прогонов: «полная
 * себестоимость» — сумма всех слоёв до надбавок, и другого значения у неё
 * на вкладке быть не может. Все суммы и цены за м³ приходят из модели:
 * складывать их в интерфейсе значит завести второй расчёт.
 *
 * Маржинальная себестоимость стоит отдельно: в бумаге её нет, а нужна она
 * ради одного вопроса — ниже какой цены блок убыточен сам по себе.
 */
export function PricePanel({ economics }: { economics: BlockEconomics }) {
  const prices = economics.price_per_m3;
  const markup = economics.markup;
  const volume = economics.block_volume_m3 > 0 ? economics.block_volume_m3 : null;
  const gap = prices.full - prices.marginal;

  const ladder = [
    {
      label: "Полная себестоимость",
      value: markup.full_cost_rub ?? 0,
      perM3: volume === null ? undefined : prices.full,
    },
    {
      label: `Общехозяйственные расходы, ${percent(markup.overhead_rate)}`,
      value: markup.overhead_rub ?? 0,
    },
    {
      label: "Себестоимость с ОХР",
      value: markup.cost_with_overhead_rub ?? 0,
      perM3: volume === null ? undefined : prices.with_overhead,
      strong: true,
    },
    {
      label: `Рентабельность, ${percent(markup.target_margin_rate)}`,
      value: markup.margin_rub ?? 0,
    },
    {
      label: "Выручка без НДС",
      value: markup.price_rub ?? 0,
      perM3: volume === null ? undefined : prices.with_margin,
      strong: true,
    },
  ];

  return (
    <section className="panel price-panel">
      <header><b>Цена блока</b><span>{money(economics.block_volume_m3, 0)} м³</span></header>
      <div className="price-ladder">
        {ladder.map((row) => (
          <div className={`price-ladder-row${row.strong ? " strong" : ""}`} key={row.label}>
            <span>{row.label}</span>
            <b>{money(row.value, 0)} ₽</b>
            <em>{row.perM3 === undefined ? "" : `${money(row.perM3)} ₽/м³`}</em>
          </div>
        ))}
      </div>
      <div className="price-panel-secondary">
        <div>
          <span>Маржинальная себестоимость</span>
          <b>{money(prices.marginal)} ₽/м³</b>
          <small>пол цены: ниже блок убыточен сам по себе</small>
        </div>
        <div>
          <span>Коридор для торга</span>
          <b>{money(gap)} ₽/м³</b>
          <small>между маржинальной и полной</small>
        </div>
        <div>
          <span>С НДС</span>
          <b>{money(prices.with_vat)} ₽/м³</b>
          <small>{money(markup.price_with_vat_rub ?? 0, 0)} ₽ на блок</small>
        </div>
      </div>
    </section>
  );
}
