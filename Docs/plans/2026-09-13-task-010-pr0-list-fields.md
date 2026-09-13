# TASK-010 PR 0 — вложенные списки в формах справочников

> **Для исполнителя-агента:** обязательный навык — superpowers:subagent-driven-development (рекомендуется) или
> superpowers:executing-plans. Шаги отмечаются чекбоксами (`- [ ]`).

**Цель:** форма справочника корректно сохраняет списки объектов: пустое подполе — `null` или значение по
умолчанию, «4,5» — «4.5», ошибка сервера `поле.N.подполе` видна под своим подполем, id подполей уникальны.

**Архитектура:** правила нормализации живут в `schemaFields.ts` рядом с `toPayload` — единственном месте, где
фронт интерпретирует схему. `ListField` только рисует и берёт готовые описания, `RecordForm` раздаёт ошибки
подполям. Разделоспецифичного кода нет.

**Стек:** React 18 + TypeScript, vitest + @testing-library/react (jsdom), pytest.

**Спецификация:** `Docs/specs/2026-09-13-task-010-payroll-decisions.md` (§5, PR 0); задача —
`TASK-010 Зарплата персонала по объектам 3.md`.

## Контекст

Разделы TASK-010 добавят списки объектов: ступени шкалы `tiers [{upto_per_shift, rate}]` (у последней ступени
`upto_per_shift = null`), интервалы крепости `hardness [{f_from, f_to, k}]`, диаметры, геологию объекта. Сейчас
форма их испортит:

1. Новая строка заполняется пустыми строками `""` (`fields/ListField.tsx:121`), подполя пишутся сырым текстом
   (`ListField.tsx:104`), `toPayload` отдаёт список как есть (`schemaFields.ts:249-251`). Сервер на `""` и
   `"4,5"` во вложенном `Decimal | None` отвечает `decimal_parsing` — последнюю ступень шкалы сохранить нельзя.
   Тот же дефект уже есть у `crew_templates.members.headcount` (`cost/v2/schemas/labor.py:78`).
2. Сервер адресует ошибку подполя как `members.0.headcount` (`cost/v2/references.py:423`, `:495-500`), а
   `RecordForm` ищет ошибку по точному имени поля (`RecordForm.tsx:115-121`) — ошибка не видна нигде.
3. `RefSelect` и `EnumSegment` ставят `id="ref-field-<имя>"` — в двух строках списка id повторяются.
4. Тесты единиц и русских подписей (`tests/test_reference_schemas.py:36-49`, `:165-175`) не обходят `$defs` —
   поля элементов списков не проверяются.

## Глобальные ограничения

- Форма не хранит знаний о разделах (CLAUDE.md): никаких проверок `section.code`.
- JSON пользователю не показывается.
- Число из payload, пришедшее числом (`1`), остаётся числом; строка — строкой. «Применить» без правок возвращает
  тот же payload.
- Пустое обязательное подполе не сохраняется (сервер подставит умолчание), пустое необязательное — `null`.
  Это то же правило, что `toPayload` применяет к полям верхнего уровня (`schemaFields.ts:253-257`).
- Проверки: `cd frontend && npx vitest run src/pages/references` после каждой задачи; перед PR — полный
  `npx vitest run`, `npx tsc -b` и `.venv/bin/python -m pytest tests/test_reference_schemas.py`.
- iCloud-дубли (`* 2.ts`, `* 3.ts`) не трогать и не коммитить.

## Файлы

- Изменить: `frontend/src/pages/references/schemaFields.ts` — `normalizeListRows`, `newListRow`,
  `listItemErrors`; `toPayload` нормализует списки.
- Изменить: `frontend/src/pages/references/fields/ListField.tsx` — умолчания новой строки, ошибки подполей,
  уникальные id.
