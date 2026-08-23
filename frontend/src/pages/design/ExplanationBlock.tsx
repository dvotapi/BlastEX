import { ruNumber } from "../../lib/format";
import type { PredictionExplanation } from "../../types/design";

function shareLabel(value: number): string {
  return `${Math.round(value)}%`;
}

export function ExplanationBlock({
  explanation,
  fallbackTitle,
}: {
  explanation?: PredictionExplanation | null;
  fallbackTitle?: string;
}) {
  if (!explanation || explanation.method === "none") return null;
  const drivers = explanation.drivers || [];
  const recommendations = explanation.recommendations || [];
  if (!drivers.length && !recommendations.length) return null;
  const title = explanation.summary
    || (fallbackTitle ? `Основные драйверы ${fallbackTitle}` : "Основные драйверы прогноза");

  return (
    <div className="explanation-block">
      {drivers.length > 0 && (
        <>
          <small>{title}</small>
          <ul className="driver-list">
            {drivers.map((item) => (
              <li key={item.feature}>
                <span>{item.label || item.label_en || item.feature}</span>
                <strong>{shareLabel(item.share_pct)}</strong>
              </li>
            ))}
          </ul>
        </>
      )}
      {recommendations.length > 0 && (
        <ul className="recommendation-list">
          {recommendations.map((item) => (
            <li key={`${item.feature}-${item.action}`}>
              {item.summary || `${item.action_label}: ожидаемый ${item.target_label} ${ruNumber(item.delta, 1)} ${item.unit}`}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
