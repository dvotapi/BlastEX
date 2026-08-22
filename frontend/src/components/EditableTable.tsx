import { useId } from "react";

export type EditableColumn<T> = {
  key: keyof T;
  label: string;
  type: "text" | "number" | "checkbox" | "select";
  options?: { value: string; label: string }[];
  step?: number;
  min?: number;
  disabled?: boolean;
  width?: string;
};

/** Аналог st.data_editor: редактируемая таблица с добавлением/удалением строк. */
export function EditableTable<T extends Record<string, unknown>>({
  columns,
  rows,
  onChange,
  newRow,
  readOnly,
  rowKey,
}: {
  columns: EditableColumn<T>[];
  rows: T[];
  onChange: (rows: T[]) => void;
  newRow?: () => T;
  readOnly?: boolean;
  rowKey?: (row: T, index: number) => string | number;
}) {
  const idPrefix = useId();

  function updateCell(index: number, key: keyof T, value: unknown) {
    const next = rows.slice();
    next[index] = { ...next[index], [key]: value };
    onChange(next);
  }

  function removeRow(index: number) {
    onChange(rows.filter((_, i) => i !== index));
  }

  if (readOnly) {
    return (
      <div className="table-scroll">
        <table>
          <thead><tr>{columns.map((c) => <th key={String(c.key)}>{c.label}</th>)}</tr></thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={rowKey ? rowKey(row, i) : i}>
                {columns.map((c) => (
                  <td key={String(c.key)}>
                    {c.type === "checkbox" ? (row[c.key] ? "да" : "нет") : String(row[c.key] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="table-scroll editable-table">
      <table>
        <thead><tr>{columns.map((c) => <th key={String(c.key)}>{c.label}</th>)}<th /></tr></thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={rowKey ? rowKey(row, i) : i}>
              {columns.map((c) => (
                <td key={String(c.key)} style={c.width ? { width: c.width } : undefined}>
                  {c.type === "select" ? (
                    <select
                      value={String(row[c.key] ?? "")}
                      disabled={c.disabled}
                      onChange={(e) => updateCell(i, c.key, e.target.value)}
                    >
                      {(c.options ?? []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  ) : c.type === "checkbox" ? (
                    <input
                      type="checkbox"
                      checked={Boolean(row[c.key])}
                      disabled={c.disabled}
                      onChange={(e) => updateCell(i, c.key, e.target.checked)}
                    />
                  ) : c.type === "number" ? (
                    <input
                      type="number"
                      id={`${idPrefix}-${String(c.key)}-${i}`}
                      value={row[c.key] === null || row[c.key] === undefined ? "" : Number(row[c.key])}
                      step={c.step ?? "any"}
                      min={c.min}
                      disabled={c.disabled}
                      onChange={(e) => updateCell(i, c.key, e.target.value === "" ? null : Number(e.target.value))}
                    />
                  ) : (
                    <input
                      type="text"
                      value={String(row[c.key] ?? "")}
                      disabled={c.disabled}
                      onChange={(e) => updateCell(i, c.key, e.target.value)}
                    />
                  )}
                </td>
              ))}
              <td><button type="button" className="row-remove" onClick={() => removeRow(i)} aria-label="Удалить строку">✕</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      {newRow && (
        <button type="button" className="row-add" onClick={() => onChange([...rows, newRow()])}>
          + Добавить строку
        </button>
      )}
    </div>
  );
}
