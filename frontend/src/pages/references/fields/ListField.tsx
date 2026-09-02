import { FieldShell } from "./FieldShell";
import { RefSelect, type RefOption } from "./RefSelect";
import { EnumSegment } from "./EnumSegment";
import { keyLabel } from "../enumLabels";
import type { FieldDescriptor } from "../schemaFields";

type Row = Record<string, unknown>;

/**
 * Список значений: строки, объекты по схеме элемента (состав бригады) и
 * свободные объекты (состав пакета работ). JSON пользователю не показываем —
 * свободный объект редактируется по ключам, которые в нём уже есть.
 */
export function ListField({
  field,
  value,
  onChange,
  disabled,
  error,
  refOptions,
  sampleRows = [],
}: {
  field: FieldDescriptor;
  value: unknown[];
  onChange: (value: unknown[]) => void;
  disabled?: boolean;
  error?: string;
  refOptions: (section: string) => RefOption[];
  /** Строки того же поля у соседних записей раздела: по ним узнаём состав ключей. */
  sampleRows?: unknown[];
}) {
  const rows = Array.isArray(value) ? value : [];

  function replace(index: number, next: unknown) {
    onChange(rows.map((row, i) => (i === index ? next : row)));
  }

  function remove(index: number) {
    onChange(rows.filter((_, i) => i !== index));
  }

  if (field.itemKind === "text") {
    return (
      <FieldShell field={field} error={error}>
        <div className="ref-list">
          {rows.map((row, index) => (
            <div className="ref-list-row" key={index}>
              <input
                value={typeof row === "string" ? row : String(row ?? "")}
                disabled={disabled}
                onChange={(event) => replace(index, event.target.value)}
              />
              <button type="button" disabled={disabled} onClick={() => remove(index)} aria-label="Удалить">
                ×
              </button>
            </div>
          ))}
          <button type="button" className="ref-list-add" disabled={disabled} onClick={() => onChange([...rows, ""])}>
            + Добавить
          </button>
        </div>
      </FieldShell>
    );
  }

  if (field.itemKind === "object" && field.itemFields?.length) {
    const itemFields = field.itemFields;
    return (
      <FieldShell field={field} error={error}>
        <div className="ref-list">
          {rows.map((row, index) => {
            const item = (row ?? {}) as Row;
            return (
              <div className="ref-list-card" key={index}>
                {itemFields.map((sub) => {
                  const raw = item[sub.name];
                  const text = raw === null || raw === undefined ? "" : String(raw);
                  const patch = (next: unknown) => replace(index, { ...item, [sub.name]: next });
                  if (sub.kind === "ref") {
                    return (
                      <RefSelect
                        key={sub.name}
                        field={sub}
                        value={text}
                        options={refOptions(sub.ref)}
                        onChange={patch}
                        disabled={disabled}
                      />
                    );
                  }
                  if (sub.kind === "enum") {
                    return (
                      <EnumSegment key={sub.name} field={sub} value={text} onChange={patch} disabled={disabled} />
                    );
                  }
                  return (
                    <div className="ref-field" key={sub.name}>
                      <label>{sub.title}</label>
                      <div className="ref-input-wrap">
                        <input
                          value={text}
                          disabled={disabled}
                          inputMode={sub.kind === "number" ? "decimal" : undefined}
                          onChange={(event) => patch(event.target.value)}
                        />
                        {sub.unit && <span className="ref-input-unit">{sub.unit}</span>}
                      </div>
                    </div>
                  );
                })}
                <button type="button" className="ref-list-remove" disabled={disabled} onClick={() => remove(index)}>
                  Удалить строку
                </button>
              </div>
            );
          })}
          <button
            type="button"
            className="ref-list-add"
            disabled={disabled}
            onClick={() => onChange([...rows, Object.fromEntries(itemFields.map((sub) => [sub.name, ""]))])}
          >
            + Добавить строку
          </button>
        </div>
      </FieldShell>
    );
  }

  // Свободный объект: схемы элемента нет, поэтому состав ключей берём из
  // сохранённых строк, а у пустого списка — из таких же строк соседних записей
  // раздела. Без этого новую запись нечем было бы заполнить: ключей нет, и
  // кнопка добавления не появлялась. Флаги уводим в конец — сначала то, что
  // описывает строку, потом её признаки.
  const known = rows.length ? rows : sampleRows;
  const keys = Array.from(
    new Set(known.flatMap((row) => (row && typeof row === "object" ? Object.keys(row as Row) : []))),
  ).sort((left, right) => {
    const flag = (key: string) => known.some((row) => typeof (row as Row)?.[key] === "boolean");
    return Number(flag(left)) - Number(flag(right));
  });
  return (
    <FieldShell field={field} error={error}>
      <div className="ref-list">
        {rows.map((row, index) => {
          const item = (row ?? {}) as Row;
          return (
            <div className="ref-list-card" key={index}>
              {keys.map((key) => {
                const raw = item[key];
                const patch = (next: unknown) => replace(index, { ...item, [key]: next });
                if (typeof raw === "boolean") {
                  return (
                    <label className="ref-checkbox" key={key}>
                      <input
                        type="checkbox"
                        checked={raw}
                        disabled={disabled}
                        onChange={(event) => patch(event.target.checked)}
                      />
                      <span>{keyLabel(key)}</span>
                    </label>
                  );
                }
                return (
                  <div className="ref-field" key={key}>
                    <label>{keyLabel(key)}</label>
                    <input
                      value={raw === null || raw === undefined ? "" : String(raw)}
                      disabled={disabled}
                      onChange={(event) => patch(event.target.value)}
                    />
                  </div>
                );
              })}
              <button type="button" className="ref-list-remove" disabled={disabled} onClick={() => remove(index)}>
                Удалить строку
              </button>
            </div>
          );
        })}
        {keys.length > 0 && (
          <button
            type="button"
            className="ref-list-add"
            disabled={disabled}
            onClick={() => onChange([...rows, Object.fromEntries(keys.map((key) => [key, ""]))])}
          >
            + Добавить строку
          </button>
        )}
      </div>
    </FieldShell>
  );
}
