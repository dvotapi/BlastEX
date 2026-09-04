import { useState } from "react";
import type { PublicDelta, PublicDeltaEntry } from "../../types/economics";
import { deltaSummary } from "./publicDelta";

const KIND_LABELS: Record<PublicDeltaEntry["kind"], string> = {
  new: "новая",
  changed: "изменена",
  deactivated: "деактивирована",
};

function entryKey(entry: PublicDeltaEntry): string {
  return `${entry.section}::${entry.public_table}#${entry.public_id}`;
}

/** Значение поля в тексте изменения: пустое и `null` читаются как прочерк. */
function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

/**
 * Плашка «Из project1»: сколько записей журнала расходится с черновиком, что
 * именно расходится и две операции — применить всё в черновик или связать
 * новую строку журнала с уже существующей записью справочника.
 *
 * Компонент ничего не знает о полях разделов: и подписи разделов, и списки
 * записей для связывания приходят от страницы.
 */
export function PublicDeltaBanner({
  delta,
  busy,
  canEdit,
  sectionLabel,
  recordsOf,
  onRefresh,
  onApplyAll,
  onLink,
}: {
  delta: PublicDelta | null;
  busy: boolean;
  canEdit: boolean;
  sectionLabel: (section: string) => string;
  recordsOf: (section: string) => Array<{ code: string; name: string }>;
  onRefresh: () => void;
  onApplyAll: () => void;
  onLink: (entry: PublicDeltaEntry, code: string) => void;
}) {
  const [choice, setChoice] = useState<Record<string, string>>({});

  if (!delta) return null;

  if (!delta.available) {
    return (
      <section className="ref-public-banner unavailable">
        <p className="page-caption">project1 недоступен: {delta.error}</p>
        <button type="button" className="ref-ghost-button" onClick={onRefresh} disabled={busy}>
          Повторить
        </button>
      </section>
    );
  }

  const total = delta.counts.new + delta.counts.changed + delta.counts.deactivated;
  // Совпадающий с журналом черновик — обычное состояние, плашке нечего сказать.
  if (total === 0) return null;

  return (
    <section className="ref-public-banner">
      <div className="ref-public-banner-head">
        <p className="page-caption">{deltaSummary(delta.counts)}</p>
        <button type="button" className="ref-ghost-button" onClick={onRefresh} disabled={busy}>
          Проверить project1
        </button>
        <button type="button" className="primary-button" onClick={onApplyAll} disabled={!canEdit || busy}>
          Применить в черновик
        </button>
      </div>

      <details className="ref-public-entries">
        <summary>Показать записи</summary>
        <ul>
          {delta.entries.map((entry) => {
            const key = entryKey(entry);
            const selected = choice[key] ?? "";
            return (
              <li key={key}>
                <p>
                  <b>{KIND_LABELS[entry.kind]}</b> · {sectionLabel(entry.section)} · {entry.name} ({entry.code})
                </p>
                {entry.kind === "changed" && entry.changes.length > 0 && (
                  <ul className="ref-public-changes">
                    {entry.changes.map((change) => (
                      <li key={change.key}>
                        {change.key}: {displayValue(change.old)} → {displayValue(change.new)}
                      </li>
                    ))}
                  </ul>
                )}
                {entry.kind === "new" && (
                  <div className="ref-public-link">
                    <select
                      value={selected}
                      disabled={!canEdit || busy}
                      onChange={(event) => setChoice((current) => ({ ...current, [key]: event.target.value }))}
                    >
                      <option value="">Связать с существующей записью…</option>
                      {recordsOf(entry.section).map((record) => (
                        <option key={record.code} value={record.code}>
                          {record.name} ({record.code})
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="ref-ghost-button"
                      onClick={() => onLink(entry, selected)}
                      disabled={!canEdit || busy || !selected}
                    >
                      Связать
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </details>
    </section>
  );
}
