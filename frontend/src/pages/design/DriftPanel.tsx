import { ruNumber } from "../../lib/format";
import {
  DRIFT_KIND_LABELS,
  DRIFT_ROLE_LABELS,
  DRIFT_SEVERITY_LABELS,
  REGISTRY_FAMILY_LABELS,
  type DatasetSummary,
  type DriftAlert,
  type DriftKind,
  type DriftReport,
  type DriftSeverity,
  type RegistryFamily,
  type RegistryRecord,
} from "../../types/design";
import { RoleBadge } from "./RoleBadge";

function severityLabel(value: string): string {
  return DRIFT_SEVERITY_LABELS[value as DriftSeverity] ?? value;
}

function kindLabel(value: string): string {
  return DRIFT_KIND_LABELS[value as DriftKind] ?? value;
}

function roleLabel(value: string): string {
  return DRIFT_ROLE_LABELS[value] ?? value;
}

function familyLabel(value: string): string {
  return REGISTRY_FAMILY_LABELS[value as RegistryFamily] ?? value;
}

function formatMean(value: number | null | undefined, unit: string): string {
  if (value == null || Number.isNaN(value)) return "—";
  const digits = unit === "mm" || unit === "kg" ? 1 : 3;
  return `${ruNumber(value, digits)}${unit ? ` ${unit}` : ""}`;
}

export function DriftPanel({
  models,
  selectedModelId,
  onModelChange,
  snapshots,
  currentDatasetId,
  onCurrentDatasetChange,
  report,
  alerts,
  busy,
  actor,
  onCheck,
  onAcknowledge,
}: {
  models: RegistryRecord[];
  selectedModelId: string;
  onModelChange: (family: string, modelId: string) => void;
  snapshots: DatasetSummary[];
  currentDatasetId: string;
  onCurrentDatasetChange: (datasetId: string) => void;
  report: DriftReport | null;
  alerts: DriftAlert[];
  busy: boolean;
  actor: string;
  onCheck: () => void;
  onAcknowledge: (alertId: string) => void;
}) {
  const production = models.filter((item) => item.status === "production");
  const selected = production.find((item) => `${item.family}:${item.model_id}` === selectedModelId) || null;
  const openAlerts = alerts.filter((item) => !item.acknowledged);

  return (
    <section className="panel">
      <header><b>Мониторинг дрифта</b><RoleBadge role="predicted" /></header>
      <div className="panel-body">
        <small>
          Сравнение текущего снимка со снимком обучения производственной модели.
          Только сигналы: автодеплоя и автопереобучения нет. Продвижение — вручную в реестре.
        </small>
        <label>Производственная модель
          <select
            value={selectedModelId}
            onChange={(e) => {
              const [family, ...rest] = e.target.value.split(":");
              onModelChange(family, rest.join(":"));
            }}
          >
            <option value="">Выберите production-модель</option>
            {production.map((item) => (
              <option key={`${item.family}:${item.model_id}`} value={`${item.family}:${item.model_id}`}>
                {familyLabel(item.family)} · {item.class_name || item.model_type} v{item.model_version}
              </option>
            ))}
          </select>
        </label>
        <label>Текущий снимок наблюдений
          <select
            value={currentDatasetId}
            onChange={(e) => onCurrentDatasetChange(e.target.value)}
          >
            <option value="">Выберите снимок</option>
            {snapshots.map((item) => (
              <option key={item.dataset_id} value={item.dataset_id}>
                {item.name || item.dataset_id} · v{item.dataset_version}
              </option>
            ))}
          </select>
        </label>
        {selected && (
          <small>
            Снимок обучения: {selected.lineage.training_dataset_id || "—"}
            {selected.lineage.training_dataset_version ? ` v${selected.lineage.training_dataset_version}` : ""}
            {" · "}схема {selected.lineage.feature_schema_version || "—"}
          </small>
        )}
        <small>Оператор: {actor || "текущий пользователь"}</small>
        <div className="plans-actions">
          <button
            type="button"
            className="calculate-button"
            onClick={onCheck}
            disabled={busy || !selectedModelId || !currentDatasetId}
          >
            Проверить дрифт
          </button>
        </div>
        {report && (
          <div className="dataset-detail">
            <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
              <div><span>Серьёзность</span><strong>{severityLabel(report.overall_severity)}</strong></div>
              <div><span>Сигналов</span><strong>{report.alerts.length}</strong></div>
              <div><span>Live-модель</span><strong>{report.live_model_unchanged ? "без изменений" : "изменена"}</strong></div>
            </div>
            <small>
              Каналы: признаки / факт / прогноз · роли {Object.values(report.data_roles).join(", ") || "designed, executed, predicted, measured"}
            </small>
            <small>
              Автодеплой: нет · автопереобучение: нет · дальше: реестр моделей
            </small>
            {report.warnings.map((item) => (
              <small key={item}>{item}</small>
            ))}
            {report.metrics.filter((item) => item.severity !== "ok").map((item) => (
              <small key={`${item.kind}:${item.name}`}>
                {kindLabel(item.kind)} · {item.name} ({roleLabel(item.role)})
                {item.unit ? `, ${item.unit}` : ""}: {severityLabel(item.severity)}
                {" · "}база {formatMean(item.baseline_mean, item.unit)} → сейчас {formatMean(item.current_mean, item.unit)}
              </small>
            ))}
          </div>
        )}
        {openAlerts.length > 0 && (
          <ul className="plans-list">
            {openAlerts.map((item) => (
              <li key={item.alert_id}>
                <button type="button" className="plans-list-open" onClick={() => onAcknowledge(item.alert_id)}>
                  <b>{severityLabel(item.severity)} · {kindLabel(item.kind)}</b>
                  <small>{item.message}</small>
                </button>
              </li>
            ))}
          </ul>
        )}
        {openAlerts.length > 0 && (
          <small>Нажмите сигнал, чтобы подтвердить получение. Это не продвигает модель.</small>
        )}
      </div>
    </section>
  );
}
