import { ruNumber } from "../../lib/format";
import type { BlastPassport, PassportMetricRow } from "../../types/design";

function RoleChip({ role }: { role: "designed" | "executed" | "predicted" | "measured" }) {
  const labels = {
    designed: "проект / designed",
    executed: "исполнение / executed",
    predicted: "прогноз / predicted",
    measured: "замер / measured",
  };
  return <span className={`passport-role role-${role}`}>{labels[role]}</span>;
}

function Metric({ label, value, unit, digits }: { label: string; value: number | null | undefined; unit: string; digits: number }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value == null ? "—" : ruNumber(value, digits)}</strong>
      <small>{unit}</small>
    </div>
  );
}

function cell(value: number | null, digits: number) {
  return value == null ? "—" : ruNumber(value, digits);
}

function digitsFor(row: PassportMetricRow) {
  if (row.unit === "кг/м³" || row.unit === "мм/с") return 3;
  if (row.unit === "шт." || row.unit === "₽") return 0;
  return 2;
}

export function PassportPanel({
  onAssemble,
  onPrint,
  busy,
  result,
}: {
  onAssemble: () => void;
  onPrint: () => void;
  busy: boolean;
  result: BlastPassport | null;
}) {
  const designed = result?.designed;
  const predicted = result?.predicted;
  const planned = result?.planned_cost;

  return (
    <section className="panel">
      <header><b>Официальный паспорт</b><span>26</span></header>
      <div className="panel-body">
        <small>
          Инженерный документ: проектные параметры, прогноз (явно помечен), смета, сейсмика и дробление.
          Колонки DESIGNED / EXECUTED / PREDICTED / MEASURED не смешиваются. Автоутверждения нет.
        </small>
        <div className="plans-actions">
          <button className="calculate-button" onClick={onAssemble} disabled={busy}>
            {busy ? "Собираем паспорт…" : "Собрать паспорт"}
          </button>
          <button className="secondary-button" onClick={onPrint} disabled={busy || !result}>
            Печать
          </button>
        </div>
        {result && designed && predicted && (
          <>
            <div className="passport-roles">
              <RoleChip role="designed" />
              <RoleChip role="executed" />
              <RoleChip role="predicted" />
              <RoleChip role="measured" />
            </div>
            <small className="passport-disclaimer">{result.disclaimer}</small>
            <small>утверждён автоматически: нет · паспорт не перезаписан</small>
            <div className="frag-caption">
              <b>{result.name || "Паспорт БВР"}</b>
              <span>{result.generated_at || "черновик документа"}</span>
            </div>
            <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <Metric label="Скважин (проект)" value={designed.hole_count} unit="шт." digits={0} />
              <Metric label="Масса ВВ" value={designed.explosive_mass_kg} unit="кг" digits={0} />
              <Metric label="X50 прогноз" value={predicted.x50_mm} unit="мм" digits={0} />
              <Metric label="Негабарит прогноз" value={predicted.oversize_pct} unit="%" digits={2} />
              <Metric label="PPV прогноз" value={predicted.ppv_mm_s} unit="мм/с" digits={2} />
              <Metric label="Отброс прогноз" value={predicted.throw_m} unit="м" digits={2} />
              <Metric label="Плановая смета" value={planned?.total_amount_rub} unit="₽" digits={0} />
              <Metric label="Факт смета" value={result.measured.cost_rub} unit="₽" digits={0} />
            </div>
            <div className="passport-table">
              <div className="passport-head">
                <span>Показатель</span>
                <span>проект</span>
                <span>исполнение</span>
                <span>прогноз</span>
                <span>замер</span>
              </div>
              {result.comparison.map((row) => (
                <div key={row.key} className="passport-row">
                  <span>{row.label}<small> {row.unit}</small></span>
                  <b className="col-designed">{cell(row.designed, digitsFor(row))}</b>
                  <b className="col-executed">{cell(row.executed, digitsFor(row))}</b>
                  <b className="col-predicted">{cell(row.predicted, digitsFor(row))}</b>
                  <b className="col-measured">{cell(row.measured, digitsFor(row))}</b>
                </div>
              ))}
            </div>
            {result.warnings[0] && <small className="frag-warnings">{result.warnings[0]}</small>}
          </>
        )}
      </div>
    </section>
  );
}
