import { FieldShell } from "./FieldShell";
import type { FieldDescriptor } from "../schemaFields";

export function BoolField({
  field,
  value,
  onChange,
  disabled,
  error,
}: {
  field: FieldDescriptor;
  value: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
  error?: string;
}) {
  return (
    <FieldShell field={field} error={error}>
      <label className="ref-checkbox">
        <input
          id={`ref-field-${field.name}`}
          type="checkbox"
          checked={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span>{value ? "да" : "нет"}</span>
      </label>
    </FieldShell>
  );
}
