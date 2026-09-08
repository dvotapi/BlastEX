import { useState } from "react";
import { groupByLayerAndSection } from "./estimateSections";
import type { BlockCostLine, BlockEconomics } from "../../types/blockEconomics";

const money = (value: number, digits = 0) =>
  value.toLocaleString("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const amount = (value: number) => value.toLocaleString("ru-RU", { maximumFractionDigits: 2 });

/**
 * Смета блока: слои себестоимости, внутри — разделы бумажной сметы.
 *
 * Строка показывает то же, что колонки в Excel: норму, единицу, цену и
 * сумму. Формула раскрывается по клику — она объясняет, откуда взялась норма.
 */
export function CostStructure({ economics }: { economics: BlockEconomics }) {
  const [openLine, setOpenLine] = useState("");
  const volume = economics.block_volume_m3 || 1;
  const groups = groupByLayerAndSection(economics.lines);

  return (
    <section className="panel cost-structure">
      <header><b>Смета блока</b><span>по разделам внутри слоёв себестоимости</span></header>
      <div className="panel-body">
        {groups.map((group) => (
          <div className="cost-structure-group" key={group.layer}>
            <div className="cost-structure-head">
              <b>{group.label}</b>
              <span>{group.hint}</span>
              <strong>{money(group.total)} ₽</strong>
              <em>{(group.total / volume).toFixed(2)} ₽/м³</em>
            </div>
            {group.sections.map((section) => (
              <div className="cost-structure-section" key={section.section}>
                <div className="cost-structure-section-head">
                  <b>{section.number}</b>
                  <span>{section.label}</span>
                  <strong>{money(section.total)} ₽</strong>
                  <em>{(section.total / volume).toFixed(2)} ₽/м³</em>
                </div>
                {section.lines.map((line) => (
                  <CostRow
                    key={`${line.cost_item_code}-${line.operation_code}`}
                    line={line}
                    volume={volume}
                    open={openLine === line.cost_item_code}
                    onToggle={() =>
                      setOpenLine(openLine === line.cost_item_code ? "" : line.cost_item_code)
                    }
                  />
                ))}
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
  volume: number;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <div className={`cost-structure-row${open ? " open" : ""}`}>
      <button type="button" onClick={onToggle} aria-expanded={open}>
        <span className="cost-row-name">{line.cost_item_name}</span>
        {/* Прочерк, а не ноль: в смете пустая ячейка значит «здесь этого нет». */}
        <span className="cost-row-unit">{line.unit || "—"}</span>
        <span className="cost-row-quantity">{line.quantity === null ? "—" : amount(line.quantity)}</span>
        <span className="cost-row-price">
          {line.unit_price_rub === null ? "—" : money(line.unit_price_rub, 2)}
        </span>
        <b>{money(line.amount_rub)} ₽</b>
        <em>{(line.amount_rub / volume).toFixed(2)} ₽/м³</em>
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
