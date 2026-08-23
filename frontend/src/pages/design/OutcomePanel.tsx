import { ruNumber } from "../../lib/format";
import {
  OUTCOME_MODEL_TYPES,
  OUTCOME_STATUS_LABELS,
  type CalibrationAlgorithm,
  type OutcomeModel,
  type OutcomeModelType,
  type OutcomePanelResponse,
  type OutcomePredictResponse,
  type OutcomeStatus,
  type OutcomeSummary,
  type OutcomeTargetPrediction,
} from "../../types/design";
import { UncertaintyBlock } from "./UncertaintyBlock";

function statusLabel(status: string): string {
  return OUTCOME_STATUS_LABELS[status as OutcomeStatus] ?? status;
}

function formatValue(value: number | null | undefined, digits: number): string {
  if (value == null || Number.isNaN(value)) return "—";
  return ruNumber(value, digits);
}

function targetDigits(name: string): number {
  return name === "toe_probability" || name === "max_ppv_mm_s" ? 2 : 1;
}

function PanelMetric({
  title,
  item,
  unit,
  digits,
}: {
  title: string;
  item: OutcomeTargetPrediction | null | undefined;
  unit: string;
  digits: number;
}) {
  return (
    <div>
      <span>{title}</span>
      <strong>{formatValue(item?.value, digits)}</strong>
      <small>{unit}</small>
      {item?.uncertainty?.lower != null && item.uncertainty.upper != null && (
        <small>интервал {formatValue(item.uncertainty.lower, digits)}–{formatValue(item.uncertainty.upper, digits)}</small>
      )}
    </div>
  );
}

