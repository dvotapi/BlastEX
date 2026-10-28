import type { BlockPayroll, PayrollSharePoint } from "../../types/blockEconomics";
import { amount, money, percent } from "./format";
import { OriginBadge } from "./estimate/OriginBadge";
import { PayrollChart } from "./PayrollChart";
import { shareView } from "./payrollModel";

function ShareRow({ title, point }: { title: string; point: PayrollSharePoint }) {
  return (
    <div className="payroll-share-row">
      <span>{title} · {amount(point.pace)} м/см</span>
      <b>{percent(point.crew_share)}</b>
      <small>получает машинист: {percent(point.main_share)}</small>
    </div>
  );
}

/** ФОТ экипажа бурения по методике: свёрнут до цены метра и доли в марже. */
export function PayrollBreakdown({ payroll }: { payroll: BlockPayroll }) {
  const view = shareView(payroll.margin);
  const { margin, pace } = payroll;
  const checked = margin.status === "CHECKED";
  const indicator = view.tone === "muted" ? view.value : `доля ${view.label} ${view.value} при пороге ${percent(margin.threshold)}`;
  const priceNote = margin.lineage.price_rub_per_m;

  return (
    <details className="panel payroll-breakdown">
      <summary className="payroll-summary">
        <b>ФОТ по методике</b>
        {payroll.price_rub_per_m != null && <span className="payroll-summary-price">{money(payroll.price_rub_per_m)} ₽/м</span>}
        <span className={`payroll-share payroll-share-${view.tone}`}>{indicator}</span>
        <OriginBadge origin="PAYROLL" />
      </summary>

      <div className="payroll-body">
        <dl className="payroll-facts">
          <div title={payroll.lineage.planned_pace || undefined}>
            <dt>Плановый темп</dt>
            <dd>{amount(pace.m_plan)} м/см</dd>
          </div>
          {pace.condition_code && (
            <div>
              <dt>Строка матрицы</dt>
              <dd>{pace.condition_code}</dd>
            </div>
          )}
          <div>
            <dt>k крепости · k диаметра</dt>
            <dd>
              {amount(pace.k_hardness, 3)} · {amount(pace.k_diameter, 3)}
              {pace.diameter_mm != null && <small> (⌀ {amount(pace.diameter_mm)} мм)</small>}
            </dd>
          </div>
          <div title={payroll.lineage.normalized_meters || undefined}>
            <dt>Приведённые метры блока</dt>
            <dd>{amount(payroll.normalized_meters)}</dd>
          </div>
          <div title={payroll.lineage.effective_shifts || undefined}>
            <dt>План вахты, эффективных смен</dt>
            <dd>{amount(payroll.effective_shifts)}</dd>
          </div>
        </dl>

        <table className="payroll-table">
          <thead>
            <tr>
              <th>Должность</th><th>Человек в смене</th><th>c_var, ₽/пр. м</th>
              <th>Постоянная часть, ₽</th><th>Переменная часть, ₽</th><th>Итого, ₽</th>
            </tr>
          </thead>
          <tbody>
            {payroll.positions.map((position) => (
              <tr key={position.position_code}>
                <td>{position.position_name || position.position_code}</td>
                <td>{amount(position.headcount)}</td>
                <td>{money(position.c_var)}</td>
                <td>{money(position.fixed_rub, 0)}</td>
                <td>{money(position.variable_rub, 0)}</td>
                <td>{money(position.amount_rub, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="payroll-price">
          {payroll.price_rub_per_m != null && (
            <div title={priceNote || undefined}>
              <span>Цена метра</span>
              <b>{money(payroll.price_rub_per_m)} ₽/м</b>
              <small>по себестоимости с надбавками</small>
            </div>
          )}
          {payroll.variable_rub_per_m != null && (
            <div title={margin.lineage.variable_rub_per_m || undefined}>
              <span>Переменные метра</span>
              <b>{money(payroll.variable_rub_per_m)} ₽/м</b>
            </div>
          )}
          {margin.margin_rub_per_m != null && (
            <div>
              <span>Маржа метра</span>
              <b>{money(margin.margin_rub_per_m)} ₽/м</b>
            </div>
          )}
        </div>

        {checked ? (
          <div className="payroll-shares">
            {margin.plan && <ShareRow title="Доля экипажа в марже, плановый темп" point={margin.plan} />}
            {margin.ceiling && <ShareRow title="Доля экипажа в марже, потолок шкалы" point={margin.ceiling} />}
            <small>Порог предупреждения: {percent(margin.threshold)}</small>
          </div>
        ) : (
          <p className="payroll-note">{view.value}</p>
        )}

        <PayrollChart payroll={payroll} />
      </div>
    </details>
  );
}
