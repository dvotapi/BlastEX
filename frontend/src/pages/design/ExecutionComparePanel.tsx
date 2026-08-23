import { ruNumber } from "../../lib/format";
import type { ExecutionCompareResponse } from "../../types/design";
import { RoleBadge } from "./RoleBadge";

function Metric({ label, value, unit }: { label: string; value: number; unit: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{ruNumber(value, 0)}</strong>
      <small>{unit}</small>
    </div>
  );
}

export function ExecutionComparePanel({
  busy,
  result,
  onCompare,
}: {
  busy: boolean;
  result: ExecutionCompareResponse | null;
  onCompare: () => void;
}) {
  const drilled = result?.design_vs_drilled;
  const charged = result?.design_vs_charged;
  const fired = result?.design_vs_fired;
  return (
    <section className="panel">
      <header>
        <b>Сравнение исполнения</b>
        <span className="role-legend compact">
          <RoleBadge role="designed" />
          <RoleBadge role="executed" />
        </span>
      </header>
      <div className="panel-body">
        <small>
          Три независимых отчёта: проект ↔ бурение, проект ↔ заряд, проект ↔ взрыв. Факт никогда не переписывает проект.
        </small>
        <button type="button" className="secondary-button" onClick={onCompare} disabled={busy}>
          {busy ? "Считаем…" : "Сравнить всё"}
        </button>
        {result && (
          <>
            <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
              <Metric label="Бурение" value={result.as_drilled_count} unit="скв." />
              <Metric label="Заряд" value={result.as_charged_count} unit="скв." />
              <Metric label="Взрыв" value={result.as_fired_count} unit="скв." />
            </div>
            <div className="exec-compare-table">
              <div className="exec-compare-head">
                <span>Сравнение</span>
                <span>Записано</span>
                <span>Сравнено</span>
              </div>
              <div className="exec-compare-row">
                <span>Проект ↔ бурение</span>
                <b>{drilled?.as_drilled_count ?? 0}</b>
                <b>{drilled?.compared_count ?? 0}</b>
              </div>
              <div className="exec-compare-row">
                <span>Проект ↔ заряд</span>
                <b>{charged?.as_charged_count ?? 0}</b>
                <b>{charged?.compared_count ?? 0}</b>
              </div>
              <div className="exec-compare-row">
                <span>Проект ↔ взрыв</span>
                <b>{fired?.as_fired_count ?? 0}</b>
                <b>{fired?.compared_count ?? 0}</b>
              </div>
            </div>
            {result.warnings.length > 0 && (
              <small className="frag-warnings">{result.warnings.slice(0, 4).join(" ")}</small>
            )}
          </>
        )}
      </div>
    </section>
  );
}