export function OutcomePanel({
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
  panel,
  busy,
  onRefresh,
  onTrain,
  onOpen,
  onMarkProduction,
  onPredictType,
  onPredictAll,
}: {
  siteId: string;
  datasetId: string;
  datasetLabel: string;
  modelType: OutcomeModelType;
  onModelTypeChange: (value: OutcomeModelType) => void;
  algorithm: string;
  onAlgorithmChange: (value: string) => void;
  algorithms: CalibrationAlgorithm[];
  models: OutcomeSummary[];
  selected: OutcomeModel | OutcomeSummary | null;
  overlay: OutcomePredictResponse | null;
  panel: OutcomePanelResponse | null;
  busy: boolean;
  onRefresh: () => void;
  onTrain: () => void;
  onOpen: (modelId: string) => void;
  onMarkProduction: () => void;
  onPredictType: () => void;
  onPredictAll: () => void;
}) {
  const availableAlgorithms = algorithms.filter((item) => item.available);
  const algorithmOptions: CalibrationAlgorithm[] = availableAlgorithms.length
    ? availableAlgorithms
    : [{ name: "random_forest", label: "Random Forest", kind: "builtin", available: true }];
  const visibleModels = models.filter((item) => item.model_type === modelType);

  return (
    <section className="panel">
      <header><b>Прогноз исходов</b><span>17</span></header>
      <div className="panel-body">
        <small>
          Отдельные модели кусковатости, сейсмики, негабарита и риска забоя. Рекомендация не перезаписывает проект.
        </small>
        <label>Тип модели
          <select value={modelType} onChange={(e) => onModelTypeChange(e.target.value as OutcomeModelType)}>
            {OUTCOME_MODEL_TYPES.map((item) => (
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
        {visibleModels.length > 0 && (
          <ul className="plans-list">
            {visibleModels.map((item) => (
              <li key={item.model_id} className={item.model_id === selected?.model_id ? "active" : ""}>
                <button type="button" className="plans-list-open" onClick={() => onOpen(item.model_id)}>
                  <b>{item.class_name || item.model_type} v{item.model_version}</b>
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
            {selected.metrics?.mae != null && (
              <small>MAE {ruNumber(Number(selected.metrics.mae), 2)} · {selected.primary_target || "цель"}</small>
            )}
            <div className="plans-actions">
              <button type="button" className="secondary-button" onClick={onMarkProduction} disabled={busy || selected.status === "production"}>
                Пометить как производственную
              </button>
              <button type="button" className="calculate-button" onClick={onPredictType} disabled={busy}>
                {busy ? "Считаем…" : "Прогноз этой модели"}
              </button>
            </div>
          </div>
        )}
        <div className="plans-actions">
          <button type="button" className="calculate-button" onClick={onPredictAll} disabled={busy}>
            {busy ? "Считаем…" : "Прогноз X50 / X80 / негабарит / PPV / забой"}
          </button>
        </div>
        {overlay && overlay.prediction_applied && (
          <div className="outcome-overlay">
            <small>Слой рекомендации · проект не изменён</small>
            <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
              {Object.values(overlay.predictions).map((item) => (
                <div key={item.target_name}>
                  <span>{item.label || item.target_name}</span>
                  <strong>{formatValue(item.value, targetDigits(item.target_name))}</strong>
                  <small>{item.unit}</small>
                </div>
              ))}
            </div>
            <UncertaintyBlock
              label={overlay.predictions[overlay.primary_target]?.label || overlay.primary_target || "исхода"}
              value={overlay.prediction ?? overlay.predicted}
              unit={overlay.unit}
              digits={targetDigits(overlay.primary_target)}
              uncertainty={overlay.uncertainty}
              confidence={overlay.confidence}
              confidenceLabelText={overlay.confidence_label}
              similarityScore={overlay.similarity_score}
              comparableCount={overlay.comparable_count}
              applicabilityWarning={overlay.applicability_warning}
            />
            <small>
              {overlay.class_name || overlay.model_type} v{overlay.model_version} · {statusLabel(overlay.status)}
            </small>
            {overlay.warnings.filter((item) => item !== overlay.applicability_warning)[0] && (
              <small className="frag-warnings">
                {overlay.warnings.filter((item) => item !== overlay.applicability_warning)[0]}
              </small>
            )}
          </div>
        )}
        {panel && (
          <div className="outcome-overlay">
            <small>Рекомендуемые исходы · ML не утверждает паспорт</small>
            <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
              <PanelMetric title="X50" item={panel.x50_mm} unit="мм" digits={1} />
              <PanelMetric title="X80" item={panel.x80_mm} unit="мм" digits={1} />
              <PanelMetric title="Негабарит" item={panel.oversize_pct} unit="%" digits={1} />
              <PanelMetric title="PPV" item={panel.ppv} unit="мм/с" digits={2} />
              <PanelMetric title="Риск забоя" item={panel.toe_risk} unit="0–1" digits={2} />
            </div>
            {panel.x50_mm?.prediction_applied && (
              <UncertaintyBlock
                label="X50"
                value={panel.x50_mm.value}
                unit="мм"
                digits={1}
                uncertainty={panel.x50_mm.uncertainty}
                confidence={panel.x50_mm.confidence}
                confidenceLabelText={panel.x50_mm.confidence_label}
                similarityScore={panel.x50_mm.similarity_score}
                comparableCount={panel.x50_mm.comparable_count}
                applicabilityWarning={panel.applicability_warning || panel.x50_mm.applicability_warning}
              />
            )}
            <small>
              {panel.models.fragmentation?.prediction_applied
                ? `FragmentationModel v${panel.models.fragmentation.model_version}`
                : "Нет модели кусковатости"}
              {" · "}
              {panel.models.vibration?.prediction_applied
                ? `VibrationModel v${panel.models.vibration.model_version}`
                : "нет модели PPV"}
              {" · "}
              {panel.models.oversize?.prediction_applied
                ? `OversizeModel v${panel.models.oversize.model_version}`
                : "нет модели негабарита"}
              {" · "}
              {panel.models.toe_risk?.prediction_applied
                ? `ToeRiskModel v${panel.models.toe_risk.model_version}`
                : "нет модели забоя"}
            </small>
            {panel.warnings.filter((item) => item !== panel.applicability_warning)[0] && (
              <small className="frag-warnings">
                {panel.warnings.filter((item) => item !== panel.applicability_warning)[0]}
              </small>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
