import {
  REGISTRY_FAMILIES,
  REGISTRY_FAMILY_LABELS,
  REGISTRY_STATUS_LABELS,
  type RegistryFamily,
  type RegistryRecord,
  type RegistryStatus,
} from "../../types/design";

function statusLabel(status: string): string {
  return REGISTRY_STATUS_LABELS[status as RegistryStatus] ?? status;
}

function familyLabel(family: string): string {
  return REGISTRY_FAMILY_LABELS[family as RegistryFamily] ?? family;
}

function shortChecksum(value: string): string {
  if (!value) return "—";
  return value.length > 12 ? `${value.slice(0, 12)}…` : value;
}

function transitionLabel(status: string): string {
  const labels: Record<string, string> = {
    staging: "В стейджинг",
    production: "В производство",
    retired: "Снять",
    archived: "В архив",
  };
  return labels[status] || statusLabel(status);
}

export function RegistryPanel({
  family,
  onFamilyChange,
  models,
  selected,
  busy,
  actor,
  onRefresh,
  onOpen,
  onPromote,
}: {
  family: RegistryFamily | "";
  onFamilyChange: (value: RegistryFamily | "") => void;
  models: RegistryRecord[];
  selected: RegistryRecord | null;
  busy: boolean;
  actor: string;
  onRefresh: () => void;
  onOpen: (family: string, modelId: string) => void;
  onPromote: (toStatus: string) => void;
}) {
  const visible = family ? models.filter((item) => item.family === family) : models;

  return (
    <section className="panel">
      <header><b>Реестр моделей</b><span>22</span></header>
      <div className="panel-body">
        <small>
          Версии, контрольная сумма и происхождение снимка. Продвижение только вручную:
          candidate → staging/production → retired/archived. Автодеплоя нет.
        </small>
        <label>Семейство
          <select
            value={family}
            onChange={(e) => onFamilyChange(e.target.value as RegistryFamily | "")}
          >
            <option value="">Все семейства</option>
            {REGISTRY_FAMILIES.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
        </label>
        <small>Оператор продвижения: {actor || "текущий пользователь"}</small>
        <div className="plans-actions">
          <button type="button" className="secondary-button" onClick={onRefresh} disabled={busy}>
            Обновить реестр
          </button>
        </div>
        {visible.length > 0 && (
          <ul className="plans-list">
            {visible.map((item) => (
              <li key={`${item.family}:${item.model_id}`} className={item.model_id === selected?.model_id && item.family === selected?.family ? "active" : ""}>
                <button type="button" className="plans-list-open" onClick={() => onOpen(item.family, item.model_id)}>
                  <b>{familyLabel(item.family)} · {item.class_name || item.model_type} v{item.model_version}</b>
                  <small>
                    {statusLabel(item.status)} · {item.site_id || "—"} · {item.sample_count} обр.
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
              <div><span>Версия</span><strong>v{selected.model_version}</strong></div>
              <div><span>Семейство</span><strong>{familyLabel(selected.family)}</strong></div>
            </div>
            <small>team_id {selected.team_id || "—"} · площадка {selected.site_id || "—"}</small>
            <small title={selected.checksum}>Контрольная сумма: {shortChecksum(selected.checksum)}</small>
            <small>
              Снимок: {selected.lineage.training_dataset_id || "—"}
              {selected.lineage.training_dataset_version ? ` v${selected.lineage.training_dataset_version}` : ""}
            </small>
            <small>Схема признаков: {selected.lineage.feature_schema_version || "—"}</small>
            <small>
              Продвинул: {selected.promoted_by || "ещё не продвигали"}
              {selected.promoted_at ? ` · ${new Date(selected.promoted_at).toLocaleString("ru-RU")}` : ""}
            </small>
            {selected.transitions.length > 0 && (
              <small>
                История: {selected.transitions.map((item) => `${item.from_status}→${item.to_status} (${item.actor})`).join(" · ")}
              </small>
            )}
            <div className="plans-actions">
              {selected.allowed_transitions.map((status) => (
                <button
                  key={status}
                  type="button"
                  className={status === "production" ? "calculate-button" : "secondary-button"}
                  onClick={() => onPromote(status)}
                  disabled={busy}
                >
                  {transitionLabel(status)}
                </button>
              ))}
            </div>
            {selected.allowed_transitions.length === 0 && (
              <small>Карточка в архиве. Дальнейшие переходы закрыты.</small>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
