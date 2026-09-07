import { NumericInput } from "./NumericInput";
import {
  NOMENCLATURE_ROLES,
  isRoleVisible,
  optionCaption,
  roleQuantity,
  unitLabel,
} from "./nomenclature";
import type { ModelDefaults, ModelParameters } from "../../types/blockEconomics";

/**
 * Выбор наименований ВМ и средств инициирования.
 *
 * Количества здесь не вводятся: их посчитал технический паспорт. Сметчик
 * выбирает наименование, цену подставляет справочник.
 */
export function NomenclaturePanel({
  params,
  defaults,
  onChange,
}: {
  params: ModelParameters;
  defaults: ModelDefaults;
  onChange: (patch: Partial<ModelParameters>) => void;
}) {
  const passport = defaults.passport;
  const visible = NOMENCLATURE_ROLES.filter((role) => isRoleVisible(role, passport));

  return (
    <section className="panel block-economics-nomenclature">
      <header>
        <b>Номенклатура блока</b>
        <span>цены из справочника</span>
      </header>
      <div className="panel-body">
        {visible.map((role) => {
          const options = defaults.nomenclature[role.role] ?? [];
          const selectedCode = params.nomenclature[role.role] ?? "";
          const selected = options.find((option) => option.code === selectedCode);
          const quantity = roleQuantity(role, passport);
          return (
            <label key={role.role}>
              {role.label}
              <select
                value={selectedCode}
                onChange={(event) =>
                  onChange({
                    nomenclature: { ...params.nomenclature, [role.role]: event.target.value },
                  })
                }
              >
                <option value="">не выбрано</option>
                {options.map((option) => (
                  <option key={option.code} value={option.code}>
                    {option.name}
                  </option>
                ))}
              </select>
              <small>
                {optionCaption(selected, role, options.length)}
                {quantity !== null && selected
                  ? ` · ${quantity.toLocaleString("ru-RU", { maximumFractionDigits: 2 })} ${unitLabel(selected.unit)} на блок`
                  : ""}
              </small>
            </label>
          );
        })}
        <label>
          Электродетонаторов на блок, шт
          <NumericInput
            value={params.electric_detonators_qty}
            min={0}
            step={1}
            onChange={(value) => onChange({ electric_detonators_qty: value ?? "0" })}
          />
        </label>
      </div>
    </section>
  );
}
