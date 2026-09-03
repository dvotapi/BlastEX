import type { BlockEconomics } from "../../types/blockEconomics";

/** Предупреждения модели: незаполненные нормы и узкие места мощности. */
export function ModelWarnings({ economics }: { economics: BlockEconomics }) {
  if (!economics.warnings.length && !economics.capacity.length) return null;
  return (
    <div className="calculation-warnings" role="status">
      <b>Модель сообщает</b>
      <ul>
        {economics.capacity.map((item) => (
          <li key={item.resource_code}>
            {item.message} (требуется {item.required} {item.unit}
            {item.available !== null ? `, доступно ${item.available} ${item.unit}` : ""})
          </li>
        ))}
        {economics.warnings
          .filter((warning) => !economics.capacity.some((item) => item.message === warning))
          .map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
      </ul>
    </div>
  );
}