- Изменить: `frontend/src/pages/references/RecordForm.tsx` — передача ошибок подполей в `ListField`.
- Изменить: `frontend/src/pages/references/schemaFields.test.ts` — тесты нормализации.
- Создать: `frontend/src/pages/references/fields/ListField.test.tsx`.
- Создать: `frontend/src/pages/references/RecordForm.test.tsx`.
- Изменить: `tests/test_reference_schemas.py` — обход `$defs`.

---

### Задача 0: ветка

- [ ] **Шаг 1: создать ветку от свежего main**

```bash
git switch main && git pull --ff-only && git switch -c feat/task-010-pr0-list-fields
```

- [ ] **Шаг 2: закоммитить решения и этот план**

```bash
git add Docs/specs/2026-09-13-task-010-payroll-decisions.md Docs/plans/2026-09-13-task-010-pr0-list-fields.md
git commit -m "TASK-010: решения к реализации и план PR 0"
```

---

### Задача 1: нормализация строк списка в `schemaFields.ts`

**Файлы:**
- Изменить: `frontend/src/pages/references/schemaFields.ts:212-261`
- Тест: `frontend/src/pages/references/schemaFields.test.ts`

**Интерфейсы:**
- Использует: `FieldDescriptor`, `decimalText`, `sectionFields` (есть).
- Даёт: `normalizeListRows(rows: unknown, field: FieldDescriptor): unknown[]`,
  `newListRow(itemFields: FieldDescriptor[]): Record<string, unknown>`,
  `listItemErrors(errors: Map<string, string>, name: string): Map<string, string>`.

- [ ] **Шаг 1: написать падающие тесты**

В `schemaFields.test.ts` дополнить импорт:

```ts
import {
  decimalText,
  defaultPayload,
  describeField,
  formatFieldValue,
  formFieldsets,
  listItemErrors,
  newListRow,
  normalizeListRows,
  numericPayloadKeys,
  sectionFields,
  toFormValues,
  toPayload,
  withoutVat,
} from "./schemaFields";
```

В конец файла добавить:

```ts
// Ступени шкалы: у последней ступени верхнего порога нет (`null`).
const TIERS_SCHEMA: JsonSchemaObject = {
  type: "object",
  $defs: {
    Tier: {
      type: "object",
      properties: {
        upto_per_shift: {
          anyOf: [{ minimum: 0, type: "number" }, { pattern: "^\\d+(\\.\\d+)?$", type: "string" }, { type: "null" }],
          default: null,
          title: "До, м/смену",
          "x-unit": "м/смену",
        },
        rate: {
          anyOf: [{ minimum: 0, type: "number" }, { pattern: "^\\d+(\\.\\d+)?$", type: "string" }],
          default: "0",
          title: "Расценка",
          "x-unit": "₽/м",
        },
        grade: { anyOf: [{ type: "string" }, { type: "null" }], default: null, title: "Категория" },
      },
    },
  },
  properties: {
    tiers: { type: "array", items: { $ref: "#/$defs/Tier" }, title: "Ступени" },
  },
};

describe("строки списка объектов", () => {
  const tiers = sectionFields(TIERS_SCHEMA)[0];
  const members = sectionFields(CREW_SCHEMA)[0];

  it("пустое необязательное подполе сохраняется как null, запятая становится точкой", () => {
    expect(
      normalizeListRows([{ upto_per_shift: "115,3846", rate: " 45 " }, { upto_per_shift: "", rate: "168,66" }], tiers),
    ).toEqual([
      { upto_per_shift: "115.3846", rate: "45" },
      { upto_per_shift: null, rate: "168.66" },
    ]);
  });

  it("пустое обязательное подполе не сохраняется — сервер возьмёт значение по умолчанию", () => {
    expect(normalizeListRows([{ position_code: "POS_A", headcount: "" }], members)).toEqual([{ position_code: "POS_A" }]);
  });

  it("пустая ссылка в необязательном текстовом подполе — null, а не пустая строка", () => {
    expect(normalizeListRows([{ rate: "1", grade: "" }], tiers)).toEqual([{ rate: "1", grade: null }]);
  });

  it("числа, null и неизвестные ключи из payload не меняются", () => {
    const rows = [{ upto_per_shift: null, rate: 45, legacy_ref: "X" }];
    expect(normalizeListRows(rows, tiers)).toEqual(rows);
  });

  it("список без схемы элемента и не-список возвращаются как есть", () => {
    const free = describeField("items", { type: "array", title: "Состав" });
    expect(normalizeListRows([{ a: "" }], free)).toEqual([{ a: "" }]);
    expect(normalizeListRows("не список", tiers)).toEqual([]);
  });

  it("toPayload нормализует списки объектов", () => {
    const fields = sectionFields(TIERS_SCHEMA);
    expect(toPayload({ tiers: [{ upto_per_shift: "", rate: "4,5" }] }, fields)).toEqual({
      tiers: [{ upto_per_shift: null, rate: "4.5" }],
    });
  });

  it("новая строка заполняется значениями по умолчанию из схемы элемента", () => {
    expect(newListRow(members.itemFields ?? [])).toEqual({ position_code: "", headcount: "1" });
    expect(newListRow(tiers.itemFields ?? [])).toEqual({ upto_per_shift: "", rate: "0", grade: "" });
  });

  it("ошибки подполей отбираются по имени списка без префикса", () => {
    const errors = new Map([
      ["members.0.headcount", "Численность: ожидается число"],
      ["members.1", "Строка: должность повторяется"],
      ["members", "Состав пуст"],
      ["membership", "чужое поле"],
    ]);
    expect(listItemErrors(errors, "members")).toEqual(
      new Map([
        ["0.headcount", "Численность: ожидается число"],
        ["1", "Строка: должность повторяется"],
      ]),
    );
  });
});
```

