import { useState } from "react";
import { RowMenu } from "./estimate/RowMenu";
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
  onRename,
  onRemove,
  canRemove,
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
  /** Переименовать активный черновик — из меню «⋮», как и удаление. */
  onRename: (name: string) => void;
  onRemove: () => void;
  /** Последний черновик удалить нельзя: вкладке нужен хотя бы один. */
  canRemove: boolean;
  /** Ссылка на выгрузку XLSX активного сценария; null — черновик ещё не сохранён. */
  exportUrl: string | null;
  busy: boolean;
  /** Сообщение о последнем сохранении (или переносе услуги); пусто — не показывать. */
  status: string;
  /** Ошибка последнего пересчёта; пусто — баннер не рисуется. */
  error: string;
}) {
  // Одно поле имени на два действия: сохранить сценарий под именем и
  // переименовать черновик. Отдельный `window.prompt` был третьим способом
  // ввести то же самое — при том, что `VariantTabs` умеет это своим полем.
  const [naming, setNaming] = useState<"save" | "rename" | null>(null);
  const [name, setName] = useState("");

  function startSave() {
    setName("");
    setNaming("save");
  }

  function commitName() {
    const trimmed = name.trim();
    if (trimmed) {
      if (naming === "rename") onRename(trimmed);
      else onSave(trimmed);
    }
    setNaming(null);
  }

  function handleSelect(id: string) {
    if (drafts.some((draft) => draft.id === id)) onSelectDraft(id);
    else onOpenRun(id);
  }

  const activeDraft = drafts.find((draft) => draft.id === activeId);

  function startRename() {
    if (!activeDraft) return;
    setName(activeDraft.name);
    setNaming("rename");
  }

  return (
    <header className="economics-header">
      <div className="economics-header-lead">
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
      </div>
      {error && (
        <p role="alert" className="economics-header-error">
          {error}
        </p>
      )}
      <div className="economics-header-actions">
        <span className="economics-header-scenario-label">Сценарий</span>
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
            onClick={() => (naming === "save" ? commitName() : startSave())}
          >
            Сохранить
          </button>
          {naming && (
            <input
              autoFocus
              aria-label={naming === "rename" ? "Новое имя сценария" : "Имя сценария"}
              value={name}
              onChange={(event) => setName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") commitName();
                if (event.key === "Escape") setNaming(null);
              }}
            />
          )}
          {naming === "rename" && (
            <button type="button" className="secondary-button" onClick={commitName}>
              Переименовать
            </button>
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

        {/* Действия над самим черновиком — за «⋮»: они редкие и разрушительные,
            в отличие от сохранения и выгрузки рядом. */}
        <RowMenu
          label="Действия со сценарием"
          items={[
            { label: "Переименовать сценарий", onSelect: startRename },
            ...(canRemove ? [{ label: "Удалить черновик", onSelect: onRemove, danger: true }] : []),
          ]}
        />
      </div>
    </header>
  );
}
