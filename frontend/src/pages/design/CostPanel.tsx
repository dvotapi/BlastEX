import { ruNumber } from "../../lib/format";
import type { CostScenarioId, DesignCostResult } from "../../types/design";
import { RoleBadge } from "./RoleBadge";

const SCENARIO_OPTIONS: { value: CostScenarioId; label: string }[] = [
  { value: "drill_blast", label: "Буровзрывные работы" },
  { value: "drilling", label: "Только бурение" },
  { value: "blasting", label: "Только взрывание" },
  { value: "contour_blasting", label: "Контурное взрывание" },
];

export function CostPanel({
  scenarioId,
  onScenarioChange,
  onCalculate,
  busy,
  result,
}: {
  scenarioId: CostScenarioId;
  onScenarioChange: (value: CostScenarioId) => void;
  onCalculate: () => void;
  busy: boolean;
  result: DesignCostResult | null;
}) {
  return (
    <section className="panel">
      <header><b>Смета по проекту</b><RoleBadge role="designed" /></header>
      <div className="panel-body">
        <label>Вид работ
          <select value={scenarioId} onChange={(e) => onScenarioChange(e.target.value as CostScenarioId)}>
            {SCENARIO_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
          </select>
        </label>
        <button className="calculate-button" onClick={onCalculate} disabled={busy}>
          {busy ? "Считаем смету…" : "Рассчитать смету"}
        </button>
        <small>Используются фактические число скважин, погонаж и масса ВВ из построенного проекта.</small>

        {result && (
          <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <div><span>Итого</span><strong>{ruNumber(result.total_amount_rub, 0)}</strong><small>₽</small></div>
            <div><span>Цена за м³</span><strong>{ruNumber(result.cost_per_m3, 1)}</strong><small>₽/м³</small></div>
            <div><span>Переменные</span><strong>{ruNumber(result.variable_total_rub, 0)}</strong><small>₽</small></div>
            <div><span>ФОТ</span><strong>{ruNumber(result.labor_total_rub, 0)}</strong><small>₽</small></div>
            <div><span>Постоянные</span><strong>{ruNumber(result.fixed_total_rub, 0)}</strong><small>₽</small></div>
            <div><span>Цена за тонну</span><strong>{result.cost_per_ton > 0 ? ruNumber(result.cost_per_ton, 1) : "—"}</strong><small>₽/т</small></div>
          </div>
        )}
      </div>
    </section>
  );
}
