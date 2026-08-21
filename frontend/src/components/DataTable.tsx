export type DataColumn<T> = {
  key: keyof T;
  label: string;
  align?: "left" | "right";
  format?: (row: T) => string;
};

export function DataTable<T extends object>({ columns, rows, emptyText }: {
  columns: DataColumn<T>[];
  rows: T[];
  emptyText?: string;
}) {
  if (!rows.length) return <p className="table-empty">{emptyText ?? "Нет данных."}</p>;
  return (
    <div className="table-scroll">
      <table>
        <thead><tr>{columns.map((c) => <th key={String(c.key)} className={c.align === "right" ? "num" : ""}>{c.label}</th>)}</tr></thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={String(c.key)} className={c.align === "right" ? "num" : ""}>
                  {c.format ? c.format(row) : String(row[c.key] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
