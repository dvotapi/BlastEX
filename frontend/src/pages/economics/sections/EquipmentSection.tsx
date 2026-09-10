/**
 * Раздел «Техника и оборудование»: четыре роли техники блока — буровая
 * установка, СЗМ, доставщик ВМ, тягач эмульсии. У каждой роли — выбор из
 * справочника, смены на блок (считает модель) и плановые смены в месяц
 * (правит сметчик, от них зависит доля постоянных затрат техники на смену).
 * Под строкой роли — её статьи только для чтения (амортизация, ТОиР,
 * страхование), найденные по общему префиксу кода статьи. Исключение —
 * станок: его статьи владения уже показаны построчно в разделе «Бурение»
 * (у них `section === "DRILLING"`), поэтому здесь у роли «Буровая
 * установка» только итоговая сумма/доля и сноска со ссылкой на «Бурение»,
 * без повторной построчной разбивки.
 */
import { useState } from "react";
import { AddMenu } from "../estimate/AddMenu";
import { CatalogSelect, type CatalogOption } from "../estimate/CatalogSelect";
import { EstimateLine, type EstimateLineCaption } from "../estimate/EstimateLine";
import { NumericInput } from "../NumericInput";
import { lineNumber } from "../estimateModel";
import { amount as formatAmount, money } from "../format";
import { linesByPrefix, lineShare } from "./lineHelpers";
import type { SectionEditorProps } from "./types";
import type { CodeName, ModelParameters, ValueOrigin } from "../../../types/blockEconomics";

/**
 * Статьи станка, относящиеся к владению им (а не к работе метром) — все
 * имеют `section === "DRILLING"` (`cost/model/drilling.py`), поэтому найти
 * их по префиксу и разделу «Техника» разом нельзя: ищем по всему расчёту и
 * отбираем именно эти коды, а не весь префикс `DRILL_` (см. `EquipmentSection`).
 */
const RIG_OWNERSHIP_ITEM_CODES = new Set(["DRILL_DEPRECIATION", "DRILL_INSURANCE", "DRILL_MAINTENANCE"]);

type EquipmentRoleKey = "rig_code" | "szm_code" | "delivery_truck_code" | "emulsion_truck_code";

type EquipmentRole = {
  param: EquipmentRoleKey;
  label: string;
  options: CodeName[];
  /** Ключ в `natural.values`/`natural.lineage` — смены на блок из расчёта модели. */
  shiftsKey: string;
  /** Префикс кода статьи, по которому находятся все статьи этой машины. */
  prefix: string;
};

export type EquipmentSectionProps = SectionEditorProps & {
  /** Раскрыть раздел «Бурение»: там учтены деньги строки станка. */
  onOpenDrillingGroup?: () => void;
};

function equipmentRoles(defaults: SectionEditorProps["defaults"]): EquipmentRole[] {
  return [
    { param: "rig_code", label: "Буровая установка", options: defaults.rigs, shiftsKey: "rig_shifts", prefix: "DRILL_" },
    { param: "szm_code", label: "СЗМ", options: defaults.szm, shiftsKey: "szm_shifts", prefix: "SZM_" },
    {
      param: "delivery_truck_code",
      label: "Доставщик ВМ",
      options: defaults.delivery_trucks,
      shiftsKey: "delivery_shifts",
      prefix: "VM_TRUCK_",
    },
    {
      param: "emulsion_truck_code",
      label: "Тягач эмульсии",
      options: defaults.emulsion_trucks,
      shiftsKey: "emulsion_shifts",
      prefix: "EMULSION_TRUCK_",
    },
  ];
}

