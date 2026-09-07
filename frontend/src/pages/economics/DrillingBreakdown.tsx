import type { BlockEconomics } from "../../types/blockEconomics";
import { drillingBreakdown } from "./drillingRows";

const money = (value: number, digits = 2) =>
  value.toLocaleString("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const amount = (value: number) => value.toLocaleString("ru-RU", { maximumFractionDigits: 2 });

/** Стоимость метра бурения: норма, смены, оснастка — та же цифра, что в структуре затрат. */
export function DrillingBreakdown({ economics }: { economics: BlockEconomics }) {
  const breakdown = drillingBreakdown(economics);
  if (!breakdown) return null;
  const { perMetre, norms, lines, drillingM } = breakdown;
  const total = lines.reduce((sum, line) => sum + line.amount_rub, 0);

  return (
    <section className="panel drilling-breakdown">
      <header>
        <b>Стоимость бурения</b>
        <span>{amount(drillingM)} м · {breakdown.conditionSource || "норма не указана"}</span>
      </header>
      <div className="drilling-breakdown-price">
        <div>
          <span>Переменная часть метра</span>
          <b>{money(perMetre.variable)} ₽/м</b>
          <small>оснастка, ДТ, запчасти, допуск экипажа</small>
        </div>
        <div>
          <span>Постоянная часть метра</span>
          <b>{money(perMetre.fixed)} ₽/м</b>
          <small>амортизация и страховка по плановым сменам</small>
        </div>
        <div>
          <span>Метр бурения</span>
          <strong>{money(perMetre.total)} ₽/м</strong>
          <small>{money(total, 0)} ₽ на блок</small>
        </div>
      </div>
      <div className="drilling-breakdown-body">
        <table className="drilling-breakdown-norms">
          <thead>
            <tr><th>Норма</th><th>Значение</th><th>Ед.</th><th>Откуда</th></tr>
          </thead>
          <tbody>
            {norms.map((row) => (
              <tr key={row.label}>
                <td>{row.label}</td>
                <td>{amount(row.value)}</td>
                <td>{row.unit}</td>
                <td><small>{row.source}</small></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="drilling-breakdown-lines">
          {lines.map((line) => (
            <div key={line.cost_item_code}>
              <span>{line.cost_item_name}</span>
              <b>{money(line.amount_rub, 0)} ₽</b>
              <em>{drillingM > 0 ? money(line.amount_rub / drillingM) : "—"} ₽/м</em>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
