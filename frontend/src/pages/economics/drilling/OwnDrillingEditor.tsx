/**
 * Бурение собственными силами: станок из справочника, объём — из паспорта,
 * стоимость метра — расчёт модели по условиям блока (станок + порода).
 * Разложение метра открывается рядом, не уводя со страницы; отдельный
 * калькулятор Cost V1 («Бурение») открывается по своей ссылке — числа между
 * ними не переносятся (см. «Решения и допущения», п. 1).
 */
import { useState, type ReactNode } from "react";
import type { ModelDefaults, ModelParameters, Numeric, ValueOrigin } from "../../../types/blockEconomics";
import { CatalogSelect, type CatalogOption } from "../estimate/CatalogSelect";
import { EstimateLine } from "../estimate/EstimateLine";
import { lineNumber } from "../estimateModel";
import { amount as formatAmount, money } from "../format";
import { lineShare } from "../sections/lineHelpers";
import type { SectionEditorProps } from "../sections/types";
import { DrillingCard, type DrillingFact } from "./DrillingCard";
import { DrillingDrawer } from "./DrillingDrawer";
import { RigPlanShiftsSlider } from "./RigPlanShiftsSlider";

/**
 * Смена станка: экипаж бурения зависит от класса станка, поэтому должности
 * станко-зависимой части состава (`defaults.rig_crews`) заменяются составом
 * нового станка; остальная бригада блока не меняется.
 */
export function rigChangePatch(
  params: ModelParameters,
  defaults: ModelDefaults,
  rigCode: string | null,
): Partial<ModelParameters> {
  const rigCrews = defaults.rig_crews ?? {};
  const rigPositions = new Set(Object.values(rigCrews).flatMap((members) => members.map((member) => member.position_code)));
  if (rigPositions.size === 0) return { rig_code: rigCode };
  const kept = params.crew.filter((member) => !rigPositions.has(member.position_code));
  const added = (rigCode ? rigCrews[rigCode] ?? [] : []).map((member) => ({ ...member, shifts_per_block: member.shifts_per_block ?? null }));
  return { rig_code: rigCode, crew: [...kept, ...added] };
}

export type OwnDrillingEditorProps = SectionEditorProps & {
  /** Открыть страницу «Бурение» (зарплата экипажа, стоимость метра). */
  onOpenDrillingPage: () => void;
  /** Переключатель «Исполнение» — рисует `DrillingSection`, показывает карточка. */
  executor: ReactNode;
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
  executor,
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

  const facts: DrillingFact[] = [
    {
      label: "Объём бурения",
      value: drillingM === null ? "—" : `${formatAmount(Number(drillingM))} п.м.`,
      origin: "PASSPORT",
      originLabel: "Из паспорта",
    },
    {
      label: "Стоимость 1 п.м.",
      value: rubPerM === undefined ? "—" : `${money(Number(rubPerM))} ₽/м`,
      origin: "CALC",
      originLabel: "Из расчёта бурения",
      originTitle: conditionTitle,
    },
    {
      // Загрузка станка: постоянные затраты станка делятся на плановые смены,
      // поэтому бегунок рядом со стоимостью метра — метр меняется на глазах.
      label: "Плановые смены станка",
      editor: (
        <RigPlanShiftsSlider
          value={params.rig_plan_shifts}
          norm={defaults.parameters.rig_plan_shifts}
          disabled={!canEdit}
          onChange={(value) => onChange({ rig_plan_shifts: value })}
        />
      ),
      origin: rigPlanOrigin,
    },
  ];

  return (
    <>
      <DrillingCard
        executor={executor}
        machine={
          <label className="drilling-card-field">
            Буровая установка
            <CatalogSelect
              id="drilling-rig"
              label="Буровая установка"
              value={params.rig_code ?? ""}
              options={rigOptions}
              onChange={(code) => onChange(rigChangePatch(params, defaults, code || null))}
              disabled={!canEdit}
              variant="field"
            />
          </label>
        }
        facts={facts}
        amount={group.total}
        volume={volume}
        action={
          <button type="button" className="secondary-button" onClick={() => setDrawerOpen(true)}>
            Открыть расчёт бурения →
          </button>
        }
        footer={
          <button type="button" className="link-button" onClick={onOpenDrillingPage}>
            Перейти к расчёту бурения (Бурение) →
          </button>
        }
      />
      {otherLines.map((line, index) => (
        <EstimateLine
          key={line.cost_item_code}
          number={lineNumber(group, index)}
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
