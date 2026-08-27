import { canDeletePlan, statusLabel } from "../../lib/lifecycle";
import type { DesignSummary } from "../../types/design";

export function PlansPanel({
  plans,
  currentDesignId,
  currentName,
  currentStatus,
  onNameChange,
  onSave,
  onOpen,
  onDelete,
  onNew,
  onExportCsv,
  onPrintPassport,
  busy,
  nameLocked,
  saveLocked,
}: {
  plans: DesignSummary[];
  currentDesignId: string;
  currentName: string;
  currentStatus: string;
  onNameChange: (name: string) => void;
  onSave: () => void;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onNew: () => void;
  onExportCsv: () => void;
  onPrintPassport: () => void;
  busy: boolean;
  nameLocked: boolean;
  saveLocked: boolean;
}) {
  return (
    <section className="panel plans-panel">
      <header>
        <b>Паспорт БВР</b>
        <span className={`lifecycle-pill status-${currentStatus}`}>{statusLabel(currentStatus)}</span>
      </header>
      <div className="panel-body">
        <label>Название паспорта
          <input value={currentName} onChange={(e) => onNameChange(e.target.value)} disabled={nameLocked} />
        </label>
        <div className="plans-actions">
          <button className="calculate-button" onClick={onSave} disabled={busy || saveLocked}>
            {currentDesignId ? "Сохранить" : "Сохранить как новый"}
          </button>
          <button className="secondary-button" onClick={onNew} disabled={busy}>Новый паспорт</button>
          <button className="secondary-button" onClick={onExportCsv} disabled={busy || !currentDesignId}>Экспорт CSV</button>
          <button className="secondary-button" onClick={onPrintPassport} disabled={busy}>Печать паспорта</button>
        </div>
        {plans.length > 0 && (
          <ul className="plans-list">
            {plans.map((p) => (
              <li key={p.design_id} className={p.design_id === currentDesignId ? "active" : ""}>
                <button className="plans-list-open" onClick={() => onOpen(p.design_id)}>
                  <b>{p.name}</b>
                  <small>
                    {statusLabel(p.lifecycle_status)} · {p.hole_count} скв. · {new Date(p.updated_at).toLocaleString("ru-RU")}
                  </small>
                </button>
                <button
                  className="plans-list-delete"
                  onClick={() => onDelete(p.design_id)}
                  disabled={!canDeletePlan(p.lifecycle_status)}
                  aria-label={`Удалить «${p.name}»`}
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