- [ ] **Шаг 2: убедиться, что тесты падают**

Run: `cd frontend && npx vitest run src/pages/references/schemaFields.test.ts`
Expected: FAIL — `normalizeListRows is not a function` (и аналогично для `newListRow`, `listItemErrors`).

- [ ] **Шаг 3: реализовать**

В `schemaFields.ts` после `decimalText` (строка 223) добавить:

```ts
/**
 * Строки списка объектов в вид payload.
 *
 * Подполя элемента подчиняются тому же правилу, что поля верхнего уровня в
 * `toPayload`: пустое необязательное — `null`, пустое обязательное не
 * сохраняется, число приводится к записи с точкой. Числа, флаги и `null` из
 * payload не трогаем — «Применить» без правок возвращает тот же объект.
 * Ключи, которых нет в схеме элемента, сохраняются как есть.
 */
export function normalizeListRows(rows: unknown, field: FieldDescriptor): unknown[] {
  if (!Array.isArray(rows)) return [];
  const subs = field.itemKind === "object" ? field.itemFields ?? [] : [];
  if (!subs.length) return rows;
  return rows.map((row) => {
    if (!row || typeof row !== "object") return row;
    const item: Record<string, unknown> = { ...(row as Record<string, unknown>) };
    for (const sub of subs) {
      const raw = item[sub.name];
      if (raw === undefined || raw === null || typeof raw !== "string") continue;
      const text = raw.trim();
      if (text === "") {
        if (sub.optional) item[sub.name] = null;
        else delete item[sub.name];
        continue;
      }
      item[sub.name] = sub.kind === "number" ? decimalText(text) : text;
    }
    return item;
  });
}

/** Новая строка списка: значения по умолчанию из схемы элемента, остальное пусто. */
export function newListRow(itemFields: FieldDescriptor[]): Record<string, unknown> {
  return Object.fromEntries(
    itemFields.map((sub) => [
      sub.name,
      sub.defaultValue === undefined || sub.defaultValue === null ? "" : sub.defaultValue,
    ]),
  );
}

/**
 * Ошибки подполей списка.
 *
 * Сервер адресует ошибку внутри списка путём `members.0.headcount`
 * (`cost/v2/references.py`); список получает её без своего имени —
 * `0.headcount`, а ошибку всей строки — `0`.
 */
export function listItemErrors(errors: Map<string, string>, name: string): Map<string, string> {
  const prefix = `${name}.`;
  const nested = new Map<string, string>();
  for (const [path, message] of errors) {
    if (path.startsWith(prefix)) nested.set(path.slice(prefix.length), message);
  }
  return nested;
}
```

