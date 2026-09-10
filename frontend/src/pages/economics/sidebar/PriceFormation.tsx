/**
 * Лестница формирования цены блока: от себестоимости к цене с НДС.
 *
 * Те же готовые числа, что в `PricePanel.tsx` (`markup` и `price_per_m3` из
 * ответа модели) — надбавки посчитаны один раз в `cost/model/markup.py`,
 * здесь их только показывают в другом наборе строк под сайдбар: НДС —
 * отдельная строка лестницы, а маржинальная цена и коридор для торга
 * переехали на вкладку «Ресурсы».
 */
import { money, percent } from "../format";
import type { BlockEconomics } from "../../../types/blockEconomics";

export function PriceFormation({ economics }: { economics: BlockEconomics }) {
  const markup = economics.markup;
  const prices = economics.price_per_m3;
  const volume = economics.block_volume_m3 > 0;

  const rows: Array<{ label: string; value: number; perM3?: number; strong?: boolean }> = [
    { label: "Себестоимость", value: markup.full_cost_rub ?? 0, perM3: prices.full },
    { label: `+ ОХР, ${percent(markup.overhead_rate)}`, value: markup.overhead_rub ?? 0 },
    { label: "Итого с ОХР", value: markup.cost_with_overhead_rub ?? 0, perM3: prices.with_overhead },
    { label: `+ Рентабельность, ${percent(markup.target_margin_rate)}`, value: markup.margin_rub ?? 0 },
    { label: "Цена без НДС", value: markup.price_rub ?? 0, perM3: prices.with_margin },
    { label: `+ НДС, ${percent(markup.vat_rate)}`, value: markup.vat_rub ?? 0 },
    { label: "Цена с НДС", value: markup.price_with_vat_rub ?? 0, perM3: prices.with_vat, strong: true },
  ];

  return (
    <section className="panel price-formation">
      <header>
        <b>Формирование цены</b>
      </header>
      <div className="price-formation-ladder">
        {rows.map((row) => (
          <div className={`price-formation-row${row.strong ? " strong" : ""}`} key={row.label}>
            <span>{row.label}</span>
            <b>{money(row.value, 0)} ₽</b>
            <em>{volume && row.perM3 !== undefined ? `${money(row.perM3)} ₽/м³` : ""}</em>
          </div>
        ))}
      </div>
    </section>
  );
}
