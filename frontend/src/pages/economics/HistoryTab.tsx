import { api } from "../../api/endpoints";
import type { EconomicsRunSummary } from "../../types/blockEconomics";
import { money } from "./format";

/**
 * Вкладка «История»: все сохранённые сценарии паспорта списком, каждый
 * открывается черновиком одним кликом («Открыть» зовёт `onOpen(run.id)` —
 * саму загрузку прогона и превращение его в черновик делает страница).
 *
 * В отличие от «Сравнение сценариев» (`RunsCompare`, которая продолжает
 * жить на своей вкладке) здесь нет чекбоксов и сопоставления построчно —
 * только список и переход; вкладки не дублируют друг друга.
 */
export function HistoryTab({
  runs,
  onOpen,
}: {
  runs: EconomicsRunSummary[];
  onOpen: (runId: string) => void;
}) {
  return (
    <section className="panel history-tab">
      <header>
        <b>История сценариев</b>
      </header>
      <div className="panel-body">
        {runs.length === 0 ? (
          <p className="page-caption">Сохранённых сценариев ещё нет: посчитайте и нажмите «Сохранить».</p>
        ) : (
          <div className="history-list">
            {runs.map((run) => (
              <div className="history-row" key={run.id}>
                <span>
                  <b>{run.name}</b>
                  <small>
                    {new Date(run.created_at).toLocaleString("ru-RU")} · ревизия {run.reference_revision_id}
                  </small>
                </span>
                <em>{money(run.price_per_m3.full ?? 0)} ₽/м³</em>
                <button type="button" className="secondary-button" onClick={() => onOpen(run.id)}>
                  Открыть
                </button>
                <a href={api.blockEconomics.exportUrl(run.id)} target="_blank" rel="noreferrer">
                  xlsx
                </a>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
