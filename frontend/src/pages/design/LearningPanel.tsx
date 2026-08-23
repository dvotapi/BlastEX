import { ruNumber } from "../../lib/format";
import {
  LEARNING_SCOPE_LABELS,
  OUTCOME_MODEL_TYPES,
  OUTCOME_STATUS_LABELS,
  type CalibrationAlgorithm,
  type LearningModel,
  type LearningPredictResponse,
  type LearningScope,
  type LearningStatus,
  type LearningSummary,
  type OutcomeModelType,
} from "../../types/design";
import { UncertaintyBlock } from "./UncertaintyBlock";
import { ExplanationBlock } from "./ExplanationBlock";

function statusLabel(status: string): string {
  return OUTCOME_STATUS_LABELS[status as LearningStatus] ?? status;
}

function scopeLabel(scope: string): string {
  return LEARNING_SCOPE_LABELS[scope as LearningScope] ?? scope;
}

function formatValue(value: number | null | undefined, digits: number): string {
  if (value == null || Number.isNaN(value)) return "—";
  return ruNumber(value, digits);
}

function targetDigits(name: string): number {
  return name === "toe_probability" || name === "max_ppv_mm_s" ? 2 : 1;
}

export function LearningPanel({
  siteId,
  datasetLabel,
  snapshotCount,
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
  onTrainGlobal,
  onTrainSite,
  onOpen,
  onMarkProduction,
  onPredict,
}: {
  siteId: string;
  datasetLabel: string;
  snapshotCount: number;
  modelType: OutcomeModelType;
  onModelTypeChange: (value: OutcomeModelType) => void;
  algorithm: string;
  onAlgorithmChange: (value: string) => void;
  algorithms: CalibrationAlgorithm[];
  models: LearningSummary[];
  selected: LearningModel | LearningSummary | null;
  overlay: LearningPredictResponse | null;
  busy: boolean;
  onRefresh: () => void;
  onTrainGlobal: () => void;
  onTrainSite: () => void;
  onOpen: (modelId: string) => void;
  onMarkProduction: () => void;
  onPredict: () => void;
}) {
  const availableAlgorithms = algorithms.filter((item) => item.available);
  const algorithmOptions: CalibrationAlgorithm[] = availableAlgorithms.length
    ? availableAlgorithms
    : [{ name: "random_forest", label: "Random Forest", kind: "builtin", available: true }];
  const visibleModels = models.filter((item) => item.model_type === modelType);
  const canTrain = snapshotCount > 0;

  return (
    <section className="panel">
      <header><b>Глобальное и площадочное обучение</b><span>21</span></header>
      <div className="panel-body">
        <small>
          Два уровня: глобальный prior команды и адаптация площадки. Снимки одной команды не попадают в другую.
          ML не утверждает паспорт.
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
          Снимки: {datasetLabel || "не выбраны"} {siteId ? `· площадка ${siteId}` : ""} · {snapshotCount} шт.
        </small>
        <div className="plans-actions">
          <button type="button" className="calculate-button" onClick={onTrainGlobal} disabled={busy || !canTrain}>
            {busy ? "Обучаем…" : "Обучить глобальный prior"}
          </button>
          <button type="button" className="secondary-button" onClick={onTrainSite} disabled={busy || !canTrain || !siteId}>
            Адаптировать площадку
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
                  <b>{scopeLabel(item.scope)} · {item.class_name || item.model_type} v{item.model_version}</b>
                  <small>
                    {statusLabel(item.status)} · {item.site_id} · {item.sample_count} обр.
                    {item.prior_model_id ? ` · prior ${item.prior_model_id}` : ""}
                  </small>
                </button>
              </li>
            ))}
          </ul>
        )}
        {selected && (
          <div className="dataset-detail">
            <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
              <div><span>Уровень</span><strong>{scopeLabel(selected.scope)}</strong></div>
              <div><span>Статус</span><strong>{statusLabel(selected.status)}</strong></div>
              <div><span>Площадка</span><strong>{selected.site_id || "—"}</strong></div>
            </div>
            <small>team_id {selected.team_id || "—"} · изоляция площадки {selected.site_id || "—"}</small>
            <small>Схема признаков: {selected.feature_schema_version || "—"}</small>
            <small>Обучение: {selected.training_date ? new Date(selected.training_date).toLocaleString("ru-RU") : "—"}</small>
            {"adaptation" in selected && selected.adaptation ? (
              <small>Адаптация: {selected.adaptation}{selected.prior_model_id ? ` от ${selected.prior_model_id}` : ""}</small>
            ) : null}
            {selected.metrics?.mae != null && (
              <small>MAE {ruNumber(Number(selected.metrics.mae), 2)} · {selected.primary_target || "цель"}</small>
            )}
            <div className="plans-actions">
              <button type="button" className="secondary-button" onClick={onMarkProduction} disabled={busy || selected.status === "production"}>
                Пометить как производственную
              </button>
              <button type="button" className="calculate-button" onClick={onPredict} disabled={busy}>
                {busy ? "Считаем…" : "Прогноз overlay"}
              </button>
            </div>
          </div>
        )}
        {overlay && overlay.prediction_applied && (
          <div className="outcome-overlay">
            <small>Слой рекомендации · проект не изменён · ML не утверждает</small>
            <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
              {Object.values(overlay.predictions).map((item) => (
                <div key={item.target_name}>
                  <span>{item.label || item.target_name}</span>
                  <strong>{formatValue(item.value, targetDigits(item.target_name))}</strong>
                  <small>{item.unit}</small>
                  {item.global_value != null && (
                    <small>prior {formatValue(item.global_value, targetDigits(item.target_name))}</small>
                  )}
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
            <ExplanationBlock
              explanation={overlay.explanation || overlay.predictions[overlay.primary_target]?.explanation}
              fallbackTitle={overlay.predictions[overlay.primary_target]?.label || overlay.primary_target || "исхода"}
            />
            <small>
              {scopeLabel(overlay.scope)} · {overlay.class_name || overlay.model_type} v{overlay.model_version} · {statusLabel(overlay.status)}
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
