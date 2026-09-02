import type { ReactNode } from "react";
import type { FieldDescriptor } from "../schemaFields";

/** Общая обвязка поля формы: заголовок, подсказка и ошибка валидации под ним. */
export function FieldShell({
  field,
  error,
  hint,
  children,
}: {
  field: FieldDescriptor;
  error?: string;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className={`ref-field${error ? " has-error" : ""}`}>
      <label htmlFor={`ref-field-${field.name}`}>
        {field.title}
        {field.optional && <span className="ref-field-optional"> — необязательно</span>}
      </label>
      {children}
      {error ? (
        <p className="ref-field-error">{error}</p>
      ) : hint ? (
        <p className="ref-field-hint">{hint}</p>
      ) : field.description && field.description !== field.title ? (
        <p className="ref-field-hint">{field.description}</p>
      ) : null}
    </div>
  );
}
