import { useEffect, useRef, useState, type ReactNode } from "react";
import { OriginBadge } from "./OriginBadge";
import { RowMenu, type RowMenuItem } from "./RowMenu";
import { amount as formatAmount, money, perM3, percent, reconcilingColumns } from "../format";
import type { ValueOrigin } from "../../../types/blockEconomics";

/**
 * Величина без собственной колонки — серой подписью под названием статьи.
 *
 * Смены бригады на блок, плановые смены техники в месяц: колонок под них в
 * смете нет и быть не должно (в бумажной смете их тоже нет), но сметчик
 * обязан видеть, что за число сейчас в силе и откуда оно взялось. Правится
 * такая величина из меню строки, а не полем прямо в строке — иначе редакторы
 * лезут в колонку действий и наползают на суммы.
 */
export type EstimateLineCaption = {
  label: string;
  /** Уже отформатированное значение: «18», «норматив», «309 095 ₽». */
  value: string;
  origin?: ValueOrigin;
  originLabel?: string;
  originTitle?: string;
  /** Подпись-ссылка: уводит туда, где величина живёт на самом деле. */
  onClick?: () => void;
};

/**
 * Строка сметы: № · статья · основание · кол-во · ед. · цена · сумма ·
 * ₽/м³ · % · ⋯. Количество и цена форматируются вместе через
 * `reconcilingColumns`, чтобы их произведение сходилось с показанной суммой;
 * когда одной из величин нет (например, у ФОТ нет единой ставки за смену),
 * колонка просто гасится прочерком.
 *
 * Меню строки — ровно одно на строку. Пункты раздела («Убрать», «Сбросить к
 * нормативу») склеиваются здесь же с пунктом-раскрывашкой редактора и
 * «Формулой»: раньше раздел рисовал своё меню, а строка своё, и у строк
 * материалов рядом стояли две одинаковые кнопки «⋯».
 */
