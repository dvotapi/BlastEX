/**
 * Карточка раздела «Бурение».
 *
 * Бурение — единственный раздел сметы, у которого способ исполнения меняет
 * саму статью затрат: свои силы дают метр из амортизации, топлива и экипажа,
 * субподряд — одну ставку по договору. Строкой таблицы это не показать: в
 * строке нет места ни под переключатель, ни под объём с ценой метра и их
 * происхождением. Поэтому раздел открывается карточкой, а обычные строки
 * (топливо, запчасти, амортизация) идут под ней.
 *
 * Карточка ничего не считает: сумму, объём и цену метра ей передают уже
 * посчитанными.
 */
import type { ReactNode } from "react";
import { OriginBadge } from "../estimate/OriginBadge";
import { money, perM3 } from "../format";
import type { ValueOrigin } from "../../../types/blockEconomics";

/** Величина бурения: либо готовое значение с происхождением, либо поле ввода. */
export type DrillingFact = {
  label: string;
  /** Готовое значение — когда величину считает модель или несёт паспорт. */
  value?: string;
  /** Поле ввода — когда величину задаёт сметчик; показывается вместо `value`. */
  editor?: ReactNode;
  origin?: ValueOrigin;
  originLabel?: string;
  originTitle?: string;
};

export function DrillingCard({
  executor,
  machine,
  facts,
  amount,
  volume,
  action,
  footer,
}: {
  /** Переключатель «Собственными силами / Субподряд» — от `DrillingSection`. */
  executor: ReactNode;
  /** Выбор станка либо пара «подрядчик + тариф». */
  machine: ReactNode;
  facts: DrillingFact[];
  amount: number;
  volume: number | null;
  /** Кнопка разложения метра либо публикации тарифа. */
  action?: ReactNode;
  /** Ссылки и формы под карточкой: переход в калькулятор, публикация тарифа. */
  footer?: ReactNode;
}) {
  return (
    <div className="estimate-card drilling-card">
      <div className="drilling-card-col">
        {executor}
        {machine}
      </div>
      <div className="drilling-card-col drilling-card-facts">
        {facts.map((fact) => (
          <div className="drilling-card-fact" key={fact.label}>
            <span className="drilling-card-fact-label">{fact.label}</span>
            <span className="drilling-card-fact-value">
              {fact.editor ?? fact.value}
              {fact.origin && (
                <OriginBadge origin={fact.origin} label={fact.originLabel} title={fact.originTitle} />
              )}
            </span>
          </div>
        ))}
      </div>
      <div className="drilling-card-col drilling-card-total">
        <span className="drilling-card-fact-label">Сумма</span>
        <b className="drilling-card-amount">{money(amount, 0)} ₽</b>
        <span className="drilling-card-perm3">{perM3(amount, volume)}</span>
        {action}
      </div>
      {footer && <div className="drilling-card-footer">{footer}</div>}
    </div>
  );
}
