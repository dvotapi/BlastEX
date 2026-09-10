import type { ReactNode } from "react";
import type { EstimateGroup } from "../estimateModel";
import { money, perM3, percent } from "../format";

/**
 * Раздел сметы: заголовок-кнопка (номер, имя, итог раздела — виден всегда,
 * даже свёрнутым) и тело со строками, которое рисует вызывающий код через
 * `children`. `id` секции фиксирован по коду раздела — по нему прокручивает
 * клик по диаграмме себестоимости.
 */
export function EstimateSection({
  group,
  volume,
  open,
  highlighted,
  onToggle,
  children,
}: {
  group: EstimateGroup;
  volume: number | null;
  open: boolean;
  highlighted: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  const bodyId = `estimate-section-body-${group.code}`;

  return (
    <section
      id={`estimate-section-${group.code}`}
      className={`estimate-section${highlighted ? " is-highlighted" : ""}`}
    >
      <div className="estimate-row estimate-section-head" role="row">
        <button
          type="button"
          className="estimate-section-toggle"
          aria-expanded={open}
          aria-controls={bodyId}
          onClick={onToggle}
        >
          <span aria-hidden="true" className="estimate-section-caret">{open ? "▾" : "▸"}</span>
          <span>{group.number}. {group.label}</span>
        </button>
        <span role="cell" className="estimate-col-basis" />
        <span role="cell" className="estimate-col-quantity" />
        <span role="cell" className="estimate-col-unit" />
        <span role="cell" className="estimate-col-price" />
        <span role="cell" className="estimate-col-amount">{money(group.total)}</span>
        <span role="cell" className="estimate-col-perm3">{perM3(group.total, volume)}</span>
        <span role="cell" className="estimate-col-share">{percent(group.share)}</span>
        <span role="cell" className="estimate-col-actions" />
      </div>
      {open && (
        <div id={bodyId} className="estimate-section-body">
          {children}
        </div>
      )}
    </section>
  );
}
