import { ruNumber } from "../../lib/format";
import type { OptimizationCandidate, OptimizationResult } from "../../types/design";
import { OPTIMIZATION_OBJECTIVE_LABELS, OPTIMIZATION_OBJECTIVE_UNITS } from "../../types/design";
import { RoleBadge } from "./RoleBadge";

export type OptimizationVariableDraft = {
  name: string;
  label: string;
  unit: string;
  enabled: boolean;
  valuesText: string;
};

function formatObjective(key: string, value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  if (key === "cost") return ruNumber(value, 0);
  if (key === "target_x50" || key === "oversize") return ruNumber(value, 1);
  return ruNumber(value, 1);
}

function candidateLabel(item: OptimizationCandidate): string {
  const values = item.decision.values;
  const parts: string[] = [];
  if (values.diameter_mm != null) parts.push(`${values.diameter_mm} мм`);
  if (values.burden_b_m != null && values.spacing_a_m != null) {
    parts.push(`${values.burden_b_m}×${values.spacing_a_m} м`);
  }
  if (values.explosive_key) parts.push(String(values.explosive_key));
  if (values.inclination_deg != null) parts.push(`${values.inclination_deg}°`);
  if (values.delay_interval_ms != null) parts.push(`${values.delay_interval_ms} мс`);
  if (!parts.length) return item.kind === "approved_baseline" ? "Утверждённый проект" : item.candidate_id;
  return parts.join(" · ");
}

export function OptimizationPanel({
  targetX50Mm,
  onTargetX50Change,
  maxCandidates,
  onMaxCandidatesChange,
  variables,
  onVariableToggle,
  onVariableValuesChange,
  objectives,
  onObjectiveToggle,
  result,
  busy,
  onRun,
  onPromote,
}: {
  targetX50Mm: number;
  onTargetX50Change: (value: number) => void;
  maxCandidates: number;
  onMaxCandidatesChange: (value: number) => void;
  variables: OptimizationVariableDraft[];
  onVariableToggle: (name: string, enabled: boolean) => void;
  onVariableValuesChange: (name: string, valuesText: string) => void;
  objectives: string[];
  onObjectiveToggle: (key: string, enabled: boolean) => void;
  result: OptimizationResult | null;
  busy: boolean;
  onRun: () => void;
  onPromote: (candidate: OptimizationCandidate) => void;
}) {
  const rows = result
    ? [...result.candidates].sort((a, b) => Number(b.on_pareto) - Number(a.on_pareto) || a.candidate_id.localeCompare(b.candidate_id))
    : [];
  return (
    <section className="panel">
      <header><b>Оптимизация Парето</b><RoleBadge role="predicted" /></header>
      <div className="panel-body">
        <small>
          Детерминированный перебор оверлеев. Утверждённый паспорт не заменяется и не перезаписывается. RL нет.
        </small>
        <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <label>Целевой X50, мм
            <input type="number" min={1} step={1} value={targetX50Mm} onChange={(e) => onTargetX50Change(Number(e.target.value))} />
          </label>
          <label>Лимит кандидатов
            <input type="number" min={2} max={80} step={1} value={maxCandidates} onChange={(e) => onMaxCandidatesChange(Number(e.target.value))} />
          </label>
        </div>
        <small>Цели (меньше — лучше)</small>
        <div className="dataset-tags">
          {Object.entries(OPTIMIZATION_OBJECTIVE_LABELS).map(([key, label]) => (
            <label key={key} className="check-row">
              <input
                type="checkbox"
                checked={objectives.includes(key)}
                onChange={(e) => onObjectiveToggle(key, e.target.checked)}
              />
              {label}
            </label>
          ))}
        </div>
        <small>Переменные, в объявленных единицах</small>
        {variables.map((item) => (
          <label key={item.name} className="check-row opt-axis">
            <input
              type="checkbox"
              checked={item.enabled}
              onChange={(e) => onVariableToggle(item.name, e.target.checked)}
            />
            <span>{item.label}{item.unit ? `, ${item.unit}` : ""}</span>
            <input
              type="text"
              value={item.valuesText}
              disabled={!item.enabled}
              onChange={(e) => onVariableValuesChange(item.name, e.target.value)}
            />
          </label>
        ))}
        <div className="plans-actions">
          <button type="button" className="calculate-button" onClick={onRun} disabled={busy || objectives.length === 0}>
            {busy ? "Ищем…" : "Найти Парето"}
          </button>
        </div>
        {result && (
          <div className="scenario-compare-wrap">
            <small>
              Оценено {result.evaluated}, на фронте {result.pareto_front.length}.
              {" "}Метод: {result.method}. Паспорт не изменён.
            </small>
            <table className="scenario-compare-table">
              <thead>
                <tr>
                  <th>Кандидат</th>
                  {result.objectives.map((key) => (
                    <th key={key}>
                      {OPTIMIZATION_OBJECTIVE_LABELS[key] || key}
                      <small>{OPTIMIZATION_OBJECTIVE_UNITS[key] || ""}</small>
                    </th>
                  ))}
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((item) => (
                  <tr key={item.candidate_id} className={item.on_pareto ? "pareto" : undefined}>
                    <th>
                      {candidateLabel(item)}
                      {item.candidate_id === result.compromise_candidate_id ? <small>компромисс</small> : null}
                      {item.on_pareto ? <small>Парето</small> : null}
                    </th>
                    {result.objectives.map((key) => (
                      <td key={`${item.candidate_id}-${key}`} className={item.on_pareto ? "best" : undefined}>
                        {formatObjective(key, item.objectives[key])}
                      </td>
                    ))}
                    <td>
                      <button
                        type="button"
                        className="secondary-button"
                        disabled={busy}
                        onClick={() => onPromote(item)}
                      >
                        В сценарий
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <small>Сохранение кандидата создаёт оверлей сравнения, а не новый утверждённый проект.</small>
            {result.warnings.length > 0 && <small>{result.warnings[0]}</small>}
          </div>
        )}
      </div>
    </section>
  );
}
