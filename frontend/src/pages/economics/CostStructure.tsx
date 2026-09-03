import { useState } from "react";
import type { BlockCostLine, BlockEconomics, CostLayer } from "../../types/blockEconomics";

const LAYERS: { code: CostLayer; label: string; hint: string }[] = [
  { code: "variable", label: "Переменные затраты", hint: "растут вместе с объёмом блока" },
  { code: "project_direct", label: "Прямые затраты блока", hint: "ФОТ, амортизация по сменам, мобилизация" },
  { code: "production", label: "Постоянные затраты юнита", hint: "распределены по плановому объёму" },
  { code: "full", label: "Нераспределённые затраты", hint: "не отнесены на блок напрямую" },
];

const money = (value: number) =>
  value.toLocaleString("ru-RU", { minimumFractionDigits: 0, maximumFractionDigits: 0 });

/** Структура затрат по слоям и статьям; формула раскрывается по клику. */
export function CostStructure({ economics }: { economics: BlockEconomics }) {
  const [openLine, setOpenLine] = useState("");
  const volume = economics.block_volume_m3 || 1;

  const byLayer = LAYERS.map((layer) => ({
    ...layer,
    lines: economics.lines.filter((line) => line.layer === layer.code),
  })).filter((group) => group.lines.length > 0);

  return (
    <section className="panel cost-structure">
      <header><b>Структура затрат</b><span>по слоям себестоимости</span></header>
      <div className="panel-body">
        {byLayer.map((group) => {
          const total = group.lines.reduce((sum, line) => sum + line.amount_rub, 0);
          return (
            <div className="cost-structure-group" key={group.code}>
              <div className="cost-structure-head">
                <b>{group.label}</b>
                <span>{group.hint}</span>
                <strong>{money(total)} ₽</strong>
                <em>{(total / volume).toFixed(2)} ₽/м³</em>
              </div>
              {group.lines.map((line) => (
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
          );
        })}
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
        <span>{line.cost_item_name}</span>
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
