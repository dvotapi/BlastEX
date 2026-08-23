import { useMemo, useState } from "react";
import { ruNumber } from "../../lib/format";
import type { AsDrilledCompareResponse, AsDrilledHole, Hole, HoleDeviation, Point3 } from "../../types/design";
import { AS_DRILLED_METRIC_LABELS, emptyAsDrilled } from "../../types/design";

function Metric({ label, value, unit, digits, warn }: { label: string; value: number | null; unit: string; digits: number; warn?: boolean }) {
  return (
    <div className={warn ? "vib-warn-metric" : undefined}>
      <span>{label}</span>
      <strong>{ruNumber(value, digits)}</strong>
      <small>{unit}</small>
    </div>
  );
}

function warnOffset(value: number | null, limit: number): boolean {
  return value !== null && Math.abs(value) > limit;
}

export function AsDrilledPanel({
  holes,
  asDrilled,
  selectedHoleId,
  onSelectedHoleIdChange,
  onRecord,
  onDelete,
  onCompare,
  onImportMwd,
  busy,
  result,
  showOverlay,
  onToggleOverlay,
}: {
  holes: Hole[];
  asDrilled: AsDrilledHole[];
  selectedHoleId: string | null;
  onSelectedHoleIdChange: (id: string | null) => void;
  onRecord: (item: AsDrilledHole) => void;
  onDelete: (designHoleId: string) => void;
  onCompare: () => void;
  onImportMwd: (designHoleId: string, samples: Record<string, number | null>[]) => void;
  busy: boolean;
  result: AsDrilledCompareResponse | null;
  showOverlay: boolean;
  onToggleOverlay: () => void;
}) {
  const selectedDesigned = holes.find((hole) => hole.id === selectedHoleId) ?? null;
  const selectedExecuted = asDrilled.find((item) => item.design_hole_id === selectedHoleId) ?? null;
  const draft = useMemo(
    () => (selectedExecuted ? selectedExecuted : selectedDesigned ? emptyAsDrilled(selectedDesigned) : null),
    [selectedDesigned, selectedExecuted],
  );
  const [form, setForm] = useState<AsDrilledHole | null>(null);
  const [mwdText, setMwdText] = useState("[\n  {\"depth_m\": 0, \"penetration_rate\": 1.2, \"rotation_pressure\": 140, \"feed_pressure\": 90, \"torque\": 2100, \"air_pressure\": 18}\n]");
  const current = form && form.design_hole_id === selectedHoleId ? form : draft;
  const selectedDeviation = result?.deviations.find((row) => row.design_hole_id === selectedHoleId) ?? null;

  function patch(next: Partial<AsDrilledHole>) {
    if (!current) return;
    setForm({ ...current, ...next, role: "executed" });
  }

  function patchPoint(key: "actual_collar" | "actual_toe", axis: keyof Point3, value: number) {
    if (!current) return;
    patch({ [key]: { ...current[key], [axis]: value } });
  }

  function recordCurrent() {
    if (!current) return;
    onRecord({ ...current, role: "executed" });
    setForm(null);
  }

  function importMwd() {
    if (!selectedHoleId) return;
    try {
      const parsed = JSON.parse(mwdText);
      const rows = Array.isArray(parsed) ? parsed : parsed.samples ?? parsed.rows ?? [];
      onImportMwd(selectedHoleId, rows);
    } catch {
      onImportMwd(selectedHoleId, []);
    }
  }

  return (
    <section className="panel">
      <header><b>Факт бурения</b><span>10</span></header>
      <div className="panel-body">
        <small>
          Проект и факт хранятся отдельно. Запись устья, забоя или MWD не переписывает проектные скважины.
          Импорт MWD — только физические величины, без привязки к производителю станка.
        </small>

        <label className="check-row">
          <input type="checkbox" checked={showOverlay} onChange={onToggleOverlay} />
          Показать факт на плане
        </label>

        <div className="geology-list">
          {asDrilled.length === 0 && (
            <div className="surface-card empty"><b>Факта нет</b><small>выберите скважину и запишите устье</small></div>
          )}
          {asDrilled.map((item) => {
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
                <i className="as-drilled-swatch" />
                <div>
                  <b>{item.design_hole_id}</b>
                  <small>
                    {row ? `устье ${ruNumber(row.collar_offset_m, 2)} м` : `${item.mwd_samples.length} MWD`}
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
              <label>Устье X, м
                <input type="number" step="0.01" value={current.actual_collar.x} onChange={(e) => patchPoint("actual_collar", "x", Number(e.target.value))} />
              </label>
              <label>Устье Y, м
                <input type="number" step="0.01" value={current.actual_collar.y} onChange={(e) => patchPoint("actual_collar", "y", Number(e.target.value))} />
              </label>
            </div>
            <div className="field-pair">
              <label>Забой X, м
                <input type="number" step="0.01" value={current.actual_toe.x} onChange={(e) => patchPoint("actual_toe", "x", Number(e.target.value))} />
              </label>
              <label>Забой Y, м
                <input type="number" step="0.01" value={current.actual_toe.y} onChange={(e) => patchPoint("actual_toe", "y", Number(e.target.value))} />
              </label>
            </div>
            <div className="field-pair">
              <label>Глубина, м
                <input type="number" step="0.01" min="0" value={current.actual_depth} onChange={(e) => patch({ actual_depth: Number(e.target.value) })} />
              </label>
              <label>Диаметр, мм
                <input type="number" step="1" min="0" value={current.actual_diameter} onChange={(e) => patch({ actual_diameter: Number(e.target.value) })} />
              </label>
            </div>
            <div className="plans-actions">
              <button type="button" className="calculate-button" onClick={recordCurrent} disabled={busy}>
                {busy ? "Пишем…" : "Записать факт"}
              </button>
              {selectedExecuted && (
                <button type="button" className="ghost-button" onClick={() => onDelete(selectedDesigned.id)}>Удалить факт</button>
              )}
            </div>
          </>
        )}

        <button type="button" className="secondary-button" onClick={onCompare} disabled={busy || asDrilled.length === 0}>
          {busy ? "Считаем…" : "Сравнить с проектом"}
        </button>

        {result && (
          <>
            <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <Metric label="Записано" value={result.as_drilled_count} unit="скв." digits={0} />
              <Metric label="Сравнено" value={result.compared_count} unit="скв." digits={0} />
            </div>
            {selectedDeviation && <DeviationMetrics row={selectedDeviation} />}
            {result.warnings.length > 0 && (
              <small className="frag-warnings">{result.warnings.slice(0, 3).join(" ")}</small>
            )}
            <div className="as-drilled-table">
              <div className="as-drilled-head">
                <span>Скважина</span>
                <span>Устье</span>
                <span>Забой</span>
                <span>Глубина</span>
              </div>
              {result.deviations.map((row) => (
                <button
                  key={row.design_hole_id}
                  type="button"
                  className={`as-drilled-row${warnOffset(row.collar_offset_m, 0.5) ? " over" : ""}${row.design_hole_id === selectedHoleId ? " active" : ""}`}
                  onClick={() => onSelectedHoleIdChange(row.design_hole_id)}
                >
                  <span>{row.design_hole_id}</span>
                  <b>{ruNumber(row.collar_offset_m, 2)}</b>
                  <b>{ruNumber(row.toe_offset_m, 2)}</b>
                  <b>{ruNumber(row.depth_deviation_m, 2)}</b>
                </button>
              ))}
            </div>
          </>
        )}

        {selectedHoleId && (
          <div className="tie-edit-block">
            <b>Импорт MWD</b>
            <small>JSON-массив: глубина, скорость проходки, давление вращения, подача, крутящий момент, воздух.</small>
            <textarea className="as-drilled-mwd" rows={4} value={mwdText} onChange={(e) => setMwdText(e.target.value)} />
            <button type="button" className="secondary-button" onClick={importMwd} disabled={busy}>
              Привязать MWD к {selectedHoleId}
            </button>
            {selectedExecuted && selectedExecuted.mwd_samples.length > 0 && (
              <small>Записано {selectedExecuted.mwd_samples.length} отсчётов MWD.</small>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function DeviationMetrics({ row }: { row: HoleDeviation }) {
  return (
    <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
      <Metric label={AS_DRILLED_METRIC_LABELS.collar_offset_m} value={row.collar_offset_m} unit="м" digits={2} warn={warnOffset(row.collar_offset_m, 0.5)} />
      <Metric label={AS_DRILLED_METRIC_LABELS.toe_offset_m} value={row.toe_offset_m} unit="м" digits={2} warn={warnOffset(row.toe_offset_m, 0.8)} />
      <Metric label={AS_DRILLED_METRIC_LABELS.depth_deviation_m} value={row.depth_deviation_m} unit="м" digits={2} warn={warnOffset(row.depth_deviation_m, 0.5)} />
      <Metric label={AS_DRILLED_METRIC_LABELS.angle_deviation_deg} value={row.angle_deviation_deg} unit="°" digits={1} warn={warnOffset(row.angle_deviation_deg, 2)} />
      <Metric label={AS_DRILLED_METRIC_LABELS.azimuth_deviation_deg} value={row.azimuth_deviation_deg} unit="°" digits={1} warn={warnOffset(row.azimuth_deviation_deg, 5)} />
      <Metric label={AS_DRILLED_METRIC_LABELS.actual_burden_m} value={row.actual_burden_m} unit="м" digits={2} />
      <Metric label={AS_DRILLED_METRIC_LABELS.actual_spacing_m} value={row.actual_spacing_m} unit="м" digits={2} />
    </div>
  );
}
