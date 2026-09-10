/**
 * Раздел «Взрывчатые материалы»: по строке на роль номенклатуры (основное
 * ВВ, боевики, средства инициирования). Название выбирается из справочника
 * (`CatalogSelect`), количество и сумму считает модель по паспорту — кроме
 * электродетонаторов, которых паспорт не считает и сметчик задаёт вручную.
 */
import { useState } from "react";
import { NumericInput } from "../NumericInput";
import { AddMenu } from "../estimate/AddMenu";
import { CatalogSelect, type CatalogOption } from "../estimate/CatalogSelect";
import { EstimateLine } from "../estimate/EstimateLine";
import { lineNumber } from "../estimateModel";
import { NOMENCLATURE_ROLES, isRoleVisible, optionCaption, type NomenclatureRole } from "../nomenclature";
import { lineByCode, lineShare } from "./lineHelpers";
import type { SectionEditorProps } from "./types";

export function ExplosivesSection({ group, params, defaults, economics, volume, canEdit, onChange }: SectionEditorProps) {
  // Роль без позиции в паспорте (нулевое количество) не занимает строку
  // сметы сама по себе — сметчик добавляет её вручную кнопкой «+ Добавить
  // материал», если материал всё же нужен (паспорт устарел, замена ЭД и т.п.).
  const [addedRoles, setAddedRoles] = useState<Set<string>>(new Set());

  const passport = defaults.passport;
  const visibleRoles = NOMENCLATURE_ROLES.filter(
    (role) => isRoleVisible(role, passport) || addedRoles.has(role.role) || Boolean(params.nomenclature[role.role]),
  );
  const hiddenRoles = NOMENCLATURE_ROLES.filter((role) => !visibleRoles.includes(role));

  function selectMaterial(role: NomenclatureRole, code: string) {
    onChange({ nomenclature: { ...params.nomenclature, [role.role]: code } });
  }

  function removeRole(role: NomenclatureRole) {
    onChange({ nomenclature: { ...params.nomenclature, [role.role]: "" } });
    setAddedRoles((current) => {
      if (!current.has(role.role)) return current;
      const next = new Set(current);
      next.delete(role.role);
      return next;
    });
  }

  return (
    <>
      {visibleRoles.map((role, index) => {
        const options = defaults.nomenclature[role.role] ?? [];
        const selectedCode = params.nomenclature[role.role] ?? "";
        const selected = options.find((option) => option.code === selectedCode);
        const catalogOptions: CatalogOption[] = options.map((option) => ({
          code: option.code,
          name: option.name,
          caption: optionCaption(option, role, options.length),
          price: option.price_rub,
          unit: option.unit,
        }));
        // Количество приходит из строки модели, сопоставленной по коду статьи
        // затрат (`role.costItemCode`), а не по коду выбранного материала —
        // тот меняется от прогона к прогону. Подпись роли (`role.label`) для
        // сопоставления не годится: бэкендовый `line.role_label` — строка для
        // предупреждений (другой регистр, другие формулировки), не машинный
        // идентификатор.
        const line = lineByCode(group.lines, role.costItemCode);
        const isManualQuantity = role.driver === null;

        return (
          <EstimateLine
            key={role.role}
            number={lineNumber(group, index)}
            name={
              <CatalogSelect
                id={`explosive-${role.role}`}
                label={role.label}
                value={selectedCode}
                options={catalogOptions}
                onChange={(code) => selectMaterial(role, code)}
                disabled={!canEdit}
              />
            }
            origin={line?.quantity_origin ?? ""}
            quantity={line?.quantity ?? null}
            // Бейджа «Ручной» рядом с полем больше нет: происхождение
            // количества уже приходит от модели и стоит в колонке «Основание».
            quantityEditor={
              isManualQuantity ? (
                <NumericInput
                  value={params.electric_detonators_qty}
                  min={0}
                  step={1}
                  ariaLabel={`Количество: ${role.label}`}
                  disabled={!canEdit}
                  onChange={(value) => onChange({ electric_detonators_qty: value ?? "0" })}
                />
              ) : undefined
            }
            unit={line?.unit ?? selected?.unit ?? ""}
            price={line?.unit_price_rub ?? null}
            amount={line?.amount_rub ?? 0}
            volume={volume}
            share={line ? lineShare(line, economics) : 0}
            formula={line?.formula}
            menuLabel={`Действия: ${role.label}`}
            menuItems={canEdit ? [{ label: "Убрать", onSelect: () => removeRole(role), danger: true }] : []}
          />
        );
      })}
      {canEdit && hiddenRoles.length > 0 && (
        <div className="estimate-section-footer">
          <AddMenu
            label="Добавить материал"
            items={hiddenRoles.map((role) => ({
              code: role.role,
              label: role.label,
              onSelect: () => setAddedRoles((current) => new Set(current).add(role.role)),
            }))}
          />
        </div>
      )}
    </>
  );
}
