import type { ReactNode } from "react";
import type { EstimateGroup, EstimateGroupCode } from "../estimateModel";
import { EstimateSection } from "./EstimateSection";

/**
 * Каркас иерархической таблицы сметы: липкая шапка колонок и семь разделов
 * конструктора (`ESTIMATE_GROUPS`), каждый — раскрывающаяся секция. Само
 * содержимое раздела рисует вызывающий код через `renderGroup` (задача 7) —
 * здесь только структура таблицы и управление разворотом.
 */
export function EstimateBuilder({
  groups,
  volume,
  expanded,
  onToggle,
  onExpandAll,
  onCollapseAll,
  highlighted,
  renderGroup,
  busy,
}: {
  groups: EstimateGroup[];
  volume: number | null;
  expanded: Set<EstimateGroupCode>;
  onToggle: (code: EstimateGroupCode) => void;
  onExpandAll: () => void;
  onCollapseAll: () => void;
  highlighted: EstimateGroupCode | null;
  renderGroup: (group: EstimateGroup) => ReactNode;
  busy: boolean;
}) {
  return (
    <div className={`estimate-builder${busy ? " is-recalculating" : ""}`} aria-busy={busy}>
      <div className="estimate-builder-toolbar">
        <button type="button" onClick={onExpandAll}>Развернуть все</button>
        <button type="button" onClick={onCollapseAll}>Свернуть все</button>
      </div>
      <div className="estimate-table" role="table" aria-label="Смета блока">
        <div className="estimate-row estimate-head" role="row">
          <span role="columnheader" className="estimate-col-number">№</span>
          <span role="columnheader" className="estimate-col-name">Статья</span>
          <span role="columnheader" className="estimate-col-basis">Основание</span>
          <span role="columnheader" className="estimate-col-quantity">Кол-во</span>
          <span role="columnheader" className="estimate-col-unit">Ед.</span>
          <span role="columnheader" className="estimate-col-price">Цена</span>
          <span role="columnheader" className="estimate-col-amount">Сумма</span>
          <span role="columnheader" className="estimate-col-perm3">₽/м³</span>
          <span role="columnheader" className="estimate-col-share">%</span>
          <span role="columnheader" className="estimate-col-actions" aria-hidden="true" />
        </div>
        {groups.map((group) => (
          <EstimateSection
            key={group.code}
            group={group}
            volume={volume}
            open={expanded.has(group.code)}
            highlighted={highlighted === group.code}
            onToggle={() => onToggle(group.code)}
          >
            {renderGroup(group)}
          </EstimateSection>
        ))}
      </div>
    </div>
  );
}
