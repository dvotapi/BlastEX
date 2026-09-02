import { FieldShell } from "./FieldShell";
import type { FieldDescriptor } from "../schemaFields";

export function TextField({
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
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        placeholder={field.optional ? "не задано" : ""}
      />
    </FieldShell>
  );
}
