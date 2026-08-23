import type { DatasetSnapshot, DatasetSummary, SampleValidation } from "../../types/design";

const FEATURE_GROUPS = ["SITE", "GEOLOGY", "GEOMETRY", "CHARGING", "TIMING", "EXECUTION", "ENVIRONMENT"];
const TARGET_GROUPS = ["FRAGMENTATION", "VIBRATION", "BLAST", "PERFORMANCE", "ECONOMICS"];

const FEATURE_LABELS: Record<string, string> = {
  SITE: "Площадка",
  GEOLOGY: "Геология",
  GEOMETRY: "Геометрия",
  CHARGING: "Заряжание",
  TIMING: "Тайминг",
  EXECUTION: "Исполнение",
  ENVIRONMENT: "Окружение",
};

const TARGET_LABELS: Record<string, string> = {
  FRAGMENTATION: "Кусковатость",
  VIBRATION: "Сейсмика",
  BLAST: "Взрыв",
  PERFORMANCE: "Эффективность",
  ECONOMICS: "Экономика",
};

export function DatasetPanel({
  siteId,
  onSiteIdChange,
  name,
  onNameChange,
  snapshots,
  selected,
  preview,
  busy,
  onRefresh,
  onBuild,
  onOpen,
}: {
  siteId: string;
  onSiteIdChange: (value: string) => void;
  name: string;
  onNameChange: (value: string) => void;
  snapshots: DatasetSummary[];
  selected: DatasetSnapshot | null;
  preview: SampleValidation | null;
  busy: boolean;
  onRefresh: () => void;
  onBuild: () => void;
  onOpen: (datasetId: string) => void;
}) {
  return (
    <section className="panel">
      <header><b>Датасет обучения</b><span>15</span></header>
      <div className="panel-body">
        <small>
          Снимок закрытых взрывов. Обучение идёт только с неизменяемой копии, не с живых паспортов.
        </small>
        <label>Площадка (site_id)
          <input value={siteId} onChange={(e) => onSiteIdChange(e.target.value)} placeholder="карьер-1" />
        </label>
        <label>Название снимка
          <input value={name} onChange={(e) => onNameChange(e.target.value)} placeholder="Снимок после взрыва" />
        </label>
        <div className="plans-actions">
          <button type="button" className="calculate-button" onClick={onBuild} disabled={busy || !siteId.trim()}>
            {busy ? "Собираем…" : "Собрать снимок"}
          </button>
          <button type="button" className="secondary-button" onClick={onRefresh} disabled={busy}>
            Обновить список
          </button>
        </div>
        {preview && (
          <div className="dataset-preview">
            <small>
              Текущий паспорт: {preview.ok ? "можно включить в снимок" : "ещё не закрыт"}
              {preview.complete_target_groups.length > 0
                ? ` · цели: ${preview.complete_target_groups.map((key) => TARGET_LABELS[key] ?? key).join(", ")}`
                : ""}
            </small>
            {!preview.ok && preview.reasons.length > 0 && (
              <small className="frag-warnings">{preview.reasons.slice(0, 3).join(" ")}</small>
            )}
          </div>
        )}
        {snapshots.length > 0 && (
          <ul className="plans-list">
            {snapshots.map((item) => (
              <li key={item.dataset_id} className={item.dataset_id === selected?.dataset_id ? "active" : ""}>
                <button type="button" className="plans-list-open" onClick={() => onOpen(item.dataset_id)}>
                  <b>{item.name || `Снимок v${item.dataset_version}`}</b>
                  <small>
                    v{item.dataset_version} · {item.sample_count} обр. · {item.site_id}
                  </small>
                </button>
              </li>
            ))}
          </ul>
        )}
        {selected && (
          <div className="dataset-detail">
            <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
              <div><span>Версия схемы</span><strong>{selected.feature_schema_version}</strong></div>
              <div><span>Версия датасета</span><strong>{selected.dataset_version}</strong></div>
              <div><span>Образцы</span><strong>{selected.sample_count}</strong></div>
            </div>
            <small>Площадка: {selected.site_id}</small>
            <small>Создан: {selected.created_at ? new Date(selected.created_at).toLocaleString("ru-RU") : "—"}</small>
            <small>Источники: {selected.source_blast_ids.join(", ") || "нет"}</small>
            <div className="dataset-tags">
              {FEATURE_GROUPS.map((key) => <i key={key}>{FEATURE_LABELS[key]}</i>)}
            </div>
            <div className="dataset-tags">
              {TARGET_GROUPS.map((key) => <i key={key}>{TARGET_LABELS[key]}</i>)}
            </div>
            {selected.rejected_count > 0 && (
              <small className="frag-warnings">Отклонено паспортов: {selected.rejected_count}</small>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