В `toPayload` заменить ветку списка (строки 249-252):

```ts
    if (field.kind === "list") {
      payload[field.name] = normalizeListRows(value, field);
      continue;
    }
```

- [ ] **Шаг 4: убедиться, что тесты проходят**

Run: `cd frontend && npx vitest run src/pages/references/schemaFields.test.ts`
Expected: PASS, включая прежние тесты файла.

- [ ] **Шаг 5: коммит**

```bash
git add frontend/src/pages/references/schemaFields.ts frontend/src/pages/references/schemaFields.test.ts
git commit -m "TASK-010 PR 0: нормализация строк списка объектов в форме справочника"
```

---

### Задача 2: `ListField` — умолчания, ошибки подполей, уникальные id

**Файлы:**
- Изменить: `frontend/src/pages/references/fields/ListField.tsx:1-128`
- Создать: `frontend/src/pages/references/fields/ListField.test.tsx`

**Интерфейсы:**
- Использует: `newListRow` из задачи 1; `FieldShell`, `RefSelect`, `EnumSegment` (есть).
- Даёт: проп `itemErrors?: Map<string, string>` у `ListField` (ключи `N.подполе` и `N`).

- [ ] **Шаг 1: написать падающий тест**

Создать `frontend/src/pages/references/fields/ListField.test.tsx`:

```tsx
// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ListField } from "./ListField";
import { sectionFields } from "../schemaFields";
import type { JsonSchemaObject } from "../../../types/referenceSchema";

afterEach(cleanup);

const CREW_SCHEMA: JsonSchemaObject = {
  type: "object",
  $defs: {
    CrewMember: {
      type: "object",
      properties: {
        position_code: { type: "string", title: "Должность", "x-ref": "positions" },
        headcount: {
          anyOf: [{ minimum: 0, type: "number" }, { type: "string" }],
          default: "1",
          title: "Численность",
          "x-unit": "чел",
        },
      },
    },
  },
  properties: {
    members: { type: "array", items: { $ref: "#/$defs/CrewMember" }, title: "Состав бригады" },
  },
};

const members = sectionFields(CREW_SCHEMA)[0];
const options = () => [{ code: "POS_A", name: "Машинист", is_active: true }];

describe("ListField: список объектов", () => {
  it("новая строка получает значения по умолчанию из схемы", () => {
    const onChange = vi.fn();
    render(<ListField field={members} value={[]} onChange={onChange} refOptions={options} />);
    fireEvent.click(screen.getByRole("button", { name: "+ Добавить строку" }));
    expect(onChange).toHaveBeenCalledWith([{ position_code: "", headcount: "1" }]);
  });

  it("ошибка сервера показывается под подполем своей строки", () => {
    render(
      <ListField
        field={members}
        value={[
          { position_code: "POS_A", headcount: "2" },
          { position_code: "POS_A", headcount: "x" },
        ]}
        onChange={() => undefined}
        refOptions={options}
        itemErrors={new Map([["1.headcount", "Численность: ожидается число"]])}
      />,
    );
    const inputs = screen.getAllByLabelText("Численность");
    expect(inputs).toHaveLength(2);
    expect(screen.getByText("Численность: ожидается число")).toBeInTheDocument();
    expect(inputs[1].closest(".ref-field")).toHaveClass("has-error");
    expect(inputs[0].closest(".ref-field")).not.toHaveClass("has-error");
  });

  it("ошибка всей строки показывается в её карточке", () => {
    render(
      <ListField
        field={members}
        value={[{ position_code: "POS_A", headcount: "1" }]}
        onChange={() => undefined}
        refOptions={options}
        itemErrors={new Map([["0", "Должность повторяется"]])}
      />,
    );
    expect(screen.getByText("Должность повторяется")).toBeInTheDocument();
  });

  it("id подполей не повторяются между строками", () => {
    const { container } = render(
      <ListField
        field={members}
        value={[
          { position_code: "POS_A", headcount: "1" },
          { position_code: "POS_A", headcount: "2" },
        ]}
        onChange={() => undefined}
        refOptions={options}
      />,
    );
    const ids = Array.from(container.querySelectorAll("[id]")).map((node) => node.id);
    expect(ids.length).toBeGreaterThan(0);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
```

