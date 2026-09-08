import { api } from "../../api/endpoints";
import type { EconomicsRunSummary, RunCompare } from "../../types/blockEconomics";

const money = (value: number) =>
  value.toLocaleString("ru-RU", { minimumFractionDigits: 0, maximumFractionDigits: 0 });

/** Сохранённые сценарии блока и сравнение до трёх снимков рядом. */
export function RunsCompare({
  runs,
  selected,
  compare,
  busy,
  onToggle,
  onCompare,
}: {
  runs: EconomicsRunSummary[];
  selected: string[];
  compare: RunCompare | null;
  busy: boolean;
  onToggle: (runId: string) => void;
  onCompare: () => void;
}) {
  return (
    <section className="panel runs-compare">
      <header>
        <b>Сценарии блока</b>
        <button
          type="button"
          className="secondary-button"
          onClick={onCompare}
          disabled={busy || selected.length < 2}
        >
          Сравнить выбранные
        </button>
      </header>
      <div className="panel-body">
        {runs.length === 0 ? (
          <p className="page-caption">Сохранённых сценариев ещё нет: посчитайте и нажмите «Сохранить сценарий».</p>
        ) : (
          <div className="runs-list">
            {runs.map((run) => (
              <label key={run.id} className={selected.includes(run.id) ? "run-row selected" : "run-row"}>
                <input
                  type="checkbox"
                  checked={selected.includes(run.id)}
                  onChange={() => onToggle(run.id)}
                  disabled={!selected.includes(run.id) && selected.length >= 3}
                />
                <span>
                  <b>{run.name}</b>
                  <small>{new Date(run.created_at).toLocaleString("ru-RU")} · {run.package_code}</small>
                </span>
                <em>{(run.price_per_m3.full ?? 0).toFixed(2)} ₽/м³</em>
                <a href={api.blockEconomics.exportUrl(run.id)} target="_blank" rel="noreferrer">xlsx</a>
              </label>
            ))}
          </div>
        )}

        {compare && (
          <div className="table-scroll compare-table">
            <table>
              <thead>
                <tr>
                  <th>Статья</th>
                  {compare.runs.map((run) => <th key={run.id}>{run.name}</th>)}
                  <th>Δ, ₽</th>
                </tr>
              </thead>
              <tbody>
                {compare.rows.map((row) => (
                  <tr key={row.cost_item_code}>
                    <td>{row.cost_item_name}</td>
                    {row.amounts.map((cell) => <td key={cell.run_id}>{money(cell.amount_rub)}</td>)}
                    <td className={row.delta_rub < 0 ? "metric-negative" : ""}>
                      {row.delta_rub > 0 ? "+" : ""}{money(row.delta_rub)}
                    </td>
                  </tr>
                ))}
                <tr className="compare-total">
                  <td>Полная себестоимость, ₽/м³</td>
                  {(compare.price_per_m3.full ?? []).map((value, index) => (
                    <td key={index}>{value.toFixed(2)}</td>
                  ))}
                  <td className={(compare.delta_price_per_m3.full ?? 0) < 0 ? "metric-negative" : ""}>
                    {(compare.delta_price_per_m3.full ?? 0) > 0 ? "+" : ""}
                    {(compare.delta_price_per_m3.full ?? 0).toFixed(2)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