export function EquipmentSection({
  group,
  params,
  defaults,
  economics,
  volume,
  canEdit,
  onChange,
  onOpenDrillingGroup,
}: EquipmentSectionProps) {
  // Роль без выбранной техники не занимает строку сметы сама по себе —
  // сметчик добавляет её кнопкой «+ Добавить технику», как и материалы ВМ.
  const [addedRoles, setAddedRoles] = useState<Set<EquipmentRoleKey>>(new Set());

  const roles = equipmentRoles(defaults);
  const visibleRoles = roles.filter((role) => Boolean(params[role.param]) || addedRoles.has(role.param));
  const hiddenRoles = roles.filter((role) => !visibleRoles.includes(role));

  function setCode(role: EquipmentRole, value: string) {
    onChange({ [role.param]: value || null } as Partial<ModelParameters>);
  }

  // Плановые смены станка живут в своём поле `rig_plan_shifts`, у остальных
  // трёх ролей — в общей карте `machine_plan_shifts` по коду техники.
  function setPlanShifts(role: EquipmentRole, code: string | null, value: string | null) {
    if (role.param === "rig_code") {
      onChange({ rig_plan_shifts: value });
      return;
    }
    if (!code) return;
    const next = { ...params.machine_plan_shifts };
    if (value === null || value === "") delete next[code];
    else next[code] = value;
    onChange({ machine_plan_shifts: next });
  }

  function removeRole(role: EquipmentRole) {
    onChange({ [role.param]: null } as Partial<ModelParameters>);
    setAddedRoles((current) => {
      if (!current.has(role.param)) return current;
      const next = new Set(current);
      next.delete(role.param);
      return next;
    });
  }

  let rowIndex = 0;

  return (
    <>
      {visibleRoles.map((role) => {
        const code = params[role.param] as string | null;
        const catalogOptions: CatalogOption[] = role.options.map((item) => ({ code: item.code, name: item.name }));
        const shiftsValue = economics?.natural.values[role.shiftsKey];
        const shiftsTitle = economics?.natural.lineage[role.shiftsKey];
        const planRaw = role.param === "rig_code" ? params.rig_plan_shifts : code ? (params.machine_plan_shifts[code] ?? null) : null;
        const planOrigin: ValueOrigin = planRaw === null || planRaw === undefined || planRaw === "" ? "NORM" : "MANUAL";
        // Статьи станка (`DRILL_*`) все имеют `section === "DRILLING"` (см.
        // `cost/model/drilling.py`), поэтому `groupOf` относит их в раздел
        // «Бурение», а не «Техника» — `group.lines` этого раздела их никогда
        // не содержит. Ищем их во всём расчёте, тем же приёмом, каким чуть
        // ниже ищется `DRILL_UNALLOCATED_FIXED` при субподряде, но не по
        // всему префиксу: `DRILL_TOOLING`/`DRILL_FUEL`/`DRILL_SPARE_PARTS`/
        // `DRILL_INSPECTION` — переменные затраты бурения метром, они уже
        // показаны в разделе «Бурение» (`OwnDrillingEditor`) и не относятся
        // к владению станком; `DRILL_SUBCONTRACT`/`DRILL_UNALLOCATED_FIXED`
        // тоже начинаются с `DRILL_`, но показаны в другом месте: первая —
        // главной строкой раздела «Бурение» (`SubcontractDrillingEditor`),
        // вторая — отдельной сноской чуть ниже (`unallocated`). Здесь — как
        // и у остальных трёх ролей — только статьи владения станком:
        // амортизация, страхование, ТОиР. Сумма этих статей идёт в строку
        // роли (`amount`/`share` ниже), но построчно они здесь больше не
        // выводятся — `OwnDrillingEditor` уже показывает их построчно в
        // разделе «Бурение» (те же статьи входят в `group.lines` раздела
        // «Бурение» через `otherLines`), и построчный дубль в «Технике»
        // вводил сметчика в заблуждение (одна и та же сумма амортизации на
        // двух страницах). Для остальных трёх ролей дубля нет — их статьи
        // существуют только в разделе «Техника».
        const items =
          role.param === "rig_code"
            ? linesByPrefix(economics?.lines ?? [], role.prefix).filter((item) =>
                RIG_OWNERSHIP_ITEM_CODES.has(item.cost_item_code),
              )
            : linesByPrefix(group.lines, role.prefix);
        const total = items.reduce((sum, line) => sum + line.amount_rub, 0);
        const share = items.reduce((sum, line) => sum + lineShare(line, economics), 0);
        // Станок при субподряде бурения не работает на блок — его постоянные
        // затраты не распределены и живут отдельной строкой в другом разделе
        // (`DRILL_UNALLOCATED_FIXED`), поэтому ищем её во всём расчёте, а не
        // в строках этого раздела.
        const unallocated =
          role.param === "rig_code" && params.drilling_executor === "SUBCONTRACTOR"
            ? economics?.lines.find((line) => line.cost_item_code === "DRILL_UNALLOCATED_FIXED")
            : undefined;

        const number = lineNumber(group, rowIndex);
        rowIndex += 1;

        // Деньги станка учтены в разделе «Бурение» — здесь у его строки нет
        // ни суммы, ни доли. Иначе итог раздела не сходился с суммой видимых
        // строк, а колонка процентов дважды считала одни и те же рубли.
        const isRig = role.param === "rig_code";
        const captions: EstimateLineCaption[] = [];
        if (shiftsValue !== undefined) {
          captions.push({
            label: "Смены на блок",
            value: formatAmount(Number(shiftsValue)),
            origin: "CALC",
            originLabel: "Расчёт",
            originTitle: shiftsTitle,
          });
        }
        captions.push({
          label: "Плановые смены в месяц",
          value: planRaw === null || planRaw === undefined || planRaw === "" ? "норматив" : formatAmount(Number(planRaw)),
          origin: planOrigin,
        });
        if (isRig && items.length > 0) {
          captions.push({
            label: "Затраты станка",
            value: `${money(total, 0)} ₽ — в разделе «Бурение»`,
            onClick: onOpenDrillingGroup,
          });
        }
        if (unallocated) {
          captions.push({
            label: "При субподряде",
            value: `${money(unallocated.amount_rub, 0)} ₽ постоянных затрат станка не распределены на блок`,
          });
        }

        return (
          <div className="equipment-role" key={role.param}>
            <EstimateLine
              number={number}
              name={
                <CatalogSelect
                  id={`equipment-${role.param}`}
                  label={role.label}
                  value={code ?? ""}
                  options={catalogOptions}
                  onChange={(value) => setCode(role, value)}
                  disabled={!canEdit}
                />
              }
              captions={captions}
              origin=""
              quantity={null}
              unit=""
              price={null}
              amount={isRig ? null : total}
              volume={volume}
              share={isRig ? null : share}
              menuLabel={`Действия: ${role.label}`}
              editorMenuLabel="Плановые смены в месяц"
              editor={
                <label className="estimate-line-field">
                  Плановые смены в месяц
                  <NumericInput
                    value={planRaw}
                    allowEmpty
                    min={0}
                    step={1}
                    placeholder="норматив"
                    ariaLabel={`Плановые смены: ${role.label}`}
                    onChange={(value) => setPlanShifts(role, code, value)}
                  />
                </label>
              }
              menuItems={canEdit ? [{ label: "Убрать", onSelect: () => removeRole(role), danger: true }] : []}
            />
            {!isRig &&
              items.map((line, index) => (
                <EstimateLine
                  key={line.cost_item_code}
                  number={`${number}.${index + 1}`}
                  name={line.cost_item_name}
                  origin={line.price_origin || line.quantity_origin}
                  quantity={line.quantity}
                  unit={line.unit}
                  price={line.unit_price_rub}
                  amount={line.amount_rub}
                  volume={volume}
                  share={lineShare(line, economics)}
                />
              ))}
          </div>
        );
      })}
      {canEdit && (
        <div className="estimate-section-footer">
          <AddMenu
            label="Добавить технику"
            items={hiddenRoles.map((role) => ({
              code: role.param,
              label: role.label,
              onSelect: () => setAddedRoles((current) => new Set(current).add(role.param)),
            }))}
          />
        </div>
      )}
    </>
  );
}
