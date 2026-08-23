import { ruNumber } from "../../lib/format";
import {
  CALIBRATION_MODEL_TYPES,
  CALIBRATION_STATUS_LABELS,
  type CalibrationAlgorithm,
  type CalibrationModel,
  type CalibrationModelType,
  type CalibrationPredictResponse,
  type CalibrationStatus,
  type CalibrationSummary,
} from "../../types/design";
import { UncertaintyBlock } from "./UncertaintyBlock";

function statusLabel(status: string): string {
  return CALIBRATION_STATUS_LABELS[status as CalibrationStatus] ?? status;
}

export function CalibrationPanel({
  siteId,
  datasetId,
  datasetLabel,
  modelType,
  onModelTypeChange,
  algorithm,
  onAlgorithmChange,
  algorithms,
  models,
  selected,
  overlay,
  busy,
  onRefresh,
  onTrain,
  onOpen,
  onMarkProduction,
  onApplyOverlay,
}: {
  siteId: string;
  datasetId: string;
  datasetLabel: string;
  modelType: CalibrationModelType;
  onModelTypeChange: (value: CalibrationModelType) => void;
  algorithm: string;
  onAlgorithmChange: (value: string) => void;
  algorithms: CalibrationAlgorithm[];
  models: CalibrationSummary[];
  selected: CalibrationModel | CalibrationSummary | null;
  overlay: CalibrationPredictResponse | null;
  busy: boolean;
  onRefresh: () => void;
  onTrain: () => void;
  onOpen: (modelId: string) => void;
  onMarkProduction: () => void;
  onApplyOverlay: () => void;
}) {
  const availableAlgorithms = algorithms.filter((item) => item.available);
  const algorithmOptions: CalibrationAlgorithm[] = availableAlgorithms.length
    ? availableAlgorithms
    : [{ name: "random_forest", label: "Random Forest", kind: "builtin", available: true }];
  const unit = overlay?.unit || (modelType === "ppv_residual" ? "мм/с" : modelType === "oversize_residual" ? "%" : "мм");

  return (
    <section className="panel">
      <header><b>Калибровка площадки</b><span>16</span></header>
      <div className="panel-body">
        <small>
          Гибрид: инженерный базис (Kuz-Ram / PPV) плюс ML-невязка. Рекомендация не перезаписывает проект.
        </small>
        <label>Тип модели
          <select value={modelType} onChange={(e) => onModelTypeChange(e.target.value as CalibrationModelType)}>
            {CALIBRATION_MODEL_TYPES.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
        </label>
        <label>Алгоритм
          <select value={algorithm} onChange={(e) => onAlgorithmChange(e.target.value)}>
            {algorithmOptions.map((item) => (
              <option key={item.name} value={item.name}>{item.label}</option>
            ))}
          </select>
        </label>
        <small>
          Снимок: {datasetLabel || "не выбран"} {siteId ? `· площадка ${siteId}` : ""}
        </small>
        <div className="plans-actions">
          <button type="button" className="calculate-button" onClick={onTrain} disabled={busy || !datasetId}>
            {busy ? "Обучаем…" : "Обучить по снимку"}
          </button>
          <button type="button" className="secondary-button" onClick={onRefresh} disabled={busy}>
            Обновить список
          </button>
        </div>
        {models.length > 0 && (
          <ul className="plans-list">
            {models.map((item) => (
              <li key={item.model_id} className={item.model_id === selected?.model_id ? "active" : ""}>
                <button type="button" className="plans-list-open" onClick={() => onOpen(item.model_id)}>
                  <b>{item.model_type} v{item.model_version}</b>
                  <small>
                    {statusLabel(item.status)} · {item.algorithm} · {item.sample_count} обр.
                  </small>
                </button>
              </li>
            ))}
          </ul>
        )}
        {selected && (
          <div className="dataset-detail">
            <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
              <div><span>Статус</span><strong>{statusLabel(selected.status)}</strong></div>
              <div><span>Версия</span><strong>{selected.model_version}</strong></div>
              <div><span>Датасет</span><strong>v{selected.training_dataset_version}</strong></div>
            </div>
            <small>Схема признаков: {selected.feature_schema_version || "—"}</small>
            <small>Обучение: {selected.training_date ? new Date(selected.training_date).toLocaleString("ru-RU") : "—"}</small>
            {selected.metrics?.calibrated_mae != null && (
              <small>
                MAE базис {ruNumber(Number(selected.metrics.baseline_mae), 2)} → калибровка {ruNumber(Number(selected.metrics.calibrated_mae), 2)}
              </small>
            )}
            <div className="plans-actions">
              <button type="button" className="secondary-button" onClick={onMarkProduction} disabled={busy || selected.status === "production"}>
                Пометить как производственную
              </button>
              <button type="button" className="calculate-button" onClick={onApplyOverlay} disabled={busy}>
                {busy ? "Считаем…" : "Применить как рекомендацию"}
              </button>
            </div>
          </div>
        )}
        {overlay && (
          <div className="calibration-overlay">
            <small>Слой рекомендации · проект не изменён</small>
            <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
              <div><span>Базис</span><strong>{ruNumber(overlay.baseline, 2)}</strong><small>{unit}</small></div>
              <div><span>Невязка</span><strong>{ruNumber(overlay.residual, 2)}</strong><small>{unit}</small></div>
              <div><span>Калибровка</span><strong>{ruNumber(overlay.calibrated, 2)}</strong><small>{unit}</small></div>
            </div>
            <UncertaintyBlock
              label="калибровки"
              value={overlay.prediction ?? overlay.calibrated}
              unit={unit}
              digits={2}
              uncertainty={overlay.uncertainty}
              confidence={overlay.confidence}
              confidenceLabelText={overlay.confidence_label}
              similarityScore={overlay.similarity_score}
              comparableCount={overlay.comparable_count}
              applicabilityWarning={overlay.applicability_warning}
            />
            <small>
              {overlay.calibration_applied
                ? `${overlay.model_type} v${overlay.model_version} · ${statusLabel(overlay.status)}`
                : "Калибровка не применена, показан только инженерный базис"}
            </small>
            {overlay.warnings.filter((item) => item !== overlay.applicability_warning)[0] && (
              <small className="frag-warnings">
                {overlay.warnings.filter((item) => item !== overlay.applicability_warning)[0]}
              </small>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
