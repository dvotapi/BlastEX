import { useState, type ReactNode } from "react";
import { OriginBadge } from "./OriginBadge";
import { RowMenu } from "./RowMenu";
import { amount as formatAmount, money, perM3, percent, reconcilingColumns } from "../format";
import type { ValueOrigin } from "../../../types/blockEconomics";

/**
 * Строка сметы: № · статья · основание · кол-во · ед. · цена · сумма ·
 * ₽/м³ · % · ⋯. Количество и цена форматируются вместе через
 * `reconcilingColumns`, чтобы их произведение сходилось с показанной суммой;
 * когда одной из величин нет (например, у ФОТ нет единой ставки за смену),
 * колонка просто гасится прочерком.
 */
export function EstimateLine({
  number,
  name,
  origin,
  originLabel,
  quantity,
  unit,
  price,
  amount,
  volume,
  share,
  actions,
  formula,
}: {
  number: string;
  name: ReactNode;
  origin: ValueOrigin;
  originLabel?: string;
  quantity: number | null;
  unit: string;
  price: number | null;
  amount: number;
  volume: number | null;
  share: number;
  actions?: ReactNode;
  formula?: string;
}) {
  const [formulaOpen, setFormulaOpen] = useState(false);

  let quantityText = "—";
  let priceText = "—";
  if (quantity !== null && price !== null) {
    const reconciled = reconcilingColumns(quantity, price, amount);
    quantityText = reconciled.quantity;
    priceText = reconciled.price;
  } else {
    if (quantity !== null) quantityText = formatAmount(quantity);
    if (price !== null) priceText = money(price);
  }

  const menuItems = formula ? [{ label: "Формула", onSelect: () => setFormulaOpen((v) => !v) }] : [];
  const formulaId = `${number}-formula`;

  return (
    <div className="estimate-line-wrap">
      <div className="estimate-row estimate-line" role="row">
        <span role="cell" className="estimate-col-number">{number}</span>
        <span role="cell" className="estimate-col-name">{name}</span>
        <span role="cell" className="estimate-col-basis">
          <OriginBadge origin={origin} label={originLabel} />
        </span>
        <span role="cell" className="estimate-col-quantity">{quantityText}</span>
        <span role="cell" className="estimate-col-unit">{unit}</span>
        <span role="cell" className="estimate-col-price">{priceText}</span>
        <span role="cell" className="estimate-col-amount">{money(amount)}</span>
        <span role="cell" className="estimate-col-perm3">{perM3(amount, volume)}</span>
        <span role="cell" className="estimate-col-share">{percent(share)}</span>
        <span role="cell" className="estimate-col-actions">
          {actions}
          <RowMenu items={menuItems} label={`Действия: строка ${number}`} />
        </span>
      </div>
      {formula && (
        <details className="estimate-line-formula" open={formulaOpen}>
          <summary id={formulaId} className="sr-only">Формула строки {number}</summary>
          <code>{formula}</code>
        </details>
      )}
    </div>
  );
}
