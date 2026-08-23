import { ruNumber } from "../../lib/format";
import type {
  DesignScenarioSummary,
  ScenarioCompareResponse,
} from "../../types/design";
import { RoleBadge } from "./RoleBadge";

function formatMetric(key: string, value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  if (key === "hole_count") return ruNumber(value, 0);
  if (key === "direct_cost_rub" || key === "total_predicted_cost_rub") return ruNumber(value, 0);
  if (key === "x50_mm" || key === "x80_mm" || key === "diameter_mm") return ruNumber(value, 0);
  if (key === "powder_factor_kg_m3") return ruNumber(value, 2);
  return ruNumber(value, 1);
}

export function ScenarioPanel({
  name,
  onNameChange,
  diameterMm,
  onDiameterChange,
  spacingM,
  onSpacingChange,
  burdenM,
  onBurdenChange,
  powderFactor,
  onPowderFactorChange,
  useOverlays,
  onUseOverlaysChange,
  items,
  compare,
  busy,
  onCreate,
  onCompare,
}: {
  name: string;
  onNameChange: (value: string) => void;
  diameterMm: number;
  onDiameterChange: (value: number) => void;
  spacingM: number;
  onSpacingChange: (value: number) => void;
  burdenM: number;
  onBurdenChange: (value: number) => void;
  powderFactor: number;
  onPowderFactorChange: (value: number) => void;
  useOverlays: boolean;
  onUseOverlaysChange: (value: boolean) => void;
  items: DesignScenarioSummary[];
  compare: ScenarioCompareResponse | null;
  busy: boolean;
  onCreate: () => void;
  onCompare: () => void;
}) {
  return (
    <section className="panel">
      <header><b>Сценарии сетки</b><RoleBadge role="predicted" /></header>
      <div className="panel-body">
        <small>
          Копии поверх утверждённого паспорта: диаметр, сетка и q. Проектные скважины и заряды не перезаписываются.
        </small>
        <label>Имя
          <input type="text" value={name} onChange={(e) => onNameChange(e.target.value)} />
        </label>
        <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <label>Диаметр, мм
            <input type="number" min={50} step={1} value={diameterMm} onChange={(e) => onDiameterChange(Number(e.target.value))} />
          </label>
          <label>q, кг/м³
            <input type="number" min={0.05} step={0.01} value={powderFactor} onChange={(e) => onPowderFactorChange(Number(e.target.value))} />
          </label>
          <label>ЛНС, м
            <input type="number" min={0.5} step={0.1} value={burdenM} onChange={(e) => onBurdenChange(Number(e.target.value))} />
          </label>
          <label>Шаг, м
            <input type="number" min={0.5} step={0.1} value={spacingM} onChange={(e) => onSpacingChange(Number(e.target.value))} />
          </label>
        </div>
        <label className="check-row">
          <input type="checkbox" checked={useOverlays} onChange={(e) => onUseOverlaysChange(e.target.checked)} />
          Подставить ML-оверлей, если есть production-модели
        </label>
        <div className="plans-actions">
          <button type="button" className="calculate-button" onClick={onCreate} disabled={busy || !name.trim()}>
            {busy ? "Считаем…" : "Добавить сценарий"}
          </button>
          <button type="button" className="secondary-button" onClick={onCompare} disabled={busy || items.length === 0}>
            Сравнить
          </button>
        </div>
        {items.length > 0 && (
          <ul className="plans-list">
            {items.map((item) => (
              <li key={item.scenario_id}>
                <span className="plans-list-open">
                  <b>{item.name}</b>
                  <small>
                    {item.diameter_mm != null ? `${ruNumber(item.diameter_mm, 0)} мм` : "—"}
                    {" · "}
                    {item.burden_b_m != null && item.spacing_a_m != null
                      ? `${ruNumber(item.burden_b_m, 1)} × ${ruNumber(item.spacing_a_m, 1)} м`
                      : "сетка —"}
                    {item.powder_factor_kg_m3 != null ? ` · q ${ruNumber(item.powder_factor_kg_m3, 2)}` : ""}
                  </small>
                </span>
              </li>
            ))}
          </ul>
        )}
        {compare && (
          <div className="scenario-compare-wrap">
            <table className="scenario-compare-table">
              <thead>
                <tr>
                  <th>Показатель</th>
                  {compare.scenarios.map((column) => (
                    <th key={column.scenario_id}>{column.name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {compare.rows.map((row) => (
                  <tr key={row.key}>
                    <th>
                      {row.label}
                      <small>{row.unit}</small>
                    </th>
                    {compare.scenarios.map((column) => {
                      const value = row.values[column.scenario_id];
                      const best = row.best_scenario_id === column.scenario_id;
                      return (
                        <td key={`${row.key}-${column.scenario_id}`} className={best ? "best" : undefined}>
                          {formatMetric(row.key, value)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            <small>Это таблица сравнения, не оптимизатор. Лучшие значения по затратам и негативу лишь подсвечены.</small>
          </div>
        )}
      </div>
    </section>
  );
}
