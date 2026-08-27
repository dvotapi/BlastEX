import { useMemo, useState } from "react";
import { ruNumber } from "../../lib/format";
import type {
  AsFiredCompareResponse,
  AsFiredHole,
  FiredDeviation,
  Hole,
  InitiationNetwork,
} from "../../types/design";
import { AS_FIRED_METRIC_LABELS, emptyAsFired } from "../../types/design";
import { RoleBadge } from "./RoleBadge";

const DETONATOR_KINDS = [
  { value: "electronic", label: "Электронный" },
  { value: "nonel", label: "НСИ" },
  { value: "detonating_cord", label: "ДШ" },
];

function Metric({ label, value, unit, digits, warn }: { label: string; value: number | null; unit: string; digits: number; warn?: boolean }) {
  return (
    <div className={warn ? "vib-warn-metric" : undefined}>
      <span>{label}</span>
      <strong>{ruNumber(value, digits)}</strong>
      <small>{unit}</small>
    </div>
  );
}

function warnAbs(value: number | null, limit: number): boolean {
  return value !== null && Math.abs(value) > limit;
}

export function AsFiredPanel({
  holes,
  network,
  asFired,
  timesMs,
  selectedHoleId,
  onSelectedHoleIdChange,
  onRecord,
  onDelete,
  onCompare,
  busy,
  result,
  locked = false,
}: {
  holes: Hole[];
  network: InitiationNetwork;
  asFired: AsFiredHole[];
  timesMs: Record<string, number> | null;
  selectedHoleId: string | null;
  onSelectedHoleIdChange: (id: string | null) => void;
  onRecord: (item: AsFiredHole) => void;
  onDelete: (designHoleId: string) => void;
  onCompare: () => void;
  busy: boolean;
  result: AsFiredCompareResponse | null;
  locked?: boolean;
}) {
  const selectedDesigned = holes.find((hole) => hole.id === selectedHoleId) ?? null;
  const selectedExecuted = asFired.find((item) => item.design_hole_id === selectedHoleId) ?? null;
  const draft = useMemo(
    () => (selectedExecuted ? selectedExecuted : selectedHoleId ? emptyAsFired(selectedHoleId, network, timesMs?.[selectedHoleId] ?? 0) : null),
    [selectedExecuted, selectedHoleId, network, timesMs],
  );
  const [form, setForm] = useState<AsFiredHole | null>(null);
  const current = form && form.design_hole_id === selectedHoleId ? form : draft;
  const selectedDeviation = result?.deviations.find((row) => row.design_hole_id === selectedHoleId) ?? null;

  function patch(next: Partial<AsFiredHole>) {
    if (!current) return;
    setForm({ ...current, ...next, role: "executed" });
  }

  function recordCurrent() {
    if (!current) return;
    onRecord({
      ...current,
      detonator: { ...current.detonator, hole_id: current.design_hole_id },
      role: "executed",
    });
    setForm(null);
  }

  return (
    <section className="panel">
      <header><b>Факт взрыва</b><RoleBadge role="executed" /></header>
      <div className="panel-body">
        <small>
          Проектная сеть не меняется. Здесь — фактический детонатор, программное время, проверенное время и отметка взрыва.
        </small>

        <div className="geology-list">
          {asFired.length === 0 && (
            <div className="surface-card empty"><b>Факта нет</b><small>выберите скважину и запишите время</small></div>
          )}
          {asFired.map((item) => {
            const row = result?.deviations.find((dev) => dev.design_hole_id === item.design_hole_id);
            return (
              <button
                key={item.design_hole_id}
                type="button"
                className={`geology-card${item.design_hole_id === selectedHoleId ? " active" : ""}`}
                onClick={() => {
                  onSelectedHoleIdChange(item.design_hole_id);
                  setForm(null);
                }}
              >
                <i className="as-fired-swatch" />
                <div>
                  <b>{item.design_hole_id}</b>
                  <small>
                    {row
                      ? `Δ ${ruNumber(row.programmed_time_delta_ms, 0)} мс`
                      : `${ruNumber(item.programmed_time_ms, 0)} мс`}
                  </small>
                </div>
              </button>
            );
          })}
        </div>

        {selectedDesigned && current && (
          <>
            <small>Проект {selectedDesigned.id} не меняется. Ниже — только факт.</small>
            <div className="field-pair">
              <label>Детонатор
                <input
                  type="text"
                  value={current.detonator.product}
                  onChange={(e) => patch({ detonator: { ...current.detonator, product: e.target.value } })}
                />
              </label>
              <label>Тип
                <select
                  value={current.detonator.kind}
                  onChange={(e) => patch({ detonator: { ...current.detonator, kind: e.target.value } })}
                >
                  {DETONATOR_KINDS.map((item) => (
                    <option key={item.value} value={item.value}>{item.label}</option>
                  ))}
                </select>
              </label>
            </div>
            <label>Идентификатор детонатора
              <input
                type="text"
                value={current.detonator.id}
                onChange={(e) => patch({ detonator: { ...current.detonator, id: e.target.value } })}
              />
            </label>
            <div className="field-pair">
              <label>Программное время, мс
                <input type="number" step="1" value={current.programmed_time_ms} onChange={(e) => patch({ programmed_time_ms: Number(e.target.value) })} />
              </label>
              <label>Проверенное время, мс
                <input
                  type="number"
                  step="1"
                  value={current.verified_time_ms ?? ""}
                  onChange={(e) => patch({ verified_time_ms: e.target.value === "" ? null : Number(e.target.value) })}
                />
              </label>
            </div>
            <label>Время взрыва
              <input type="text" placeholder="2026-08-23T14:30:00+00:00" value={current.firing_timestamp} onChange={(e) => patch({ firing_timestamp: e.target.value })} />
            </label>
            <div className="plans-actions">
              <button type="button" className="calculate-button" onClick={recordCurrent} disabled={busy || locked}>
                {busy ? "Пишем…" : "Записать факт"}
              </button>
              {selectedExecuted && (
                <button type="button" className="ghost-button" onClick={() => onDelete(selectedDesigned.id)} disabled={locked}>Удалить факт</button>
              )}
            </div>
          </>
        )}

        <button type="button" className="secondary-button" onClick={onCompare} disabled={busy || asFired.length === 0}>
          {busy ? "Считаем…" : "Сравнить с проектом"}
        </button>

        {result && (
          <>
            <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <Metric label="Записано" value={result.as_fired_count} unit="скв." digits={0} />
              <Metric label="Сравнено" value={result.compared_count} unit="скв." digits={0} />
            </div>
            {selectedDeviation && <FiredMetrics row={selectedDeviation} />}
            {result.warnings.length > 0 && (
              <small className="frag-warnings">{result.warnings.slice(0, 3).join(" ")}</small>
            )}
            <div className="as-drilled-table">
              <div className="as-fired-head">
                <span>Скважина</span>
                <span>Δ прогр.</span>
                <span>Δ факт</span>
                <span>Детонатор</span>
              </div>
              {result.deviations.map((row) => (
                <button
                  key={row.design_hole_id}
                  type="button"
                  className={`as-fired-row${warnAbs(row.programmed_time_delta_ms, 5) ? " over" : ""}${row.design_hole_id === selectedHoleId ? " active" : ""}`}
                  onClick={() => onSelectedHoleIdChange(row.design_hole_id)}
                >
                  <span>{row.design_hole_id}</span>
                  <b>{ruNumber(row.programmed_time_delta_ms, 0)}</b>
                  <b>{ruNumber(row.timing_error_ms, 0)}</b>
                  <b>{row.detonator_product_mismatch ? "≠" : "="}</b>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function FiredMetrics({ row }: { row: FiredDeviation }) {
  return (
    <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
      <Metric label="Проект, мс" value={row.designed_time_ms} unit="мс" digits={0} />
      <Metric label="Программа, мс" value={row.programmed_time_ms} unit="мс" digits={0} />
      <Metric label={AS_FIRED_METRIC_LABELS.programmed_time_delta_ms} value={row.programmed_time_delta_ms} unit="мс" digits={0} warn={warnAbs(row.programmed_time_delta_ms, 5)} />
      <Metric label={AS_FIRED_METRIC_LABELS.verified_time_delta_ms} value={row.verified_time_delta_ms} unit="мс" digits={0} warn={warnAbs(row.verified_time_delta_ms, 5)} />
      <Metric label={AS_FIRED_METRIC_LABELS.timing_error_ms} value={row.timing_error_ms} unit="мс" digits={0} warn={warnAbs(row.timing_error_ms, 2)} />
      <Metric label="Проверено, мс" value={row.verified_time_ms} unit="мс" digits={0} />
    </div>
  );
}
