import { useState } from "react";
import { scenarioLabel, type Draft } from "./scenario";
import type { EconomicsRunSummary } from "../../types/blockEconomics";

/**
 * Шапка вкладки «Экономика блока»: заголовок, контекст паспорта, выбор
 * сценария (открытые черновики + сохранённые прогоны паспорта) и три
 * действия — сохранить текущий черновик под именем, дублировать его в
 * новый черновик, выгрузить сохранённый сценарий в XLSX.
 *
 * Шапка не знает, «грязный» ли черновик, — это решает `isDirty` в
 * `scenario.ts` по данным страницы; сюда приходит уже готовый признак.
 */
export function EconomicsHeader({
  context,
  drafts,
  runs,
  activeId,
  onSelectDraft,
  onOpenRun,
  dirty,
  onSave,
  onDuplicate,
  exportUrl,
  busy,
  status,
  error,
}: {
  context: { site: string; passport: string; revision: string };
  drafts: Draft[];
  runs: EconomicsRunSummary[];
  activeId: string;
  onSelectDraft: (id: string) => void;
  onOpenRun: (runId: string) => void;
  dirty: boolean;
  onSave: (name: string) => void;
  onDuplicate: () => void;
  /** Ссылка на выгрузку XLSX активного сценария; null — черновик ещё не сохранён. */
  exportUrl: string | null;
  busy: boolean;
  /** Сообщение о последнем сохранении (или переносе услуги); пусто — не показывать. */
  status: string;
  /** Ошибка последнего пересчёта; пусто — баннер не рисуется. */
  error: string;
}) {
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");

  function startSave() {
    setName("");
    setNaming(true);
  }

  function commitSave() {
    const trimmed = name.trim();
    if (trimmed) onSave(trimmed);
    setNaming(false);
  }

  function handleSelect(id: string) {
    if (drafts.some((draft) => draft.id === id)) onSelectDraft(id);
    else onOpenRun(id);
  }

  return (
    <header className="economics-header">
      <div className="economics-header-title">
        <h1>Экономика блока</h1>
        {dirty ? (
          <span className="save-status dirty" aria-live="polite">
            Черновик · не сохранено
          </span>
        ) : (
          status && (
            <span className="save-status" aria-live="polite">
              {status}
            </span>
          )
        )}
      </div>
      <p className="economics-header-context">
        {context.site} · {context.passport} · {context.revision}
      </p>
      {error && (
        <p role="alert" className="economics-header-error">
          {error}
        </p>
      )}
      <div className="economics-header-actions">
        <select
          aria-label="Сценарий"
          value={activeId}
          disabled={busy}
          onChange={(event) => handleSelect(event.target.value)}
        >
          <optgroup label="Черновики">
            {drafts.map((draft) => (
              <option key={draft.id} value={draft.id}>
                {scenarioLabel(draft, runs)}
              </option>
            ))}
          </optgroup>
          <optgroup label="Сохранённые сценарии">
            {runs.map((run) => (
              <option key={run.id} value={run.id}>
                {run.name}
              </option>
            ))}
          </optgroup>
        </select>

        <div className="economics-header-save">
          <button
            type="button"
            className="primary-button"
            disabled={busy}
            onClick={() => (naming ? commitSave() : startSave())}
          >
            Сохранить
          </button>
          {naming && (
            <input
              autoFocus
              aria-label="Имя сценария"
              value={name}
              onChange={(event) => setName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") commitSave();
                if (event.key === "Escape") setNaming(false);
              }}
            />
          )}
        </div>

        <button type="button" className="secondary-button" disabled={busy} onClick={onDuplicate}>
          Дублировать
        </button>

        {exportUrl ? (
          <a className="secondary-button" href={exportUrl} download>
            XLSX
          </a>
        ) : (
          <button
            type="button"
            className="secondary-button"
            disabled
            title="Сначала сохраните сценарий"
          >
            XLSX
          </button>
        )}
      </div>
    </header>
  );
}