- [ ] **Шаг 2: убедиться, что тест падает**

Run: `cd frontend && npx vitest run src/pages/references/fields/ListField.test.tsx`
Expected: FAIL — новая строка `{position_code: "", headcount: ""}`; `getAllByLabelText("Численность")` не находит
поля (у `<label>` нет `htmlFor`); id `ref-field-position_code` повторяется.

- [ ] **Шаг 3: реализовать**

В `ListField.tsx` заменить импорт типов и сигнатуру (строки 5, 14-31):

```tsx
import { newListRow, type FieldDescriptor } from "../schemaFields";
```

```tsx
export function ListField({
  field,
  value,
  onChange,
  disabled,
  error,
  itemErrors,
  refOptions,
  sampleRows = [],
}: {
  field: FieldDescriptor;
  value: unknown[];
  onChange: (value: unknown[]) => void;
  disabled?: boolean;
  error?: string;
  /** Ошибки внутри списка: `0.headcount` — подполе строки, `0` — вся строка. */
  itemErrors?: Map<string, string>;
  refOptions: (section: string) => RefOption[];
  /** Строки того же поля у соседних записей раздела: по ним узнаём состав ключей. */
  sampleRows?: unknown[];
}) {
```

Ветку объектного элемента (строки 66-128) заменить целиком:

```tsx
  if (field.itemKind === "object" && field.itemFields?.length) {
    const itemFields = field.itemFields;
    return (
      <FieldShell field={field} error={error}>
        <div className="ref-list">
          {rows.map((row, index) => {
            const item = (row ?? {}) as Row;
            const rowError = itemErrors?.get(String(index));
            return (
              <div className={`ref-list-card${rowError ? " has-error" : ""}`} key={index}>
                {itemFields.map((sub) => {
                  const raw = item[sub.name];
                  const text = raw === null || raw === undefined ? "" : String(raw);
                  const patch = (next: unknown) => replace(index, { ...item, [sub.name]: next });
                  // Имя с номером строки делает id подполя уникальным в форме и
                  // связывает подпись с полем; значение пишется по имени подполя.
                  const cell: FieldDescriptor = { ...sub, name: `${field.name}.${index}.${sub.name}` };
                  const subError = itemErrors?.get(`${index}.${sub.name}`);
                  if (sub.kind === "ref") {
                    return (
                      <RefSelect
                        key={sub.name}
                        field={cell}
                        value={text}
                        options={refOptions(sub.ref)}
                        onChange={patch}
                        disabled={disabled}
                        error={subError}
                      />
                    );
                  }
                  if (sub.kind === "enum") {
                    return (
                      <EnumSegment
                        key={sub.name}
                        field={cell}
                        value={text}
                        onChange={patch}
                        disabled={disabled}
                        error={subError}
                      />
                    );
                  }
                  return (
                    <FieldShell key={sub.name} field={cell} error={subError}>
                      <div className="ref-input-wrap">
                        <input
                          id={`ref-field-${cell.name}`}
                          value={text}
                          disabled={disabled}
                          inputMode={sub.kind === "number" ? "decimal" : undefined}
                          onChange={(event) => patch(event.target.value)}
                        />
                        {sub.unit && <span className="ref-input-unit">{sub.unit}</span>}
                      </div>
                    </FieldShell>
                  );
                })}
                {rowError && <p className="ref-field-error">{rowError}</p>}
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
            onClick={() => onChange([...rows, newListRow(itemFields)])}
          >
            + Добавить строку
          </button>
        </div>
      </FieldShell>
    );
  }
```

