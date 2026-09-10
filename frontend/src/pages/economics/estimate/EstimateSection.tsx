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
        {/* Номер раздела — в колонке «№», как у строк: колонки читаются сверху
            вниз одной линейкой, а не сбиваются на заголовке раздела. */}
        <span role="cell" className="estimate-col-number estimate-section-number">{group.number}</span>
        <button
          type="button"
          className="estimate-section-toggle"
          // Номер виден в своей колонке, но в имени кнопки он остаётся: с
          // клавиатуры раздел называется так же, как читается глазами, и не
          // путается с одноимённым сегментом кольца в сайдбаре.
          aria-label={`${group.number}. ${group.label}`}
          aria-expanded={open}
          aria-controls={bodyId}
          onClick={onToggle}
        >
          <span aria-hidden="true" className="estimate-section-caret">{open ? "▾" : "▸"}</span>
          <span>{group.label}</span>
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
