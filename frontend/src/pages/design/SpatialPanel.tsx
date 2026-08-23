import { ruNumber } from "../../lib/format";
import type { SpatialModel, SpatialOverlay, SpatialSummary } from "../../types/design";
import { RoleBadge } from "./RoleBadge";

function formatValue(value: number | null | undefined, digits: number): string {
  if (value == null || Number.isNaN(value)) return "—";
  return ruNumber(value, digits);
}

export function SpatialPanel({
  siteId,
  datasetId,
  datasetLabel,
  models,
  selected,
  overlay,
  busy,
  onRefresh,
  onTrain,
  onOpen,
  onMarkProduction,
  onPredict,
}: {
  siteId: string;
  datasetId: string;
  datasetLabel: string;
  models: SpatialSummary[];
  selected: SpatialModel | SpatialSummary | null;
  overlay: SpatialOverlay | null;
  busy: boolean;
  onRefresh: () => void;
  onTrain: () => void;
  onOpen: (modelId: string) => void;
  onMarkProduction: () => void;
  onPredict: () => void;
}) {
  const holes = overlay?.holes.slice(0, 8) ?? [];

  return (
    <section className="panel">
      <header><b>Скважинный ML</b><RoleBadge role="predicted" /></header>
      <div className="panel-body">
        <small>
          Прогноз X50 / негабарита / забоя и остатков по скважине или окрестности.
          Только слой predicted: заряды и утверждённая сетка не перезаписываются.
        </small>
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
                  <b>{item.class_name || "SpatialHoleModel"} v{item.model_version}</b>
                  <small>
                    {item.status} · {item.hole_count} скв. · снимок v{item.training_dataset_version}
                  </small>
                </button>
              </li>
            ))}
          </ul>
        )}
        {selected && (
          <div className="dataset-detail">
            <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
              <div><span>Статус</span><strong>{selected.status}</strong></div>
              <div><span>Скважин</span><strong>{selected.hole_count}</strong></div>
              <div><span>Датасет</span><strong>v{selected.training_dataset_version}</strong></div>
            </div>
            <small>Схема: {selected.feature_schema_version || "spatial-1.0.0"} · роли designed / executed / predicted / measured</small>
            <div className="plans-actions">
              <button type="button" className="secondary-button" onClick={onMarkProduction} disabled={busy || selected.status === "production"}>
                Пометить как производственную
              </button>
              <button type="button" className="calculate-button" onClick={onPredict} disabled={busy}>
                {busy ? "Считаем…" : "Карта по скважинам"}
              </button>
            </div>
          </div>
        )}
        {!selected && (
          <div className="plans-actions">
            <button type="button" className="calculate-button" onClick={onPredict} disabled={busy}>
              {busy ? "Считаем…" : "Карта без модели (физика)"}
            </button>
          </div>
        )}
        {overlay && overlay.prediction_applied && (
          <div className="dataset-detail">
            <small>Слой predicted · проект не изменён · {overlay.hole_count} скважин</small>
            <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
              <div><span>X50 блока</span><strong>{formatValue(overlay.block.x50_mm, 1)}</strong><small>мм</small></div>
              <div><span>Негабарит блока</span><strong>{formatValue(overlay.block.oversize_pct, 1)}</strong><small>%</small></div>
              <div><span>Забой блока</span><strong>{formatValue(overlay.block.toe_probability, 2)}</strong></div>
            </div>
            {holes.map((item) => (
              <small key={item.hole_id}>
                {item.hole_id}: X50 {formatValue(item.x50_mm, 1)} мм
                {" · "}негабарит {formatValue(item.oversize_pct, 1)}%
                {" · "}забой {formatValue(item.toe_probability, 2)}
                {" · "}ост. X50 {formatValue(item.residual_x50_mm, 1)} мм
              </small>
            ))}
            {overlay.warnings[0] && <small className="frag-warnings">{overlay.warnings[0]}</small>}
          </div>
        )}
      </div>
    </section>
  );
}