- [ ] **Шаг 4: убедиться, что тесты проходят**

Run: `cd frontend && npx vitest run src/pages/references`
Expected: PASS.

- [ ] **Шаг 5: коммит**

```bash
git add frontend/src/pages/references/fields/ListField.tsx frontend/src/pages/references/fields/ListField.test.tsx
git commit -m "TASK-010 PR 0: ошибки и уникальные id подполей списка"
```

---

### Задача 3: `RecordForm` раздаёт ошибки подполям

**Файлы:**
- Изменить: `frontend/src/pages/references/RecordForm.tsx:5-15`, `:216-231`
- Создать: `frontend/src/pages/references/RecordForm.test.tsx`

**Интерфейсы:**
- Использует: `listItemErrors` (задача 1), проп `itemErrors` (задача 2).

- [ ] **Шаг 1: написать падающий тест**

Создать `frontend/src/pages/references/RecordForm.test.tsx`:

```tsx
// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RecordForm, type DraftItem } from "./RecordForm";
import type { ReferenceSectionSchema } from "../../types/referenceSchema";
import type { ReferenceValidationIssue } from "../../types/economics";

afterEach(cleanup);

const SECTION: ReferenceSectionSchema = {
  code: "crew_templates",
  label: "Бригады",
  group: "labor",
  view: "table",
  deprecated: false,
  list_columns: [],
  fieldsets: [],
  json_schema: {
    type: "object",
    $defs: {
      CrewMember: {
        type: "object",
        properties: {
          position_code: { type: "string", title: "Должность", "x-ref": "positions" },
          headcount: {
            anyOf: [{ minimum: 0, type: "number" }, { type: "string" }],
            default: "1",
            title: "Численность",
            "x-unit": "чел",
          },
        },
      },
    },
    properties: {
      members: { type: "array", items: { $ref: "#/$defs/CrewMember" }, title: "Состав бригады" },
    },
  },
};

const RECORD: DraftItem = {
  row_id: "row-1",
  code: "CREW_DRILL",
  name: "Бригада бурения",
  payload: { members: [{ position_code: "POS_A", headcount: 2 }] },
  is_active: true,
  valid_from: null,
  valid_to: null,
  source: "",
  comment: "",
  revision: 1,
};

function renderForm(onApply: (next: DraftItem) => void, issues: ReferenceValidationIssue[] = []) {
  return render(
    <RecordForm
      section={SECTION}
      record={RECORD}
      published={RECORD}
      issues={issues}
      canEdit
      isNew={false}
      changed={false}
      refOptions={() => [{ code: "POS_A", name: "Машинист", is_active: true }]}
      sectionLabels={{ positions: "Должности" }}
      siblings={[]}
      context={{ sections: {} }}
      vatRate={0.2}
      onApply={onApply}
      onReset={() => undefined}
      onDeactivate={() => undefined}
      onDuplicate={() => undefined}
      onClose={() => undefined}
    />,
  );
}

describe("RecordForm: списки объектов", () => {
  it("«Применить» без правок возвращает тот же payload", () => {
    const onApply = vi.fn();
    renderForm(onApply);
    fireEvent.click(screen.getByRole("button", { name: "Применить" }));
    expect(onApply.mock.calls[0][0].payload).toEqual(RECORD.payload);
  });

  it("запятая в числе подполя сохраняется точкой, пустое обязательное — не сохраняется", () => {
    const onApply = vi.fn();
    renderForm(onApply);
    fireEvent.click(screen.getByRole("button", { name: "+ Добавить строку" }));
    const [first, second] = screen.getAllByLabelText("Численность");
    fireEvent.change(first, { target: { value: "2,5" } });
    fireEvent.change(second, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Применить" }));
    // Во второй строке оба подполя обязательные и пустые: ключи не сохраняются,
    // сервер подставит умолчание численности и сообщит о пустой должности.
    expect(onApply.mock.calls[0][0].payload).toEqual({
      members: [{ position_code: "POS_A", headcount: "2.5" }, {}],
    });
  });

  it("ошибка проверки ревизии видна под подполем строки", () => {
    renderForm(() => undefined, [
      {
        level: "error",
        section: "crew_templates",
        code: "CREW_DRILL",
        message: "Состав бригады → строка 1 → Численность: ожидается число",
        field: "members.0.headcount",
      },
    ]);
    expect(screen.getByText("Состав бригады → строка 1 → Численность: ожидается число")).toBeInTheDocument();
  });
});
```

