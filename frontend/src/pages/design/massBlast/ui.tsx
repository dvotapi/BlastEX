// Общие элементы окна проекта МВ: поле с подписью, подсказкой источника,
// ошибкой ввода и замечаниями проверки; открытие PDF и скачивание.
import { useId, type ReactNode } from "react";
import { downloadFile, fetchBlob } from "../../../api/client";
import type { MassBlastIssue } from "../../../types/massBlast";

export function errorText(reason: unknown, fallback: string): string {
  return reason instanceof Error && reason.message ? reason.message : fallback;
}

export function Issues({ issues }: { issues: MassBlastIssue[] }) {
  if (!issues.length) return null;
  return (
    <>
      {issues.map((issue, index) => (
        <small key={`${issue.code}:${index}`} className={issue.level === "error" ? "form-error" : "frag-warnings"}>
          {issue.message}
        </small>
      ))}
    </>
  );
}

export function Field({
  label,
  hint,
  error,
  issues = [],
  wide = false,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  issues?: MassBlastIssue[];
  wide?: boolean;
  children: (id: string) => ReactNode;
}) {
  const id = useId();
  return (
    <div className={`drill-field${wide ? " wide" : ""}`}>
      <label htmlFor={id}>{label}</label>
      {children(id)}
      {hint && <small className="drill-hint">{hint}</small>}
      {error && <small className="form-error">{error}</small>}
      <Issues issues={issues} />
    </div>
  );
}

export function TextInput({
  label,
  value,
  onChange,
  disabled,
  hint,
  error,
  issues,
  wide,
  placeholder,
  type = "text",
  multiline = false,
  maxLength,
  inputMode,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
  hint?: string;
  error?: string;
  issues?: MassBlastIssue[];
  wide?: boolean;
  placeholder?: string;
  type?: "text" | "date" | "time";
  multiline?: boolean;
  maxLength?: number;
  inputMode?: "decimal";
}) {
  return (
    <Field label={label} hint={hint} error={error} issues={issues} wide={wide || multiline}>
      {(id) =>
        multiline ? (
          <textarea id={id} rows={2} value={value} maxLength={maxLength} placeholder={placeholder} disabled={disabled} onChange={(event) => onChange(event.target.value)} />
        ) : (
          <input
            id={id}
            type={type}
            value={value}
            maxLength={maxLength}
            inputMode={inputMode}
            placeholder={placeholder}
            disabled={disabled}
            onChange={(event) => onChange(event.target.value)}
          />
        )
      }
    </Field>
  );
}

/** Подсказка пустого поля: значение, которое подставит расчёт, и откуда оно. */
export function fromReference(own: string, computed: unknown, source = "из справочника объекта"): string | undefined {
  if (own.trim()) return undefined;
  const value = computed === null || computed === undefined ? "" : String(computed).trim();
  return value ? `${source}: ${value}` : undefined;
}

/** PDF в новой вкладке. Вкладка открывается сразу (иначе браузер её заблокирует), адрес — после ответа. */
export async function openPdf(url: string): Promise<void> {
  const tab = window.open("", "_blank");
  try {
    const blob = await fetchBlob(url);
    const href = URL.createObjectURL(blob);
    if (tab) tab.location.href = href;
    else window.open(href, "_blank");
    window.setTimeout(() => URL.revokeObjectURL(href), 60_000);
  } catch (reason) {
    tab?.close();
    throw reason;
  }
}

export async function download(url: string, fallback: string): Promise<string | null> {
  const { warning } = await downloadFile(url, fallback);
  return warning;
}

export function ruNum(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return Number(value.toFixed(digits)).toLocaleString("ru-RU", { maximumFractionDigits: digits });
}