export function EstimateLine({
  number,
  name,
  captions,
  origin,
  originLabel,
  quantity,
  quantityEditor,
  unit,
  price,
  amount,
  volume,
  share,
  menuItems,
  menuLabel,
  editor,
  editorMenuLabel = "Изменить",
  formula,
}: {
  number: string;
  name: ReactNode;
  captions?: EstimateLineCaption[];
  origin: ValueOrigin;
  originLabel?: string;
  quantity: number | null;
  /** Компактное поле прямо в колонке «Кол-во» — там, где величина и есть количество. */
  quantityEditor?: ReactNode;
  unit: string;
  price: number | null;
  /** null — сумма строки учтена в другом разделе: «—» вместо числа. */
  amount: number | null;
  volume: number | null;
  /** null — доля не считается: пустая ячейка процента. */
  share: number | null;
  /** Пункты меню от раздела; сам раздел `RowMenu` больше не рисует. */
  menuItems?: RowMenuItem[];
  menuLabel?: string;
  /** Панель правки под строкой, открывается пунктом меню `editorMenuLabel`. */
  editor?: ReactNode;
  editorMenuLabel?: string;
  formula?: string;
}) {
  const [panel, setPanel] = useState<"editor" | "formula" | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const rowRef = useRef<HTMLDivElement>(null);

  // Открытая панель правки забирает фокус: пункт меню — это обещание, что
  // сейчас можно править, и искать поле мышью после выбора пункта не нужно.
  useEffect(() => {
    if (panel !== "editor") return;
    panelRef.current?.querySelector<HTMLElement>("input, select, textarea, button")?.focus();
  }, [panel]);

  function closePanel() {
    setPanel(null);
    rowRef.current?.querySelector<HTMLElement>(".row-menu-trigger")?.focus();
  }

  let quantityText = "—";
  let priceText = "—";
  if (quantityEditor) {
    // Пока сметчик печатает, количество в поле и количество в последнем
    // ответе модели расходятся — согласовывать по ним цену значит дёргать
    // колонку цены на каждом нажатии клавиши.
    priceText = price === null ? "—" : money(price);
  } else if (quantity !== null && price !== null && amount !== null) {
    const reconciled = reconcilingColumns(quantity, price, amount);
    quantityText = reconciled.quantity;
    priceText = reconciled.price;
  } else {
    if (quantity !== null) quantityText = formatAmount(quantity);
    if (price !== null) priceText = money(price);
  }

  const panelId = `estimate-line-${number}-panel`;
  const rowLabel = menuLabel ?? `Действия: строка ${number}`;
  const sectionItems = menuItems ?? [];
  const items: RowMenuItem[] = [
    ...(editor
      ? [
          {
            label: editorMenuLabel,
            onSelect: () => setPanel((current) => (current === "editor" ? null : "editor")),
            expanded: panel === "editor",
            controls: panelId,
          },
        ]
      : []),
    ...sectionItems.filter((item) => !item.danger),
    ...(formula
      ? [
          {
            label: "Формула",
            onSelect: () => setPanel((current) => (current === "formula" ? null : "formula")),
            expanded: panel === "formula",
            controls: panelId,
          },
        ]
      : []),
    // «Убрать» — последним пунктом: разрушительное действие не должно стоять
    // там, куда рука идёт по привычке.
    ...sectionItems.filter((item) => item.danger),
  ];

  return (
    <div className="estimate-line-wrap">
      <div
        ref={rowRef}
        className={`estimate-row estimate-line${amount === null ? " is-reference" : ""}`}
        role="row"
      >
        <span role="cell" className="estimate-col-number">{number}</span>
        <span role="cell" className="estimate-col-name">
          <span className="estimate-line-title">{name}</span>
          {captions && captions.length > 0 && (
            <span className="estimate-line-caption">
              {captions.map((caption, index) => (
                <span className="estimate-line-caption-item" key={caption.label}>
                  {index > 0 && <span aria-hidden="true" className="estimate-line-caption-sep">·</span>}
                  {caption.onClick ? (
                    <button type="button" className="link-button" onClick={caption.onClick}>
                      {caption.label}: {caption.value}
                    </button>
                  ) : (
                    <span>
                      {caption.label}: {caption.value}
                    </span>
                  )}
                  {caption.origin && (
                    <OriginBadge
                      origin={caption.origin}
                      label={caption.originLabel}
                      title={caption.originTitle}
                    />
                  )}
                </span>
              ))}
            </span>
          )}
        </span>
        <span role="cell" className="estimate-col-basis">
          <OriginBadge origin={origin} label={originLabel} />
        </span>
        <span role="cell" className="estimate-col-quantity">
          {quantityEditor ?? quantityText}
        </span>
        <span role="cell" className="estimate-col-unit">{unit}</span>
        <span role="cell" className="estimate-col-price">{priceText}</span>
        <span role="cell" className="estimate-col-amount">{amount === null ? "—" : money(amount)}</span>
        <span role="cell" className="estimate-col-perm3">
          {amount === null ? "—" : perM3(amount, volume)}
        </span>
        <span role="cell" className="estimate-col-share">{share === null ? "" : percent(share)}</span>
        <span role="cell" className="estimate-col-actions">
          <RowMenu items={items} label={rowLabel} />
        </span>
      </div>
      {(editor || formula) && (
        <div
          id={panelId}
          ref={panelRef}
          className="estimate-line-panel"
          role="group"
          aria-label={`${rowLabel}: параметры`}
          hidden={panel === null}
          // Панель — поверхность правки, а не всплывашка: клик вне её не
          // закрывает, закрывает тот же пункт меню или Escape внутри.
          onKeyDown={(event) => {
            if (event.key !== "Escape") return;
            event.stopPropagation();
            closePanel();
          }}
        >
          {panel === "editor" && editor}
          {panel === "formula" && <code>{formula}</code>}
        </div>
      )}
    </div>
  );
}