- [ ] **Шаг 2: убедиться, что тест падает**

Run: `cd frontend && npx vitest run src/pages/references/RecordForm.test.tsx`
Expected: первый тест PASS (payload без правок не меняется и сейчас); второй — PASS после задачи 1 (нормализация
в `toPayload`); третий — FAIL: сообщение не найдено, `RecordForm` не передаёт ошибки подполей.

- [ ] **Шаг 3: реализовать**

В `RecordForm.tsx` дополнить импорт из `./schemaFields`:

```tsx
import {
  formFieldsets,
  isRubleField,
  listItemErrors,
  parseNumber,
  sectionFields,
  toFormValues,
  toPayload,
  withoutVat,
  type FieldDescriptor,
  type FormValues,
} from "./schemaFields";
```

В `renderField`, ветка `case "list"` (строки 216-231):

```tsx
      case "list":
        return (
          <ListField
            key={field.name}
            field={field}
            value={Array.isArray(values[field.name]) ? (values[field.name] as unknown[]) : []}
            onChange={(next) => setValue(field.name, next)}
            disabled={disabled}
            error={error}
            itemErrors={listItemErrors(fieldErrors, field.name)}
            refOptions={refOptions}
            sampleRows={siblings.flatMap((payload) => {
              const value = payload[field.name];
              return Array.isArray(value) ? value : [];
            })}
          />
        );
```

- [ ] **Шаг 4: убедиться, что тесты проходят**

Run: `cd frontend && npx vitest run src/pages/references`
Expected: PASS.

- [ ] **Шаг 5: коммит**

```bash
git add frontend/src/pages/references/RecordForm.tsx frontend/src/pages/references/RecordForm.test.tsx
git commit -m "TASK-010 PR 0: ошибки проверки ревизии под подполями списка"
```

---

### Задача 4: тесты схем обходят `$defs`

**Файлы:**
- Изменить: `tests/test_reference_schemas.py:36-49`, `:165-175`

Сейчас в `$defs` единственная модель — `CrewMember` (`crew_templates`), и она проходит обе проверки; тест —
страховка для элементов списков PR 1 (`tiers`, `hardness`, `diameter`, `geology`, `extra_tariff`).

- [ ] **Шаг 1: переписать проверки**

Добавить рядом с `_is_numeric`:

```python
def _field_containers(section: str):
    """Свойства раздела и вложенных моделей: подполе списка — такое же поле формы."""

    schema = section_json_schema(section)
    yield section, schema.get("properties") or {}
    for name, model in (schema.get("$defs") or {}).items():
        yield f"{section}.{name}", model.get("properties") or {}
```

Заменить тело `test_every_numeric_field_declares_a_unit`:

```python
    def test_every_numeric_field_declares_a_unit(self):
        """Без единицы сметчик не понимает, руб/смену перед ним или руб/месяц."""

        missing: list[str] = []
        for section in SECTION_SCHEMAS:
            for container, properties in _field_containers(section):
                for name, field in properties.items():
                    if not _is_numeric(field):
                        continue
                    if "x-unit" not in field and not any(
                        "x-unit" in variant for variant in field.get("anyOf", []) if isinstance(variant, dict)
                    ):
                        missing.append(f"{container}.{name}")
        assert missing == []
```

