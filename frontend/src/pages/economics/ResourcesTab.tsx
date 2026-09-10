import type { BlockEconomics } from "../../types/blockEconomics";
import { ModelWarnings } from "./ModelWarnings";
import { amount, money } from "./format";

/**
 * Вкладка «Ресурсы»: все натуральные величины расчёта с источниками (не
 * только бурение, как `DrillingBreakdown`, — весь `natural.values`), узкие
 * места мощности техники и бригады, предупреждения модели и маржинальная
 * себестоимость с коридором для торга (те же два числа, что в
 * `PricePanel`, — их не пересчитывают, а показывают).
 */
export function ResourcesTab({ economics }: { economics: BlockEconomics }) {
  const values = economics.natural.values;
  const lineage = economics.natural.lineage;
  const rows = Object.keys(values)
    .sort()
    .map((key) => ({ key, value: values[key], source: lineage[key] ?? "" }));

  const prices = economics.price_per_m3;
  const gap = prices.full - prices.marginal;

  return (
    <div className="resources-tab">
      <section className="panel">
        <header>
          <b>Натуральные величины расчёта</b>
        </header>
        <div className="panel-body">
          {rows.length === 0 ? (
            <p className="page-caption">Модель ещё не посчитала натуральные величины.</p>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Показатель</th>
                    <th>Значение</th>
                    <th>Источник</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.key}>
                      <td>{row.key}</td>
                      <td>{row.value}</td>
                      <td>
                        <small>{row.source}</small>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {economics.capacity.length > 0 && (
        <section className="panel resources-capacity">
          <header>
            <b>Узкие места мощности</b>
          </header>
          <div className="panel-body">
            <ul>
              {economics.capacity.map((item) => (
                <li key={item.resource_code}>
                  <b>{item.resource_name}</b>: {item.message} (требуется {amount(item.required)} {item.unit}
                  {item.available !== null ? `, доступно ${amount(item.available)} ${item.unit}` : ""})
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      <ModelWarnings economics={economics} />

      <section className="panel resources-margin">
        <header>
          <b>Маржинальная себестоимость</b>
        </header>
        <div className="panel-body resources-margin-body">
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
        </div>
      </section>
    </div>
  );
}
