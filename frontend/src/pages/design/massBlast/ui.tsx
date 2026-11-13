// Общие элементы окна проекта МВ: поле с подписью, подсказкой источника,
// ошибкой ввода и замечаниями проверки; открытие PDF и скачивание.
import { useId, useState, type ReactNode } from "react";
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

/** Значение по умолчанию поля (сервер): что подставится в пустое поле и откуда (§14, В1). */
export type AutoValue = { value: unknown; source: string };

/** «Запомнить для объекта» (В8): галочка у поля объекта. */
export type RememberControl = { checked: boolean; onChange: (checked: boolean) => void };

export const SOURCE_LABELS: Record<string, string> = {
  REFERENCE: "справочник объекта",
  DESIGN: "проект блока",
  SURVEY: "съёмка блока",
  DRILL_PASSPORT: "паспорт на бурение",
  PREVIOUS: "прошлый проект",
  RULE: "правило",
  PROJECT: "проект МВ",
};

/** Текст значения по умолчанию для поля ввода: число — с запятой. */
export function autoText(auto: AutoValue | undefined): string {
  if (!auto || auto.value === null || auto.value === undefined) return "";
  return typeof auto.value === "number" ? String(auto.value).replace(".", ",") : String(auto.value);
}

export function Field({
  label,
  hint,
  error,
  issues = [],
  wide = false,
  auto,
  own,
  onReset,
  remember,
  disabled = false,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  issues?: MassBlastIssue[];
  wide?: boolean;
  /** Значение по умолчанию и что введено в поле: пометка источника и «↺». */
  auto?: AutoValue;
  own?: string;
  onReset?: () => void;
  remember?: RememberControl | null;
  /** Поле недоступно: «↺» и «Запомнить» тоже. */
  disabled?: boolean;
  children: (id: string) => ReactNode;
}) {
  const id = useId();
  const autoValue = autoText(auto);
  const usesAuto = Boolean(autoValue) && !(own ?? "").trim();
  const differs = Boolean(autoValue) && Boolean((own ?? "").trim()) && (own ?? "").trim() !== autoValue;
  return (
    <div className={`drill-field${wide ? " wide" : ""}${usesAuto ? " mb-auto" : ""}`}>
      <label htmlFor={id}>{label}</label>
      {children(id)}
      {usesAuto && auto && <small className="drill-source">{SOURCE_LABELS[auto.source] ?? "автоматически"}</small>}
      {differs && auto && onReset && (
        <button type="button" className="link-button mb-reset" onClick={onReset} disabled={disabled}
          title={`Вернуть «${autoValue}» (${SOURCE_LABELS[auto.source] ?? "автоматически"})`}>
          ↺ {SOURCE_LABELS[auto.source] ?? "автоматически"}: {autoValue.length > 40 ? `${autoValue.slice(0, 40)}…` : autoValue}
        </button>
      )}
      {remember && (
        <label className="drill-ack mb-remember">
          <input type="checkbox" checked={remember.checked} disabled={disabled} onChange={(event) => remember.onChange(event.target.checked)} />
          Запомнить для объекта
        </label>
      )}
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
  auto,
  remember,
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
  /** В1: пустое поле показывает значение по умолчанию; правка делает его своим. */
  auto?: AutoValue;
  remember?: RememberControl | null;
}) {
  // Стёртое значение остаётся пустым, пока поле в фокусе: иначе, чтобы ввести своё,
  // нельзя было бы очистить поле — значение по умолчанию тут же возвращалось бы.
  const [cleared, setCleared] = useState(false);
  const shown = value !== "" || cleared ? value : autoText(auto);
  const change = (next: string) => {
    setCleared(next === "");
    onChange(next);
  };
  const blur = () => setCleared(false);
  return (
    <Field label={label} hint={hint} error={error} issues={issues} wide={wide || multiline} auto={auto} own={value}
      onReset={() => onChange("")} remember={remember} disabled={disabled}>
      {(id) =>
        multiline ? (
          <textarea id={id} rows={2} value={shown} maxLength={maxLength} placeholder={placeholder} disabled={disabled}
            onBlur={blur} onChange={(event) => change(event.target.value)} />
        ) : (
          <input
            id={id}
            type={type}
            value={shown}
            maxLength={maxLength}
            inputMode={inputMode}
            placeholder={placeholder}
            disabled={disabled}
            onBlur={blur}
            onChange={(event) => change(event.target.value)}
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

/**
 * PDF в новой вкладке. Вкладка открывается сразу, в обработчике щелчка (после
 * `await` браузер заблокировал бы её как всплывающее окно); адрес — когда
 * `url()` сохранит правки и вернёт адрес документа. `null` — вкладка закрывается.
 */
export async function openPdf(url: () => Promise<string | null>): Promise<void> {
  const tab = window.open("", "_blank");
  try {
    const target = await url();
    if (!target) {
      tab?.close();
      return;
    }
    const blob = await fetchBlob(target);
    const href = URL.createObjectURL(blob);
    if (tab) tab.location.href = href;
    else if (!window.open(href, "_blank")) {
      URL.revokeObjectURL(href);
      throw new Error("Браузер не дал открыть вкладку с PDF: разрешите всплывающие окна для BlastEX.");
    }
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
