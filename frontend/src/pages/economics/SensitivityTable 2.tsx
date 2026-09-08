import type { SensitivityRow } from "../../types/blockEconomics";

const money = (value: number) => value.toFixed(2);

/** Чувствительность полной цены м³ к ±10 % по каждому параметру. */
export function SensitivityTable({
  rows,
  busy,
  onCompute,
}: {
  rows: SensitivityRow[];
  busy: boolean;
  onCompute: () => void;
}) {
  return (
    <section className="panel sensitivity-panel">
      <header>
        <b>Чувствительность</b>
        <button type="button" className="secondary-button" onClick={onCompute} disabled={busy}>
          {busy ? "Считаем…" : "Рассчитать ±10 %"}
        </button>
      </header>
      {rows.length === 0 ? (
        <p className="page-caption">
          Перебор ±10 % по цене ВВ, массе ВВ, погонажу, плану юнита, сменам станка,
          численности бригады, цене ДТ и сдельным расценкам.
        </p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Параметр</th>
                <th>−10 %, ₽/м³</th>
                <th>+10 %, ₽/м³</th>
                <th>Δ цены м³</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.code}>
                  <td>{row.label}</td>
                  <td>{money(row.price_minus_rub_m3)}</td>
                  <td>{money(row.price_plus_rub_m3)}</td>
                  <td className={row.delta_rub_m3 < 0 ? "metric-negative" : ""}>
                    {row.delta_rub_m3 > 0 ? "+" : ""}{money(row.delta_rub_m3)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
