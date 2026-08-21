export function MetricsTable({ title, rows }: { title?: string; rows: [string, string][] }) {
  return (
    <div className="metrics-table-wrap">
      {title && <h4>{title}</h4>}
      <table className="hole-metrics-table">
        <thead><tr><th>Показатель</th><th>Значение</th></tr></thead>
        <tbody>{rows.map(([label, value], i) => <tr key={i}><td>{label}</td><td>{value}</td></tr>)}</tbody>
      </table>
    </div>
  );
}
