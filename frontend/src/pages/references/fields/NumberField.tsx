import { FieldShell } from "./FieldShell";
import { formatNumber, isRubleField, parseNumber, withoutVat, type FieldDescriptor } from "../schemaFields";

/**
 * Число с единицей измерения. Единица показана внутри поля, поэтому её не
 * приходится дописывать в заголовок и нельзя перепутать ₽/см и ₽/мес.
 */
export function NumberField({
  field,
  value,
  onChange,
  disabled,
  error,
  vatMode,
  vatRate,
}: {
  field: FieldDescriptor;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  error?: string;
  vatMode?: boolean;
  vatRate?: number;
}) {
  const parsed = parseNumber(value);
  const showsVat = Boolean(vatMode) && isRubleField(field) && parsed !== null;
  const hint = showsVat
    ? `Будет сохранено без НДС: ${formatNumber(withoutVat(parsed as number, vatRate ?? 0))} ${field.unit}`
    : undefined;

  return (
    <FieldShell field={field} error={error} hint={hint}>
      <div className="ref-input-wrap">
        <input
          id={`ref-field-${field.name}`}
          inputMode="decimal"
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          placeholder={field.optional ? "не задано" : ""}
        />
        {field.unit && <span className="ref-input-unit">{field.unit}</span>}
      </div>
    </FieldShell>
  );
}
