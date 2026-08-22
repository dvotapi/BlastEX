import type { DesignSummary } from "../../types/design";

export function PlansPanel({
  plans,
  currentDesignId,
  currentName,
  onNameChange,
  onSave,
  onOpen,
  onDelete,
  onNew,
  onExportCsv,
  onPrintPassport,
  busy,
}: {
  plans: DesignSummary[];
  currentDesignId: string;
  currentName: string;
  onNameChange: (name: string) => void;
  onSave: () => void;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onNew: () => void;
  onExportCsv: () => void;
  onPrintPassport: () => void;
  busy: boolean;
}) {
  return (
    <section className="panel plans-panel">
      <header><b>Паспорт БВР</b><span>{plans.length ? `${plans.length} сохранено` : "Нет сохранённых"}</span></header>
      <div className="panel-body">
        <label>Название паспорта<input value={currentName} onChange={(e) => onNameChange(e.target.value)} /></label>
        <div className="plans-actions">
          <button className="calculate-button" onClick={onSave} disabled={busy}>{currentDesignId ? "Сохранить" : "Сохранить как новый"}</button>
          <button className="secondary-button" onClick={onNew} disabled={busy}>Новый паспорт</button>
          <button className="secondary-button" onClick={onExportCsv} disabled={busy || !currentDesignId}>Экспорт CSV</button>
          <button className="secondary-button" onClick={onPrintPassport} disabled={busy || !currentDesignId}>Печать паспорта</button>
        </div>
        {plans.length > 0 && (
          <ul className="plans-list">
            {plans.map((p) => (
              <li key={p.design_id} className={p.design_id === currentDesignId ? "active" : ""}>
                <button className="plans-list-open" onClick={() => onOpen(p.design_id)}>
                  <b>{p.name}</b>
                  <small>{p.hole_count} скв. · {new Date(p.updated_at).toLocaleString("ru-RU")}</small>
                </button>
                <button className="plans-list-delete" onClick={() => onDelete(p.design_id)} aria-label={`Удалить «${p.name}»`}>✕</button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