Заменить тело `test_every_field_has_a_russian_title`:

```python
    def test_every_field_has_a_russian_title(self):
        latin = set("abcdefghijklmnopqrstuvwxyz")
        for section in SECTION_SCHEMAS:
            for container, properties in _field_containers(section):
                for name, node in properties.items():
                    if node.get("x-internal"):
                        continue
                    title = node.get("title", "")
                    assert title, f"{container}.{name}: нет подписи поля"
                    # Английский заголовок pydantic («Rock Code») в интерфейс не попадает.
                    assert not set(title.lower()) <= latin | set(" -/()0123456789"), f"{container}.{name}: подпись {title!r}"
```

- [ ] **Шаг 2: проверить страховку на нарушении**

Временно в `cost/v2/schemas/labor.py:78` заменить
`headcount: Decimal = UnitField("чел", description="Численность", default=Decimal("1"), ge=0)` на
`headcount: Decimal = Field(description="Численность", default=Decimal("1"), ge=0)` (`Field` уже импортирован),
запустить:

Run: `.venv/bin/python -m pytest tests/test_reference_schemas.py -k "unit or russian_title" -v`
Expected: FAIL с `crew_templates.CrewMember.headcount` в списке. Вернуть `UnitField` (`git checkout cost/v2/schemas/labor.py`).

- [ ] **Шаг 3: убедиться, что тесты проходят**

Run: `.venv/bin/python -m pytest tests/test_reference_schemas.py -v`
Expected: PASS.

- [ ] **Шаг 4: коммит**

```bash
git add tests/test_reference_schemas.py
git commit -m "TASK-010 PR 0: проверка единиц и подписей у подполей списков"
```

---

### Задача 5: проверка на стенде и PR

- [ ] **Шаг 1: полный прогон**

```bash
cd frontend && npx vitest run && npx tsc -b
```

```bash
.venv/bin/python -m pytest tests/test_reference_schemas.py tests/test_api_economics.py -q
```

Expected: всё зелёное. `tsc -b` падает только на iCloud-дублях — проверить на чистом чекауте
(`git worktree add ../blastex-pr0 feat/task-010-pr0-list-fields`).

- [ ] **Шаг 2: стенд (api-stand :8020 / frontend-stand :5181)**

В разделе «Бригады» открыть запись, добавить строку состава, ввести численность «1,5», очистить должность у новой
строки, «Применить» → «Проверить». Ожидание: ошибка «строка 2 → Должность» видна под полем должности второй строки;
после выбора должности проверка проходит, численность сохранена как 1.5. Скриншот — в описание PR.

- [ ] **Шаг 3: PR**

```bash
git push -u origin feat/task-010-pr0-list-fields
gh pr create --title "TASK-010 PR 0: вложенные списки в формах справочников" --body "$(cat <<'EOF'
Подготовка форм справочников к разделам TASK-010 (ступени шкалы, интервалы крепости, геология объекта).

- Подполя списка объектов сохраняются по тем же правилам, что поля верхнего уровня: пустое необязательное — null, пустое обязательное не сохраняется, «4,5» → «4.5».
- Новая строка списка получает значения по умолчанию из схемы элемента.
- Ошибка проверки ревизии `поле.N.подполе` показывается под своим подполем; ошибка строки — в карточке.
- id подполей уникальны между строками.
- Тесты единиц и русских подписей обходят вложенные модели `$defs`.

Решения: Docs/specs/2026-09-13-task-010-payroll-decisions.md. План: Docs/plans/2026-09-13-task-010-pr0-list-fields.md.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Шаг 4: ревью** — `/code-review` по PR и замечания Codex до слияния.
