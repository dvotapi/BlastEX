import { FieldShell } from "./FieldShell";
import { enumLabel } from "../enumLabels";
import type { FieldDescriptor } from "../schemaFields";

/** До трёх значений — сегменты (видно всё сразу), дальше — обычный селект. */
export function EnumSegment({
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
  const options = field.options;
  const asSegments = options.length <= 3 && !field.optional;

  return (
    <FieldShell field={field} error={error}>
      {asSegments ? (
        <div className="ref-segments" role="group" aria-label={field.title}>
          {options.map((option) => (
            <button
              key={option}
              type="button"
              className={option === value ? "active" : ""}
              disabled={disabled}
              onClick={() => onChange(option)}
            >
              {enumLabel(option)}
            </button>
          ))}
        </div>
      ) : (
        <select
          id={`ref-field-${field.name}`}
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">{field.optional ? "не задано" : "— выберите —"}</option>
          {options.map((option) => (
            <option key={option} value={option}>
              {enumLabel(option)}
            </option>
          ))}
        </select>
      )}
    </FieldShell>
  );
}
