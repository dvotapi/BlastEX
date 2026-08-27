import { ruNumber } from "../../lib/format";
import type {
  DesignRecommendation,
  OptimizationCandidate,
  RecommendationAssessment,
} from "../../types/design";
import {
  OPTIMIZATION_OBJECTIVE_LABELS,
  OPTIMIZATION_OBJECTIVE_UNITS,
  RECOMMENDATION_PROFILE_LABELS,
} from "../../types/design";
import { RoleBadge } from "./RoleBadge";
import { ExplanationBlock } from "./ExplanationBlock";
import { UncertaintyBlock } from "./UncertaintyBlock";

const PROFILES = ["BALANCED", "LOW_COST", "FINE_FRAGMENTATION", "LOW_VIBRATION"] as const;

function formatObjective(key: string, value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  if (key === "cost") return ruNumber(value, 0);
  return ruNumber(value, 1);
}

function overlayLabel(item: OptimizationCandidate | null | undefined, fallback: string): string {
  if (!item) return fallback;
  const values = item.decision.values;
  const parts: string[] = [];
  if (values.diameter_mm != null) parts.push(`${values.diameter_mm} мм`);
  if (values.burden_b_m != null && values.spacing_a_m != null) {
    parts.push(`${values.burden_b_m}×${values.spacing_a_m} м`);
  } else if (values.burden_b_m != null) {
    parts.push(`ЛНС ${values.burden_b_m} м`);
  }
  if (values.explosive_key) parts.push(String(values.explosive_key));
  if (!parts.length) return item.kind === "approved_baseline" ? "Утверждённый проект" : item.candidate_id;
  return parts.join(" · ");
}

function AssessmentCard({ item }: { item: RecommendationAssessment }) {
  return (
    <div className="recommendation-assessment">
      <UncertaintyBlock
        label={item.target_label || item.target_name}
        value={item.prediction}
        unit={item.unit}
        uncertainty={item.uncertainty}
        confidence={item.confidence}
        confidenceLabelText={item.confidence_label}
        similarityScore={item.similarity_score}
        comparableCount={item.comparable_count}
        applicabilityWarning={item.applicability_warning}
      />
      <ExplanationBlock explanation={item.explanation} fallbackTitle={item.target_label} />
    </div>
  );
}

export function RecommendationPanel({
  profile,
  onProfileChange,
  useOverlays,
  onUseOverlaysChange,
  result,
  busy,
  onRun,
  onPromote,
}: {
  profile: string;
  onProfileChange: (value: string) => void;
  useOverlays: boolean;
  onUseOverlaysChange: (value: boolean) => void;
  result: DesignRecommendation | null;
  busy: boolean;
  onRun: () => void;
  onPromote: (candidate: OptimizationCandidate) => void;
}) {
  const suggested = result?.suggested ?? null;
  const objectives = result?.objectives ?? [];
  return (
    <section className="panel">
      <header><b>ML-рекомендация</b><RoleBadge role="predicted" /></header>
      <div className="panel-body">
        <small>
          Предлагает оверлей по профилю. Паспорт не утверждается и не перезаписывается. Решение принимает инженер.
        </small>
        <label>Профиль
          <select value={profile} onChange={(e) => onProfileChange(e.target.value)}>
            {PROFILES.map((key) => (
              <option key={key} value={key}>{RECOMMENDATION_PROFILE_LABELS[key]} · {key}</option>
            ))}
          </select>
        </label>
        <label className="check-row">
          <input type="checkbox" checked={useOverlays} onChange={(e) => onUseOverlaysChange(e.target.checked)} />
          Подставить production-модели (интервал, уверенность, сходство)
        </label>
        <div className="plans-actions">
          <button type="button" className="calculate-button" onClick={onRun} disabled={busy}>
            {busy ? "Считаем…" : "Рекомендовать оверлей"}
          </button>
        </div>
        {result && (
          <div className="recommendation-result">
            <small className="recommendation-banner">
              Рекомендация, не утверждение. Автоприменение выключено. Роль источника: {result.source_design_role}.
              Роль оверлея: {result.suggested_role}.
            </small>
            <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <div>
                <span>Профиль</span>
                <strong>{RECOMMENDATION_PROFILE_LABELS[result.profile] || result.profile}</strong>
              </div>
              <div>
                <span>Предложение</span>
                <strong>{overlayLabel(suggested, "нет допустимого оверлея")}</strong>
              </div>
              <div>
                <span>Оценено / Парето</span>
                <strong>{result.evaluated} / {result.pareto_count}</strong>
              </div>
              <div>
                <span>Применено само</span>
                <strong>{result.auto_applied ? "да" : "нет"}</strong>
              </div>
            </div>
            {suggested && objectives.length > 0 && (
              <table className="scenario-compare-table">
                <thead>
                  <tr>
                    <th></th>
                    {objectives.map((key) => (
                      <th key={key}>
                        {OPTIMIZATION_OBJECTIVE_LABELS[key] || key}
                        <small>{OPTIMIZATION_OBJECTIVE_UNITS[key] || ""}</small>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.baseline && (
                    <tr>
                      <th>Утверждённый проект</th>
                      {objectives.map((key) => (
                        <td key={`base-${key}`}>{formatObjective(key, result.baseline?.objectives[key])}</td>
                      ))}
                    </tr>
                  )}
                  <tr className="pareto">
                    <th>Рекомендация<small>PREDICTED</small></th>
                    {objectives.map((key) => (
                      <td key={`sug-${key}`} className="best">{formatObjective(key, suggested.objectives[key])}</td>
                    ))}
                  </tr>
                </tbody>
              </table>
            )}
            {result.reasons.length > 0 && (
              <ul className="recommendation-why">
                {result.reasons.map((item, index) => (
                  <li key={`${item.kind}-${item.metric}-${index}`}>
                    <strong>{item.title}</strong>
                    <span>{item.detail}</span>
                  </li>
                ))}
              </ul>
            )}
            {result.assessments.filter((item) => item.model_available).map((item) => (
              <AssessmentCard key={item.target_name} item={item} />
            ))}
            {suggested && (
              <div className="plans-actions">
                <button
                  type="button"
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => onPromote(suggested)}
                >
                  Сохранить как сценарий
                </button>
              </div>
            )}
            <small>Сохранение создаёт оверлей сравнения. Утверждённый паспорт остаётся без изменений.</small>
            {result.warnings.length > 0 && <small>{result.warnings[0]}</small>}
          </div>
        )}
      </div>
    </section>
  );
}
