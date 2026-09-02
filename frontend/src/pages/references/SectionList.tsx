import { useMemo, useState } from "react";
import type { ReferenceSectionSchema } from "../../types/referenceSchema";
import { enumLabel } from "./enumLabels";
import { fieldIndex, formatFieldValue, sectionFields } from "./schemaFields";
import type { DraftItem } from "./RecordForm";

/**
 * Список записей раздела. Колонки задаёт схема (`list_columns`), поэтому новый
 * раздел получает осмысленный список без правки фронта.
 */
export function SectionList({
  section,
  rows,
  selected,
  changed,
  errorCodes,
  canEdit,
  refName,
  onSelect,
  onAdd,
}: {
  section: ReferenceSectionSchema;
  rows: DraftItem[];
  selected: string;
  changed: Set<string>;
  errorCodes: Set<string>;
  canEdit: boolean;
  refName: (refSection: string, code: string) => string;
  onSelect: (rowId: string) => void;
  onAdd: () => void;
}) {
  const fields = useMemo(() => fieldIndex(section.json_schema), [section]);
  const segmentField = useMemo(
    () => sectionFields(section.json_schema).find((field) => field.kind === "enum" && field.options.length <= 4),
    [section],
  );
  const [segment, setSegment] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);

  const columns = section.list_columns.length ? section.list_columns : ["name"];
  const visible = rows.filter((row) => {
    if (activeOnly && !row.is_active) return false;
    if (segment && segmentField && String(row.payload[segmentField.name] ?? "") !== segment) return false;
    return true;
  });

  function cell(row: DraftItem, column: string) {
    if (column === "name") return null;
    const field = fields.get(column);
    const value = row.payload[column];
    if (field?.kind === "ref" && typeof value === "string" && value) {
      return (
        <>
          <b>{refName(field.ref, value)}</b>
          <small>{value}</small>
        </>
      );
    }
    if (field?.kind === "enum" && typeof value === "string" && value) {
      return <span className="ref-tag">{enumLabel(value)}</span>;
    }
    return <span>{formatFieldValue(value, field)}</span>;
  }

  return (
    <section className="ref-list-panel">
      <header className="ref-list-head">
        <div>
          <h3>{section.label}</h3>
          {section.deprecated && <p className="ref-list-note">Раздел устарел и оставлен ради старых ревизий.</p>}
        </div>
        <div className="ref-list-head-actions">
          <button type="button" className="ref-ghost-button" disabled title="Импорт из Excel появится позже">
            Импорт из Excel — скоро
          </button>
          {canEdit && (
            <button type="button" className="primary-button" onClick={onAdd}>
              + Добавить запись
            </button>
          )}
        </div>
      </header>

      <div className="ref-list-filters">
        {segmentField && (
          <div className="ref-segments">
            <button type="button" className={segment === "" ? "active" : ""} onClick={() => setSegment("")}>
              Все · {rows.length}
            </button>
            {segmentField.options.map((option) => {
              const count = rows.filter((row) => String(row.payload[segmentField.name] ?? "") === option).length;
              return (
                <button
                  key={option}
                  type="button"
                  className={segment === option ? "active" : ""}
                  onClick={() => setSegment(option)}
                >
                  {enumLabel(option)} · {count}
                </button>
              );
            })}
          </div>
        )}
        <label className="ref-checkbox">
          <input type="checkbox" checked={activeOnly} onChange={(event) => setActiveOnly(event.target.checked)} />
          <span>Только активные</span>
        </label>
      </div>

      <div className="ref-table-scroll">
        <table className="ref-table">
          <thead>
            <tr>
              <th>Наименование</th>
              {columns
                .filter((column) => column !== "name")
                .map((column) => (
                  <th key={column}>{fields.get(column)?.title ?? column}</th>
                ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => (
              <tr
                key={row.row_id}
                className={[
                  row.row_id === selected ? "selected" : "",
                  changed.has(row.row_id) ? "changed" : "",
                  row.is_active ? "" : "inactive-row",
                  errorCodes.has(row.code) ? "has-error" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                onClick={() => onSelect(row.row_id)}
              >
                <td>
                  <b>{row.name || "Без наименования"}</b>
                  <small>{row.code}</small>
                </td>
                {columns
                  .filter((column) => column !== "name")
                  .map((column) => (
                    <td key={column}>{cell(row, column)}</td>
                  ))}
              </tr>
            ))}
            {visible.length === 0 && (
              <tr className="ref-table-empty">
                <td colSpan={columns.length}>Записей нет.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
