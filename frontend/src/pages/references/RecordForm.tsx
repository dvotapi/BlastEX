import { useEffect, useMemo, useState } from "react";
import type { ReferenceSectionSchema } from "../../types/referenceSchema";
import type { EconomicsReferenceItem, ReferenceValidationIssue } from "../../types/economics";
import { derivedHints, type DerivedContext } from "../../lib/referenceDerived";
import {
  formFieldsets,
  isRubleField,
  parseNumber,
  sectionFields,
  toFormValues,
  toPayload,
  withoutVat,
  type FieldDescriptor,
  type FormValues,
} from "./schemaFields";
import { BoolField } from "./fields/BoolField";
import { DateField } from "./fields/DateField";
import { EnumSegment } from "./fields/EnumSegment";
import { ListField } from "./fields/ListField";
import { NumberField } from "./fields/NumberField";
import { RefSelect, type RefOption } from "./fields/RefSelect";
import { TextField } from "./fields/TextField";

export type DraftItem = EconomicsReferenceItem & { row_id: string };

type Meta = {
  code: string;
  name: string;
  is_active: boolean;
  valid_from: string | null;
  valid_to: string | null;
  source: string;
  comment: string;
};

function metaOf(record: DraftItem): Meta {
  return {
    code: record.code,
    name: record.name,
    is_active: record.is_active,
    valid_from: record.valid_from,
    valid_to: record.valid_to,
    source: record.source,
    comment: record.comment,
  };
}

/**
 * Универсальная форма записи справочника.
 *
 * Ни одного знания о конкретном разделе: состав полей, единицы, ссылки и
 * группировка приходят из схемы. Раздел добавляется на бэкенде — форма
 * появляется сама.
 */
