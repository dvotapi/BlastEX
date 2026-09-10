/**
 * Раздел «Персонал»: по строке на запись состава бригады (`params.crew`).
 * Должность выбирается из справочника, численность и смены на блок правит
 * сметчик; строки взносов, резерва и суточных, которых нет в составе
 * бригады напрямую, показываются под ними только для чтения.
 */
import { CatalogSelect, type CatalogOption } from "../estimate/CatalogSelect";
import { EstimateLine } from "../estimate/EstimateLine";
import { NumericInput } from "../NumericInput";
import { AddMenu } from "../estimate/AddMenu";
import { lineNumber } from "../estimateModel";
import { amount as formatAmount, money } from "../format";
import { crewOrigin } from "../origin";
import { lineByCode, lineShare } from "./lineHelpers";
import type { SectionEditorProps } from "./types";
import type { CrewMemberInput } from "../../../types/blockEconomics";

export function LaborSection({ group, params, defaults, economics, volume, canEdit, onChange }: SectionEditorProps) {
  // Должность выбирают только из прямых — косвенные (начальник участка и
  // т.п.) заложены в ОХР, а не в состав бригады блока.
  const directPositions = defaults.positions.filter((position) => position.category === "DIRECT");

  function update(index: number, patch: Partial<CrewMemberInput>) {
    onChange({ crew: params.crew.map((member, i) => (i === index ? { ...member, ...patch } : member)) });
  }

  function add() {
    // Та же логика, что была в `CrewEditor.add`: первая ещё не занятая
    // должность из каталога, а если все заняты — первая по списку.
    const used = new Set(params.crew.map((member) => member.position_code));
    const next = directPositions.find((position) => !used.has(position.code)) ?? directPositions[0];
    if (!next) return;
    onChange({ crew: [...params.crew, { position_code: next.code, headcount: 1, shifts_per_block: null }] });
  }

  function remove(index: number) {
    onChange({ crew: params.crew.filter((_, i) => i !== index) });
  }

  function resetToNorm(index: number, template: CrewMemberInput) {
    update(index, { position_code: template.position_code, headcount: template.headcount, shifts_per_block: null });
  }

  // Строки ФОТ, которых нет среди записей бригады напрямую (взносы, резерв,
  // суточные) — показываются под составом бригады только для чтения.
  const usedCodes = new Set(params.crew.map((member) => `LABOR_${member.position_code}`));
  const readOnlyLines = group.lines.filter((line) => !usedCodes.has(line.cost_item_code));

  return (
    <>
      {params.crew.map((member, index) => {
        const position = defaults.positions.find((item) => item.code === member.position_code);
        const options: CatalogOption[] = directPositions.map((item) => ({
          code: item.code,
          name: item.name,
          caption: `${money(item.fixed_monthly_rub, 0)} ₽/мес · ${item.norm_shifts_per_month} см/мес`,
        }));
        const template = defaults.parameters.crew.find((item) => item.position_code === member.position_code);
        const origin = crewOrigin(member, template);
        const line = lineByCode(group.lines, `LABOR_${member.position_code}`);
        const positionLabel = position?.name ?? member.position_code;

        return (
          <EstimateLine
            key={`${member.position_code}-${index}`}
            number={lineNumber(group, index)}
            name={
              <CatalogSelect
                id={`labor-position-${index}`}
                label="Должность"
                value={member.position_code}
                options={options}
                onChange={(code) => update(index, { position_code: code })}
                disabled={!canEdit}
              />
            }
            origin={origin}
            // Смены на блок своей колонки в смете не имеют: они видны серой
            // подписью под должностью, а правятся из меню строки.
            captions={[
              {
                label: "Смены на блок",
                value:
                  member.shifts_per_block === null || member.shifts_per_block === ""
                    ? "норматив"
                    : formatAmount(Number(member.shifts_per_block)),
                origin,
              },
            ]}
            quantity={Number(member.headcount)}
            quantityEditor={
              <NumericInput
                value={member.headcount}
                min={0}
                step={1}
                ariaLabel={`Численность: ${positionLabel}`}
                onChange={(value) => update(index, { headcount: value ?? "0" })}
              />
            }
            unit="чел."
            price={position?.fixed_monthly_rub ?? null}
            amount={line?.amount_rub ?? 0}
            volume={volume}
            share={line ? lineShare(line, economics) : 0}
            menuLabel={`Действия: ${positionLabel}`}
            editorMenuLabel="Смены на блок"
            editor={
              <label className="estimate-line-field">
                Смены на блок
                <NumericInput
                  value={member.shifts_per_block}
                  allowEmpty
                  min={0}
                  step={0.1}
                  placeholder="норматив"
                  ariaLabel={`Смен на блок: ${positionLabel}`}
                  onChange={(value) => update(index, { shifts_per_block: value })}
                />
              </label>
            }
            menuItems={
              canEdit
                ? [
                    ...(template
                      ? [{ label: "Сбросить к нормативу", onSelect: () => resetToNorm(index, template) }]
                      : []),
                    { label: "Убрать", onSelect: () => remove(index), danger: true },
                  ]
                : []
            }
          />
        );
      })}
      {canEdit && directPositions.length > 0 && (
        <div className="estimate-section-footer">
          <button type="button" className="row-add" onClick={add}>
            + Добавить должность
          </button>
        </div>
      )}
      {readOnlyLines.map((line, index) => (
        <EstimateLine
          key={line.cost_item_code}
          number={lineNumber(group, params.crew.length + index)}
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
    </>
  );
}
