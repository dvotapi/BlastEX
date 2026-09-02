import { FieldShell } from "./FieldShell";
import type { FieldDescriptor } from "../schemaFields";

export type RefOption = { code: string; name: string; is_active: boolean };

/**
 * Ссылка на запись другого раздела. Список берётся из текущего черновика,
 * поэтому только что заведённая запись сразу доступна для выбора.
 * Показываем активные записи; недействующая остаётся в списке, только если она
 * уже выбрана в этой записи — иначе выбор молча потерялся бы.
 */
export function RefSelect({
  field,
  value,
  options,
  onChange,
  disabled,
  error,
  sectionLabel,
}: {
  field: FieldDescriptor;
  value: string;
  options: RefOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
  error?: string;
  sectionLabel?: string;
}) {
  const visible = options.filter((option) => option.is_active || option.code === value);
  const selected = options.find((option) => option.code === value);
  const missing = value && !selected;

  return (
    <FieldShell
      field={field}
      error={error}
      hint={
        missing
          ? `Запись ${value} не найдена в разделе «${sectionLabel ?? field.ref}»`
          : undefined
      }
    >
      <div className="ref-select-wrap">
        {value && <span className="ref-code-tag">{value}</span>}
        <select
          id={`ref-field-${field.name}`}
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">{field.optional ? "не задано" : "— выберите —"}</option>
          {missing && <option value={value}>{value} — запись отсутствует</option>}
          {visible.map((option) => (
            <option key={option.code} value={option.code} className={option.is_active ? "" : "inactive-option"}>
              {option.name || option.code}
              {option.is_active ? "" : " (не действует)"}
            </option>
          ))}
        </select>
      </div>
    </FieldShell>
  );
}