export function RecordForm({
  section,
  record,
  published,
  issues,
  canEdit,
  isNew,
  changed,
  refOptions,
  sectionLabels,
  siblings,
  context,
  vatRate,
  onApply,
  onReset,
  onDeactivate,
  onDuplicate,
  onClose,
}: {
  section: ReferenceSectionSchema;
  record: DraftItem;
  published: EconomicsReferenceItem | undefined;
  issues: ReferenceValidationIssue[];
  canEdit: boolean;
  isNew: boolean;
  changed: boolean;
  refOptions: (refSection: string) => RefOption[];
  sectionLabels: Record<string, string>;
  /** Payload остальных записей раздела — образец для списков без схемы элемента. */
  siblings: Array<Record<string, unknown>>;
  context: DerivedContext;
  vatRate: number;
  onApply: (next: DraftItem) => void;
  onReset: () => void;
  onDeactivate: () => void;
  onDuplicate: () => void;
  onClose: () => void;
}) {
  const fields = useMemo(() => sectionFields(section.json_schema), [section]);
  const fieldsets = useMemo(() => formFieldsets(section), [section]);
  const hasRubleFields = fields.some(isRubleField);

  const [meta, setMeta] = useState<Meta>(() => metaOf(record));
  const [values, setValues] = useState<FormValues>(() => toFormValues(record.payload, fields));
  const [vatMode, setVatMode] = useState(false);
  // Поля, тронутые с включённым «ввести с НДС»: пересчитываем только их, чтобы
  // уже сохранённые суммы без НДС не делились на ставку второй раз.
  const [touched, setTouched] = useState<Set<string>>(() => new Set());

  // Форма пересобирается на любую внешнюю смену записи, а не только на выбор
  // другой строки: «Сбросить» и «Деактивировать» меняют запись в черновике, и
  // форма обязана показать результат, иначе следующий «Применить» вернёт
  // отменённое.
  useEffect(() => {
    setMeta(metaOf(record));
    setValues(toFormValues(record.payload, fields));
    setVatMode(false);
    setTouched(new Set());
  }, [record, section.code]); // eslint-disable-line react-hooks/exhaustive-deps

  const fieldErrors = useMemo(() => {
    const map = new Map<string, string>();
    for (const issue of issues) {
      if (issue.field && !map.has(issue.field)) map.set(issue.field, issue.message);
    }
    return map;
  }, [issues]);
  const commonIssues = issues.filter((issue) => !issue.field);

  const previewPayload = useMemo(() => toPayload(values, fields, record.payload), [values, fields, record.payload]);
  const hints = useMemo(
    () => derivedHints(section.code, meta.code, previewPayload, context),
    [section.code, meta.code, previewPayload, context],
  );

  function setValue(name: string, value: unknown) {
    setValues((current) => ({ ...current, [name]: value }));
    if (vatMode) setTouched((current) => new Set(current).add(name));
  }

  function apply() {
    const payload = toPayload(values, fields, record.payload);
    for (const field of fields) {
      if (!vatMode || !isRubleField(field) || !touched.has(field.name)) continue;
      const parsed = parseNumber(payload[field.name]);
      if (parsed === null) continue;
      payload[field.name] = String(withoutVat(parsed, vatRate));
    }
    onApply({
      ...record,
      ...meta,
      code: meta.code.trim().toUpperCase(),
      payload,
    });
    setVatMode(false);
    setTouched(new Set());
  }

  function renderField(field: FieldDescriptor) {
    const error = fieldErrors.get(field.name);
    const disabled = !canEdit;
    switch (field.kind) {
      case "ref":
        return (
          <RefSelect
            key={field.name}
            field={field}
            value={String(values[field.name] ?? "")}
            options={refOptions(field.ref)}
            sectionLabel={sectionLabels[field.ref]}
            onChange={(next) => setValue(field.name, next)}
            disabled={disabled}
            error={error}
          />
        );
      case "enum":
        return (
          <EnumSegment
            key={field.name}
            field={field}
            value={String(values[field.name] ?? "")}
            onChange={(next) => setValue(field.name, next)}
            disabled={disabled}
            error={error}
          />
        );
      case "number":
        return (
          <NumberField
            key={field.name}
            field={field}
            value={String(values[field.name] ?? "")}
            onChange={(next) => setValue(field.name, next)}
            disabled={disabled}
            error={error}
            vatMode={vatMode && touched.has(field.name)}
            vatRate={vatRate}
          />
        );
      case "boolean":
        return (
          <BoolField
            key={field.name}
            field={field}
            value={values[field.name] === true}
            onChange={(next) => setValue(field.name, next)}
            disabled={disabled}
            error={error}
          />
        );
      case "date":
        return (
          <DateField
            key={field.name}
            field={field}
            value={String(values[field.name] ?? "")}
            onChange={(next) => setValue(field.name, next)}
            disabled={disabled}
            error={error}
          />
        );
      case "list":
        return (
          <ListField
            key={field.name}
            field={field}
            value={Array.isArray(values[field.name]) ? (values[field.name] as unknown[]) : []}
            onChange={(next) => setValue(field.name, next)}
            disabled={disabled}
            error={error}
            refOptions={refOptions}
            sampleRows={siblings.flatMap((payload) => {
              const value = payload[field.name];
              return Array.isArray(value) ? value : [];
            })}
          />
        );
      default:
        return (
          <TextField
            key={field.name}
            field={field}
            value={String(values[field.name] ?? "")}
            onChange={(next) => setValue(field.name, next)}
            disabled={disabled}
            error={error}
          />
        );
    }
  }

  return (
    <aside className="ref-form">
      <header className="ref-form-head">
        <div>
          <span className="ref-form-kicker">
            {isNew ? "Новая запись" : changed ? "Изменено в черновике" : section.label}
          </span>
          <b>{meta.name || meta.code || "Без наименования"}</b>
        </div>
        <div className="ref-form-head-actions">
          {canEdit && published && (
            <button type="button" title="Деактивировать запись" onClick={onDeactivate}>
              {meta.is_active ? "⌀" : "✓"}
            </button>
          )}
          <button type="button" title="Закрыть" onClick={onClose}>
            ×
          </button>
        </div>
      </header>

      <div className="ref-form-body">
        {commonIssues.length > 0 && (
          <div className="ref-form-issues">
            {commonIssues.map((issue, index) => (
              <p key={index} className={issue.level}>
                {issue.message}
              </p>
            ))}
          </div>
        )}

        <div className="ref-field">
          <label htmlFor="ref-meta-name">Наименование</label>
          <input
            id="ref-meta-name"
            value={meta.name}
            disabled={!canEdit}
            onChange={(event) => setMeta({ ...meta, name: event.target.value })}
          />
        </div>
        <div className="ref-field">
          <label htmlFor="ref-meta-code">Код</label>
          <input
            id="ref-meta-code"
            value={meta.code}
            disabled={!canEdit}
            onChange={(event) => setMeta({ ...meta, code: event.target.value.toUpperCase() })}
          />
        </div>

        {hasRubleFields && canEdit && (
          <label className="ref-vat-toggle">
            <input type="checkbox" checked={vatMode} onChange={(event) => setVatMode(event.target.checked)} />
            <span>
              Ввести с НДС {Math.round(vatRate * 100)} % — при применении рублёвые поля пересчитаются без НДС
            </span>
          </label>
        )}

        {fieldsets.map((fieldset, index) => (
          <section className="ref-fieldset" key={fieldset.title || index}>
            {fieldset.title && <h4>{fieldset.title}</h4>}
            {fieldset.fields.map(renderField)}
          </section>
        ))}

        {hints.length > 0 && (
          <div className="ref-hints">
            {hints.map((hint) => (
              <div key={hint.label}>
                <span>{hint.label}</span>
                <b>{hint.value}</b>
              </div>
            ))}
          </div>
        )}

        <section className="ref-fieldset">
          <h4>Прочее</h4>
          <div className="ref-field-row">
            <div className="ref-field">
              <label htmlFor="ref-meta-from">Действует с</label>
              <input
                id="ref-meta-from"
                type="date"
                value={meta.valid_from ?? ""}
                disabled={!canEdit}
                onChange={(event) => setMeta({ ...meta, valid_from: event.target.value || null })}
              />
            </div>
            <div className="ref-field">
              <label htmlFor="ref-meta-to">Действует до</label>
              <input
                id="ref-meta-to"
                type="date"
                value={meta.valid_to ?? ""}
                disabled={!canEdit}
                onChange={(event) => setMeta({ ...meta, valid_to: event.target.value || null })}
              />
            </div>
          </div>
          <div className="ref-field">
            <label htmlFor="ref-meta-source">Источник</label>
            <input
              id="ref-meta-source"
              value={meta.source}
              disabled={!canEdit}
              onChange={(event) => setMeta({ ...meta, source: event.target.value })}
            />
          </div>
          <div className="ref-field">
            <label htmlFor="ref-meta-comment">Комментарий</label>
            <textarea
              id="ref-meta-comment"
              rows={2}
              value={meta.comment}
              disabled={!canEdit}
              onChange={(event) => setMeta({ ...meta, comment: event.target.value })}
            />
          </div>
        </section>
      </div>

      <footer className="ref-form-actions">
        {canEdit && published && (
          <button type="button" className="ref-ghost-button" onClick={onDuplicate}>
            Дублировать
          </button>
        )}
        {/* У записи, которой ещё нет в опубликованной ревизии, возвращать
            нечего: единственное осмысленное действие — убрать её из черновика,
            иначе ошибочно добавленная строка блокирует публикацию. */}
        <button
          type="button"
          className={published ? "ref-ghost-button" : "ref-ghost-button danger"}
          onClick={onReset}
          disabled={!canEdit}
        >
          {published ? "Сбросить" : "Удалить"}
        </button>
        <button type="button" className="primary-button" onClick={apply} disabled={!canEdit}>
          Применить
        </button>
      </footer>
    </aside>
  );
}
