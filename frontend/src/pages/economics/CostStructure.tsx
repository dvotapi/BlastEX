import { useMemo, useState } from "react";
import { groupByLayerAndSection } from "./estimateSections";
import { amount, money, perM3, reconcilingColumns } from "./format";
import type { BlockCostLine, BlockEconomics } from "../../types/blockEconomics";

/**
 * Смета блока: слои себестоимости, внутри — разделы бумажной сметы.
 *
 * Строка показывает то же, что колонки в Excel: норму, единицу, цену и
 * сумму. Формула раскрывается по клику — она объясняет, откуда взялась норма.
 */
export function CostStructure({ economics }: { economics: BlockEconomics }) {
  const [openLine, setOpenLine] = useState("");
  // Ноль здесь не «единица»: при пустом объёме блока сумма, делённая на 1,
  // выглядела бы как цена кубометра и расходилась с ₽/м³ из модели, где
  // при нулевом объёме цены обнулены с предупреждением.
  const volume = economics.block_volume_m3 > 0 ? economics.block_volume_m3 : null;
  const groups = useMemo(() => groupByLayerAndSection(economics.lines), [economics.lines]);

  return (
    <section className="panel cost-structure">
      <header><b>Смета блока</b><span>по разделам внутри слоёв себестоимости</span></header>
      <div className="panel-body">
        {groups.map((group) => (
          <div className="cost-structure-group" key={group.layer}>
            <div className="cost-structure-head">
              <b>{group.label}</b>
              <span>{group.hint}</span>
              <strong>{money(group.total, 0)} ₽</strong>
              <em>{perM3(group.total, volume)}</em>
            </div>
            {group.sections.map((section) => (
              <div className="cost-structure-section" key={section.section}>
                <div className="cost-structure-section-head">
                  <b>{section.number}</b>
                  <span>{section.label}</span>
                  <strong>{money(section.total, 0)} ₽</strong>
                  <em>{perM3(section.total, volume)}</em>
                </div>
                {section.lines.map((line, index) => {
                  // Ключ строки — код, операция и номер повтора: две услуги с
                  // одним названием или две записи одной должности дают строки
                  // с одинаковым кодом, и по коду они раскрывались бы вместе.
                  // Место в разделе для ключа не годится: исчезнувшая выше
                  // строка сдвинула бы его и закрыла раскрытую.
                  const twin = section.lines.filter(
                    (row, position) =>
                      position < index &&
                      row.cost_item_code === line.cost_item_code &&
                      row.operation_code === line.operation_code,
                  ).length;
                  const id = `${section.section}-${line.cost_item_code}-${line.operation_code}-${twin}`;
                  return (
                    <CostRow
                      key={id}
                      line={line}
                      volume={volume}
                      open={openLine === id}
                      onToggle={() => setOpenLine(openLine === id ? "" : id)}
                    />
                  );
                })}
              </div>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}

function CostRow({
  line,
  volume,
  open,
  onToggle,
}: {
  line: BlockCostLine;
  volume: number | null;
  open: boolean;
  onToggle: () => void;
}) {
  // Норма и цена печатаются вместе: их произведение должно давать сумму
  // строки, а для этого знаки подбираются по обоим числам сразу.
  const columns =
    line.quantity === null || line.unit_price_rub === null
      ? null
      : reconcilingColumns(line.quantity, line.unit_price_rub, line.amount_rub);

  return (
    <div className={`cost-structure-row${open ? " open" : ""}`}>
      <button type="button" onClick={onToggle} aria-expanded={open}>
        <span className="cost-row-name">{line.cost_item_name}</span>
        {/* Прочерк, а не ноль: в смете пустая ячейка значит «здесь этого нет». */}
        <span className="cost-row-unit">{line.unit || "—"}</span>
        <span className="cost-row-quantity">
          {columns?.quantity ?? (line.quantity === null ? "—" : amount(line.quantity))}
        </span>
        <span className="cost-row-price">{columns?.price ?? "—"}</span>
        <b>{money(line.amount_rub, 0)} ₽</b>
        <em>{perM3(line.amount_rub, volume)}</em>
      </button>
      {open && (
        <p className="cost-structure-formula">
          {line.formula || "Формула не задана"}
          {line.operation_code ? ` · операция ${line.operation_code}` : ""}
        </p>
      )}
    </div>
  );
}
