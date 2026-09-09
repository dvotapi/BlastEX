/**
 * Раздел «Взрывчатые материалы»: по строке на роль номенклатуры (основное
 * ВВ, боевики, средства инициирования). Название выбирается из справочника
 * (`CatalogSelect`), количество и сумму считает модель по паспорту — кроме
 * электродетонаторов, которых паспорт не считает и сметчик задаёт вручную.
 */
import { useState } from "react";
import { NumericInput } from "../NumericInput";
import { CatalogSelect, type CatalogOption } from "../estimate/CatalogSelect";
import { EstimateLine } from "../estimate/EstimateLine";
import { OriginBadge } from "../estimate/OriginBadge";
import { RowMenu } from "../estimate/RowMenu";
import { lineNumber } from "../estimateModel";
import { NOMENCLATURE_ROLES, isRoleVisible, optionCaption, type NomenclatureRole } from "../nomenclature";
import { lineByRoleLabel, lineShare } from "./lineHelpers";
import type { SectionEditorProps } from "./types";

export function ExplosivesSection({ group, params, defaults, economics, volume, canEdit, onChange }: SectionEditorProps) {
  // Роль без позиции в паспорте (нулевое количество) не занимает строку
  // сметы сама по себе — сметчик добавляет её вручную кнопкой «+ Добавить
  // материал», если материал всё же нужен (паспорт устарел, замена ЭД и т.п.).
  const [addedRoles, setAddedRoles] = useState<Set<string>>(new Set());
  const [addMenuOpen, setAddMenuOpen] = useState(false);

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
        // Количество приходит из строки модели, сопоставленной по роли, а не
        // по коду выбранного материала — код меняется от прогона к прогону,
        // а роль (`role_label`) нет. Та же идея, что у
        // `groupVariantsByLayerAndSection` в `estimateSections.ts`.
        const line = lineByRoleLabel(group.lines, role.label);
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
            quantity={isManualQuantity ? null : (line?.quantity ?? null)}
            unit={line?.unit ?? selected?.unit ?? ""}
            price={line?.unit_price_rub ?? null}
            amount={line?.amount_rub ?? 0}
            volume={volume}
            share={line ? lineShare(line, economics) : 0}
            formula={line?.formula}
            actions={
              <>
                {isManualQuantity && (
                  <span className="explosives-manual-qty">
                    <NumericInput
                      value={params.electric_detonators_qty}
                      min={0}
                      step={1}
                      ariaLabel={`Количество: ${role.label}`}
                      onChange={(value) => onChange({ electric_detonators_qty: value ?? "0" })}
                    />
                    <OriginBadge origin="MANUAL" />
                  </span>
                )}
                {canEdit && (
                  <RowMenu
                    items={[{ label: "Убрать", onSelect: () => removeRole(role), danger: true }]}
                    label={`Действия: ${role.label}`}
                  />
                )}
              </>
            }
          />
        );
      })}
      {canEdit && hiddenRoles.length > 0 && (
        <div className="row-menu explosives-add-role">
          <button type="button" className="row-add" onClick={() => setAddMenuOpen((open) => !open)}>
            + Добавить материал
          </button>
          {addMenuOpen && (
            <div className="row-menu-list" role="menu" aria-label="Добавить материал">
              {hiddenRoles.map((role) => (
                <button
                  key={role.role}
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setAddedRoles((current) => new Set(current).add(role.role));
                    setAddMenuOpen(false);
                  }}
                >
                  {role.label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </>
  );
}
