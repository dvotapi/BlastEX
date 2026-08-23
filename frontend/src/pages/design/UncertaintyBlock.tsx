import { ruNumber } from "../../lib/format";
import type { UncertaintyInterval } from "../../types/design";

const CONFIDENCE_LABELS: Record<string, string> = {
  high: "Высокая",
  medium: "Средняя",
  low: "Низкая",
};

function confidenceLabel(value: string | undefined, fallback?: string): string {
  if (fallback) return fallback;
  if (!value) return "—";
  return CONFIDENCE_LABELS[value] ?? value;
}

function formatInterval(uncertainty: UncertaintyInterval | undefined, digits: number, unit: string): string {
  if (!uncertainty || uncertainty.lower == null || uncertainty.upper == null) return "—";
  const suffix = unit ? ` ${unit}` : "";
  return `${ruNumber(uncertainty.lower, digits)}–${ruNumber(uncertainty.upper, digits)}${suffix}`;
}

export function UncertaintyBlock({
  label,
  value,
  unit,
  digits = 1,
  uncertainty,
  confidence,
  confidenceLabelText,
  similarityScore,
  comparableCount,
  applicabilityWarning,
}: {
  label: string;
  value: number | null | undefined;
  unit: string;
  digits?: number;
  uncertainty?: UncertaintyInterval;
  confidence?: string;
  confidenceLabelText?: string;
  similarityScore?: number;
  comparableCount?: number;
  applicabilityWarning?: string;
}) {
  const similarityPct = similarityScore == null ? "—" : `${Math.round(similarityScore * 100)} %`;
  const comparable = comparableCount == null ? "—" : String(comparableCount);
  return (
    <div className="uncertainty-block">
      <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <div>
          <span>Прогноз {label}</span>
          <strong>{value == null || Number.isNaN(value) ? "—" : ruNumber(value, digits)}</strong>
          <small>{unit}</small>
        </div>
        <div>
          <span>Ожидаемый интервал</span>
          <strong>{formatInterval(uncertainty, digits, unit)}</strong>
        </div>
        <div>
          <span>Уверенность</span>
          <strong>{confidenceLabel(confidence, confidenceLabelText)}</strong>
        </div>
        <div>
          <span>Сопоставимых взрывов</span>
          <strong>{comparable}</strong>
        </div>
        <div>
          <span>Сходство</span>
          <strong>{similarityPct}</strong>
        </div>
      </div>
      {applicabilityWarning ? (
        <small className="applicability-warning">{applicabilityWarning}</small>
      ) : null}
    </div>
  );
}
