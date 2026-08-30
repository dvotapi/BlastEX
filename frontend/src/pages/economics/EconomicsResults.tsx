import { useState } from "react";
import type { EconomicCalculationResult, EconomicMetrics } from "../../types/economics";

const MONEY = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
const NUMBER = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 });

const METRICS: Array<{ key: keyof EconomicMetrics; label: string; money?: boolean }> = [
  { key: "billed_quantity", label: "Оплачиваемый объём" },
  { key: "revenue_rub", label: "Рыночная выручка", money: true },
  { key: "variable_cost", label: "Переменные затраты", money: true },
  { key: "project_direct_cost", label: "Прямые затраты объекта", money: true },
  { key: "production_cost", label: "Производственная себестоимость", money: true },
  { key: "full_internal_cost", label: "Полная внутренняя себестоимость", money: true },
  { key: "contribution_margin", label: "Маржинальный доход", money: true },
  { key: "project_margin", label: "Результат после прямых затрат", money: true },
  { key: "production_margin", label: "Производственный результат", money: true },
  { key: "full_cost_margin", label: "Полный финансовый результат", money: true },
];

function value(value: number, isMoney?: boolean): string {
  return `${isMoney ? MONEY.format(value) : NUMBER.format(value)}${isMoney ? " ₽" : ""}`;
}

export function EconomicsResults({ result }: { result: EconomicCalculationResult }) {
  const [details, setDetails] = useState(false);
  return (
    <section className="economics-results">
      <div className="economic-result-header">
        <div><h3>Экономика производственного юнита</h3><p>Формулы {result.formula_version} · справочники {result.reference_revision_id}</p></div>
      </div>

      <div className="economic-summary-cards">
        <div><span>Изменение выручки</span><b>{MONEY.format(result.delta.totals.revenue_rub)} ₽</b></div>
        <div><span>Изменение полной себестоимости</span><b>{MONEY.format(result.delta.totals.full_internal_cost)} ₽</b></div>
        <div className={result.delta.totals.full_cost_margin < 0 ? "negative" : "positive"}><span>Изменение результата юнита</span><b>{MONEY.format(result.delta.totals.full_cost_margin)} ₽</b></div>
        <div className={result.after.totals.full_cost_margin < 0 ? "negative" : "positive"}><span>Результат после добавления</span><b>{MONEY.format(result.after.totals.full_cost_margin)} ₽</b></div>
      </div>

      <section className="panel">
        <header><b>До / После / Изменение</b></header>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Показатель</th><th>До</th><th>После</th><th>Изменение</th></tr></thead>
            <tbody>
              {METRICS.map((metric) => (
                <tr key={metric.key}>
                  <td>{metric.label}</td>
                  <td className="num">{value(result.before.totals[metric.key], metric.money)}</td>
                  <td className="num">{value(result.after.totals[metric.key], metric.money)}</td>
                  <td className={`num ${result.delta.totals[metric.key] < 0 ? "metric-negative" : ""}`}>{value(result.delta.totals[metric.key], metric.money)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <header><b>Помесячное изменение</b></header>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Месяц</th><th>Выручка</th><th>Переменные</th><th>Прямые</th><th>Производственные</th><th>Полная себестоимость</th><th>Результат</th></tr></thead>
            <tbody>{result.delta.periods.map((row) => <tr key={row.month}><td>{row.month}</td><td>{MONEY.format(row.revenue_rub)} ₽</td><td>{MONEY.format(row.variable_cost)} ₽</td><td>{MONEY.format(row.project_direct_cost)} ₽</td><td>{MONEY.format(row.production_cost)} ₽</td><td>{MONEY.format(row.full_internal_cost)} ₽</td><td className={row.full_cost_margin < 0 ? "metric-negative" : ""}>{MONEY.format(row.full_cost_margin)} ₽</td></tr>)}</tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <header><b>Загрузка ресурсов после добавления объекта</b></header>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Месяц</th><th>Ресурс</th><th>Потребность</th><th>Доступно</th><th>Загрузка</th><th>Дефицит</th></tr></thead>
            <tbody>{result.after.resource_utilization.map((row) => <tr key={`${row.month}-${row.resource_code}`} className={row.excess > 0 ? "capacity-over" : ""}><td>{row.month}</td><td>{row.resource_name}</td><td>{NUMBER.format(row.demand)}</td><td>{row.available === null ? "не задано" : NUMBER.format(row.available)}</td><td>{row.utilization_pct === null ? "—" : `${NUMBER.format(row.utilization_pct)}%`}</td><td>{NUMBER.format(row.excess)}</td></tr>)}</tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <header><b>Экономика строк работ после добавления</b></header>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Строка</th><th>Пакет</th><th>Выручка</th><th>Прямые</th><th>Полная себестоимость</th><th>Результат</th><th>Безубыточная цена</th></tr></thead>
            <tbody>{result.after.service_lines.map((row) => <tr key={row.id}><td>{row.name}</td><td>{row.package_code}</td><td>{MONEY.format(row.revenue_rub)} ₽</td><td>{MONEY.format(row.project_direct_cost)} ₽</td><td>{MONEY.format(row.full_internal_cost)} ₽</td><td className={row.full_cost_margin < 0 ? "metric-negative" : ""}>{MONEY.format(row.full_cost_margin)} ₽</td><td>{row.break_even_price_rub === null ? "—" : `${NUMBER.format(row.break_even_price_rub)} ₽/${row.billing_unit}`}</td></tr>)}</tbody>
          </table>
        </div>
      </section>

      {(result.warnings.length > 0 || result.before.warnings.length > 0 || result.after.warnings.length > 0) && (
        <section className="calculation-warnings">
          <b>Предупреждения расчёта</b>
          <ul>{Array.from(new Set([...result.warnings, ...result.before.warnings, ...result.after.warnings])).map((warning) => <li key={warning}>{warning}</li>)}</ul>
        </section>
      )}

      <button className="secondary-button" onClick={() => setDetails((value) => !value)}>{details ? "Скрыть детализацию" : "Показать формулы и статьи"}</button>
      {details && (
        <section className="panel cost-line-details">
          <header><b>Детализация затрат после добавления</b><span>{result.after.cost_lines.length} строк</span></header>
          <div className="table-scroll"><table><thead><tr><th>Месяц</th><th>Строка</th><th>Операция</th><th>Статья</th><th>Слой</th><th>Сумма</th><th>Формула</th></tr></thead><tbody>{result.after.cost_lines.map((row, index) => <tr key={`${row.month}-${row.cost_item_code}-${index}`}><td>{row.month}</td><td>{row.service_line_name}</td><td>{row.operation_code}</td><td>{row.cost_item_name}</td><td>{row.layer}</td><td>{MONEY.format(Number(row.amount_rub))} ₽</td><td>{row.formula}</td></tr>)}</tbody></table></div>
        </section>
      )}
    </section>
  );
}
