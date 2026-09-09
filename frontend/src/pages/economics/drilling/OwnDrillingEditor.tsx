/**
 * Бурение собственными силами: станок из справочника, объём — из паспорта,
 * стоимость метра — расчёт модели по условиям блока (станок + порода).
 * Разложение метра открывается рядом, не уводя со страницы; отдельный
 * калькулятор Cost V1 («Бурение») открывается по своей ссылке — числа между
 * ними не переносятся (см. «Решения и допущения», п. 1).
 */
import { useState } from "react";
import type { Numeric, ValueOrigin } from "../../../types/blockEconomics";
import { CatalogSelect, type CatalogOption } from "../estimate/CatalogSelect";
import { EstimateLine } from "../estimate/EstimateLine";
import { NumericInput } from "../NumericInput";
import { OriginBadge } from "../estimate/OriginBadge";
import { lineNumber } from "../estimateModel";
import { amount as formatAmount, money } from "../format";
import { lineShare } from "../sections/lineHelpers";
import type { SectionEditorProps } from "../sections/types";
import { DrillingDrawer } from "./DrillingDrawer";

export type OwnDrillingEditorProps = SectionEditorProps & {
  /** Открыть отдельный калькулятор бурения (Cost V1, вкладка «Бурение»). */
  onOpenDrillingPage: () => void;
};

function sameNumeric(a: Numeric | null | undefined, b: Numeric | null | undefined): boolean {
  const na = a === null || a === undefined || a === "" ? null : String(a);
  const nb = b === null || b === undefined || b === "" ? null : String(b);
  return na === nb;
}

export function OwnDrillingEditor({
  group,
  params,
  defaults,
  economics,
  volume,
  canEdit,
  onChange,
  onOpenDrillingPage,
}: OwnDrillingEditorProps) {
  const [drawerOpen, setDrawerOpen] = useState(false);

  const rigOptions: CatalogOption[] = defaults.rigs.map((rig) => ({ code: rig.code, name: rig.name }));
  const drillingM = defaults.passport.physical.drilling_m ?? null;
  const rubPerM = economics?.natural.values.drilling_rub_per_m;
  const conditionTitle = economics?.natural.lineage.drilling_condition;

  // Норматив плановых смен станка — тот же, что заведён в шаблоне пакета:
  // совпадает с ним — «Норматив», сметчик поправил — «Ручной».
  const rigPlanOrigin: ValueOrigin = sameNumeric(params.rig_plan_shifts, defaults.parameters.rig_plan_shifts)
    ? "NORM"
    : "MANUAL";

  const otherLines = group.lines.filter((line) => line.cost_item_code !== "DRILL_SUBCONTRACT");

  return (
    <>
      <EstimateLine
        number={lineNumber(group, 0)}
        name={
          <CatalogSelect
            id="drilling-rig"
            label="Буровая установка"
            value={params.rig_code ?? ""}
            options={rigOptions}
            onChange={(code) => onChange({ rig_code: code || null })}
            disabled={!canEdit}
          />
        }
        origin=""
        quantity={null}
        unit=""
        price={null}
        amount={group.total}
        volume={volume}
        share={group.share}
        actions={
          <>
            <span className="drilling-volume">
              Объём бурения: {drillingM === null ? "—" : formatAmount(Number(drillingM))} м
              <OriginBadge origin="PASSPORT" />
            </span>
            {rubPerM !== undefined && (
              <span className="drilling-rate">
                Стоимость метра: {money(Number(rubPerM))} ₽/м
                <OriginBadge origin="CALC" label="Расчёт бурения" title={conditionTitle} />
              </span>
            )}
            <label className="drilling-plan-shifts">
              Плановые смены станка
              <NumericInput
                value={params.rig_plan_shifts}
                allowEmpty
                min={0}
                step={1}
                placeholder="норматив"
                ariaLabel="Плановые смены станка"
                onChange={(value) => onChange({ rig_plan_shifts: value })}
              />
              <OriginBadge origin={rigPlanOrigin} />
            </label>
          </>
        }
      />
      <p className="drilling-links">
        <button type="button" className="link-button" onClick={() => setDrawerOpen(true)}>
          Открыть расчёт бурения →
        </button>
        <button type="button" className="link-button" onClick={onOpenDrillingPage}>
          Перейти к расчёту бурения (Бурение) →
        </button>
      </p>
      {otherLines.map((line, index) => (
        <EstimateLine
          key={line.cost_item_code}
          number={`${lineNumber(group, 0)}.${index + 1}`}
          name={line.cost_item_name}
          origin={line.price_origin || line.quantity_origin}
          quantity={line.quantity}
          unit={line.unit}
          price={line.unit_price_rub}
          amount={line.amount_rub}
          volume={volume}
          share={lineShare(line, economics)}
          formula={line.formula}
        />
      ))}
      {drawerOpen && economics && <DrillingDrawer economics={economics} onClose={() => setDrawerOpen(false)} />}
    </>
  );
}
