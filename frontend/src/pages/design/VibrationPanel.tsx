import { ruNumber } from "../../lib/format";
import type {
  Receptor,
  ReceptorKind,
  ScaledDistanceConvention,
  VibrationMeasurement,
  VibrationModel,
  VibrationPredictResponse,
} from "../../types/design";
import {
  RECEPTOR_KIND_LABELS,
  SCALED_DISTANCE_FORMULAS,
  SCALED_DISTANCE_LABELS,
  emptyVibrationMeasurement,
} from "../../types/design";

const KINDS = Object.entries(RECEPTOR_KIND_LABELS) as Array<[ReceptorKind, string]>;
const CONVENTIONS = Object.entries(SCALED_DISTANCE_LABELS) as Array<[ScaledDistanceConvention, string]>;

function Metric({ label, value, unit, digits, warn }: { label: string; value: number; unit: string; digits: number; warn?: boolean }) {
  return (
    <div className={warn ? "vib-warn-metric" : undefined}>
      <span>{label}</span>
      <strong>{ruNumber(value, digits)}</strong>
      <small>{unit}</small>
    </div>
  );
}

export function VibrationPanel({
  model,
  onModelChange,
  receptors,
  selectedReceptorId,
  onSelectedReceptorIdChange,
  placing,
  onTogglePlacing,
  onUpsertReceptor,
  onDeleteReceptor,
  measurements,
  onUpsertMeasurement,
  onDeleteMeasurement,
  micWindowMs,
  onMicWindowChange,
  onPredict,
  busy,
  result,
}: {
  model: VibrationModel;
  onModelChange: (patch: Partial<VibrationModel>) => void;
  receptors: Receptor[];
  selectedReceptorId: string | null;
  onSelectedReceptorIdChange: (id: string | null) => void;
  placing: boolean;
  onTogglePlacing: () => void;
  onUpsertReceptor: (receptor: Receptor) => void;
  onDeleteReceptor: (id: string) => void;
  measurements: VibrationMeasurement[];
  onUpsertMeasurement: (item: VibrationMeasurement) => void;
  onDeleteMeasurement: (id: string) => void;
  micWindowMs: number;
  onMicWindowChange: (value: number) => void;
  onPredict: () => void;
  busy: boolean;
  result: VibrationPredictResponse | null;
}) {
  const selected = receptors.find((item) => item.id === selectedReceptorId) ?? null;
  const selectedMeasurements = measurements.filter((item) => item.receptor_id === selectedReceptorId);
  const selectedPrediction = result?.predictions.find((item) => item.receptor_id === selectedReceptorId);

  function patchSelected(patch: Partial<Receptor>) {
    if (!selected) return;
    onUpsertReceptor({ ...selected, ...patch });
  }

  return (
    <section className="panel">
      <header><b>Сейсмика</b><span>09</span></header>
      <div className="panel-body">
        <small>
          Площадочный закон <b>PPV = K × SDⁿ</b>. Конвенция приведённого расстояния хранится в модели
          и не подменяется молча. Прогноз и замер — разные сущности.
        </small>

        <label>
          Конвенция SD
          <select
            value={model.scaled_distance}
            onChange={(e) => onModelChange({ scaled_distance: e.target.value as ScaledDistanceConvention })}
          >
            {CONVENTIONS.map(([value, label]) => (
              <option key={value} value={value}>{label} · {SCALED_DISTANCE_FORMULAS[value]}</option>
            ))}
          </select>
        </label>
        <div className="field-pair">
          <label>K
            <input type="number" step="1" value={model.k} onChange={(e) => onModelChange({ k: Number(e.target.value) })} />
          </label>
          <label>n
            <input type="number" step="0.1" value={model.n} onChange={(e) => onModelChange({ n: Number(e.target.value) })} />
          </label>
        </div>
        <div className="field-pair">
          <label>Источник калибровки
            <input
              type="text"
              value={model.calibration_source}
              onChange={(e) => onModelChange({ calibration_source: e.target.value })}
              placeholder="кампания / литература"
            />
          </label>
          <label>Доверие, 0–1
            <input
              type="number"
              min="0"
              max="1"
              step="0.05"
              value={model.confidence}
              onChange={(e) => onModelChange({ confidence: Number(e.target.value) })}
            />
          </label>
        </div>

        <div className="geology-list">
          {receptors.length === 0 && (
            <div className="surface-card empty"><b>Рецепторов нет</b><small>поставьте объект на план</small></div>
          )}
          {receptors.map((receptor) => {
            const pred = result?.predictions.find((item) => item.receptor_id === receptor.id);
            return (
              <button
                key={receptor.id}
                type="button"
                className={`geology-card${receptor.id === selectedReceptorId ? " active" : ""}`}
                onClick={() => onSelectedReceptorIdChange(receptor.id)}
              >
                <i className={`receptor-swatch kind-${receptor.kind}`} />
                <div>
                  <b>{receptor.name || receptor.id}</b>
                  <small>
                    {RECEPTOR_KIND_LABELS[receptor.kind] ?? receptor.kind}
                    {pred ? ` · ${ruNumber(pred.ppv_mm_s, 2)} мм/с` : ""}
                    {pred?.exceeds_limit ? " · выше нормы" : ""}
                  </small>
                </div>
              </button>
            );
          })}
        </div>

        <div className="plans-actions">
          <button type="button" className={`secondary-button${placing ? " active" : ""}`} onClick={onTogglePlacing}>
            {placing ? "Кликните план" : "Поставить рецептор"}
          </button>
        </div>

        {selected && (
          <>
            <label>
              Название
              <input type="text" value={selected.name} onChange={(e) => patchSelected({ name: e.target.value })} />
            </label>
            <div className="field-pair">
              <label>
                Тип
                <select
                  value={selected.kind}
                  onChange={(e) => patchSelected({ kind: e.target.value as ReceptorKind, name: selected.name || RECEPTOR_KIND_LABELS[e.target.value as ReceptorKind] })}
                >
                  {KINDS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>
              <label>
                Норма PPV, мм/с
                <input
                  type="number"
                  min="0"
                  step="0.1"
                  value={selected.ppv_limit_mm_s ?? ""}
                  placeholder="нет"
                  onChange={(e) => patchSelected({ ppv_limit_mm_s: e.target.value === "" ? null : Number(e.target.value) })}
                />
              </label>
            </div>
            <small>X {ruNumber(selected.location.x, 1)} · Y {ruNumber(selected.location.y, 1)} м</small>
            <button type="button" className="ghost-button" onClick={() => onDeleteReceptor(selected.id)}>Удалить рецептор</button>
          </>
        )}

        <label>
          Окно MIC, мс
          <input type="number" min="1" step="1" value={micWindowMs} onChange={(e) => onMicWindowChange(Number(e.target.value))} />
        </label>
        <button className="calculate-button" onClick={onPredict} disabled={busy}>
          {busy ? "Считаем PPV…" : "Рассчитать сейсмику"}
        </button>
        <small>MIC берётся из событий инициирования в выбранном окне. Замеры ниже не подменяют прогноз.</small>

        {result && (
          <>
            <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <Metric label="MIC" value={result.mic.mic_kg} unit="кг" digits={1} />
              <Metric label="Окно" value={result.mic_window_ms} unit="мс" digits={0} />
            </div>
            <small>
              Закон {result.convention_formula}. Источник: {result.model.calibration_source || "не задан"},
              доверие {ruNumber(result.model.confidence, 2)}.
            </small>
            {selectedPrediction && (
              <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
                <Metric
                  label="Прогноз PPV"
                  value={selectedPrediction.ppv_mm_s}
                  unit="мм/с"
                  digits={2}
                  warn={selectedPrediction.exceeds_limit}
                />
                <Metric label="Расстояние" value={selectedPrediction.distance_m} unit="м" digits={1} />
                <Metric label="SD" value={selectedPrediction.scaled_distance_value} unit="" digits={4} />
                <Metric label="Замеров" value={selectedPrediction.measured.length} unit="шт." digits={0} />
              </div>
            )}
            {result.warnings.length > 0 && (
              <small className="frag-warnings">{result.warnings.slice(0, 4).join(" ")}</small>
            )}
            <div className="vib-table">
              {result.predictions.map((row) => (
                <div key={row.receptor_id} className={`vib-row${row.exceeds_limit ? " over" : ""}`}>
                  <span>{row.receptor_name || row.receptor_id}</span>
                  <small>{ruNumber(row.distance_m, 0)} м</small>
                  <b>{ruNumber(row.ppv_mm_s, 2)} мм/с</b>
                </div>
              ))}
            </div>
          </>
        )}

        {selected && (
          <div className="tie-edit-block">
            <b>Замеры PPV</b>
            {selectedMeasurements.length === 0 && <small>Замеров нет — они не смешиваются с прогнозом.</small>}
            {selectedMeasurements.map((item) => (
              <div key={item.id} className="tie-row">
                <input
                  type="number"
                  step="0.1"
                  value={item.ppv_mm_s}
                  onChange={(e) => onUpsertMeasurement({ ...item, ppv_mm_s: Number(e.target.value) })}
                />
                <small>мм/с</small>
                <input
                  type="number"
                  step="0.1"
                  placeholder="Гц"
                  value={item.frequency_hz ?? ""}
                  onChange={(e) => onUpsertMeasurement({
                    ...item,
                    frequency_hz: e.target.value === "" ? null : Number(e.target.value),
                  })}
                />
                <small>Гц</small>
                <button type="button" className="ghost-button" onClick={() => onDeleteMeasurement(item.id)}>×</button>
              </div>
            ))}
            <button
              type="button"
              className="secondary-button"
              onClick={() => onUpsertMeasurement(emptyVibrationMeasurement(selected.id, measurements))}
            >
              Добавить замер
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
