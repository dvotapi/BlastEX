import { FieldShell } from "./FieldShell";
import type { FieldDescriptor } from "../schemaFields";

export function DateField({
  field,
  value,
  onChange,
  disabled,
  error,
}: {
  field: FieldDescriptor;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  error?: string;
}) {
  return (
    <FieldShell field={field} error={error}>
      <input
        id={`ref-field-${field.name}`}
        type="date"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      />
    </FieldShell>
  );
}
