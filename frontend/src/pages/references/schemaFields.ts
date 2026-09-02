/**
 * Разбор JSON Schema раздела в описания полей формы.
 *
 * Это единственное место, где фронт интерпретирует схему: компоненты формы и
 * списка получают уже готовые описания и не разбирают `anyOf`, `$ref` и
 * метки `x-*` самостоятельно.
 */
import type {
  JsonSchemaNode,
  JsonSchemaObject,
  ReferenceSectionSchema,
} from "../../types/referenceSchema";

export type FieldKind = "number" | "text" | "enum" | "boolean" | "date" | "ref" | "list";

export type FieldDescriptor = {
  name: string;
  title: string;
  description: string;
  kind: FieldKind;
  unit: string;
  /** Раздел, на записи которого ссылается поле (`x-ref`). */
  ref: string;
  options: string[];
  optional: boolean;
  internal: boolean;
  minimum?: number;
  maximum?: number;
  defaultValue: unknown;
  /** Для списков: описание элемента. Объектный элемент раскрывается в подполя. */
  itemKind?: "text" | "object" | "free";
  itemFields?: FieldDescriptor[];
};

export type FormValues = Record<string, unknown>;

const RUBLE_UNITS = /₽/;

/**
 * Подпись поля.
 *
 * Подпись разрешает сервер (`cost/v2/schemas`): в `title` каталога схем уже
 * лежит русское название, и сообщения валидации называют поле так же. Здесь
 * остаётся только запасной вариант на случай поля без заголовка.
 */
function humanTitle(name: string, node: JsonSchemaNode): string {
  const title = typeof node.title === "string" ? node.title.trim() : "";
  return title || name;
}

function variants(node: JsonSchemaNode): JsonSchemaNode[] {
  return node.anyOf && node.anyOf.length ? node.anyOf : [node];
}

function pick<T>(node: JsonSchemaNode, read: (variant: JsonSchemaNode) => T | undefined): T | undefined {
  for (const variant of variants(node)) {
    const value = read(variant);
    if (value !== undefined) return value;
  }
  return undefined;
}

function isOptional(node: JsonSchemaNode): boolean {
  return variants(node).some((variant) => variant.type === "null");
}

function resolveRef(node: JsonSchemaNode, defs: Record<string, JsonSchemaNode>): JsonSchemaNode | null {
  const ref = node.$ref;
  if (typeof ref !== "string" || !ref.startsWith("#/$defs/")) return null;
  return defs[ref.slice("#/$defs/".length)] ?? null;
}

function describeItem(
  items: JsonSchemaNode | undefined,
  defs: Record<string, JsonSchemaNode>,
): Pick<FieldDescriptor, "itemKind" | "itemFields"> {
  if (!items) return { itemKind: "free" };
  const nested = resolveRef(items, defs);
  if (nested?.properties) {
    return {
      itemKind: "object",
      itemFields: Object.entries(nested.properties)
        .map(([name, node]) => describeField(name, node, defs))
        .filter((field) => !field.internal),
    };
  }
  if (items.type === "string") return { itemKind: "text" };
  return { itemKind: "free" };
}

export function describeField(
  name: string,
  node: JsonSchemaNode,
  defs: Record<string, JsonSchemaNode> = {},
): FieldDescriptor {
  const unit = pick(node, (variant) => variant["x-unit"]) ?? node["x-unit"] ?? "";
  const ref = pick(node, (variant) => variant["x-ref"]) ?? node["x-ref"] ?? "";
  const options = pick(node, (variant) => variant.enum) ?? node.enum ?? [];
  const type = pick(node, (variant) => (variant.type === "null" ? undefined : variant.type));
  const format = pick(node, (variant) => variant.format);

  let kind: FieldKind = "text";
  if (ref) kind = "ref";
  else if (options.length) kind = "enum";
  else if (type === "array") kind = "list";
  else if (type === "boolean") kind = "boolean";
  else if (type === "number" || type === "integer") kind = "number";
  else if (format === "date") kind = "date";
  // Decimal приходит как «число или строка с числовым шаблоном»: единица
  // измерения отличает его от свободного текста.
  else if (unit) kind = "number";

  const itemsNode = pick(node, (variant) => variant.items) ?? node.items;

  return {
    name,
    title: humanTitle(name, node),
    description: typeof node.description === "string" ? node.description : "",
    kind,
    unit,
    ref,
    options: [...options],
    optional: isOptional(node),
    internal: node["x-internal"] === true,
    minimum: pick(node, (variant) => variant.minimum),
    maximum: pick(node, (variant) => variant.maximum),
    defaultValue: node.default,
    ...(kind === "list" ? describeItem(itemsNode, defs) : {}),
  };
}

/** Все поля раздела, кроме служебных, в порядке объявления схемы. */
export function sectionFields(schema: JsonSchemaObject | undefined): FieldDescriptor[] {
  const defs = schema?.$defs ?? {};
  return Object.entries(schema?.properties ?? {})
    .map(([name, node]) => describeField(name, node, defs))
    .filter((field) => !field.internal);
}

export function fieldIndex(schema: JsonSchemaObject | undefined): Map<string, FieldDescriptor> {
  return new Map(sectionFields(schema).map((field) => [field.name, field]));
}

/** Группы полей формы: состав приходит с сервера, описания — из схемы. */
export function formFieldsets(
  section: ReferenceSectionSchema,
): Array<{ title: string; fields: FieldDescriptor[] }> {
  const index = fieldIndex(section.json_schema);
  const grouped = section.fieldsets
    .map((fieldset) => ({
      title: fieldset.title,
      fields: fieldset.fields.map((name) => index.get(name)).filter((field): field is FieldDescriptor => !!field),
    }))
    .filter((fieldset) => fieldset.fields.length > 0);
  if (grouped.length) return grouped;
  return [{ title: "", fields: sectionFields(section.json_schema) }];
}

export function isRubleField(field: FieldDescriptor): boolean {
  return field.kind === "number" && RUBLE_UNITS.test(field.unit);
}

/** Значение payload в вид, пригодный для input: числа и коды — строками. */
export function toFormValues(payload: Record<string, unknown>, fields: FieldDescriptor[]): FormValues {
  const values: FormValues = {};
  for (const field of fields) {
    const raw = payload[field.name];
    switch (field.kind) {
      case "boolean":
        values[field.name] = raw === undefined ? field.defaultValue === true : raw === true;
        break;
      case "list":
        values[field.name] = Array.isArray(raw) ? raw : [];
        break;
      default:
        values[field.name] = raw === null || raw === undefined ? "" : String(raw);
    }
  }
  return values;
}

/**
 * Число в виде, который понимает Decimal на сервере.
 *
 * Сметчик набирает «4,2» и «55 000» — с запятой и пробелами, как принято в
 * русской записи. Схема раздела принимает только точку без разделителей
 * разрядов, поэтому нормализуем на границе сохранения. Всё, что не похоже на
 * число, оставляем как есть: пусть о нём скажет валидация, а не мы молча.
 */
export function decimalText(text: string): string {
  const compact = text.replace(/[\s ]/g, "").replace(",", ".");
  return compact !== "" && /^[+-]?\d*\.?\d*$/.test(compact) ? compact : text;
}

/**
 * Обратное преобразование. Пустое необязательное поле сохраняется как `null`,
 * пустое обязательное — не сохраняется вовсе, и запись получает значение по
 * умолчанию из схемы вместо ошибки «ожидается число».
 */
export function toPayload(
  values: FormValues,
  fields: FieldDescriptor[],
  base: Record<string, unknown> = {},
): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  // Служебные поля (legacy_ref и прочие x-internal) не редактируются, но и не
  // теряются при сохранении записи.
  const editable = new Set(fields.map((field) => field.name));
  for (const [key, value] of Object.entries(base)) {
    if (!editable.has(key)) payload[key] = value;
  }

  for (const field of fields) {
    const value = values[field.name];
    if (field.kind === "boolean") {
      payload[field.name] = value === true;
      continue;
    }
    if (field.kind === "list") {
      payload[field.name] = Array.isArray(value) ? value : [];
      continue;
    }
    const text = typeof value === "string" ? value.trim() : value == null ? "" : String(value);
    if (text === "") {
      if (field.optional) payload[field.name] = null;
      continue;
    }
    payload[field.name] = field.kind === "number" ? decimalText(text) : text;
  }
  return payload;
}

/**
 * Payload новой записи: значения по умолчанию из схемы. Пустая форма с
 * нормативом «21 смена» понятнее, чем пустые поля, которые сервер молча
 * заполнит теми же значениями.
 */
export function defaultPayload(fields: FieldDescriptor[]): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  for (const field of fields) {
    if (field.defaultValue === undefined || field.defaultValue === null) continue;
    payload[field.name] = field.defaultValue;
  }
  return payload;
}

/** Цена без НДС по введённой сумме с НДС. Округление — до копейки. */
export function withoutVat(value: number, vatRate: number): number {
  if (!Number.isFinite(value) || !Number.isFinite(vatRate) || vatRate <= 0) return value;
  return Math.round((value / (1 + vatRate)) * 100) / 100;
}

export function parseNumber(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value !== "string") return null;
  const text = value.trim().replace(/\s| /g, "").replace(",", ".");
  if (!text) return null;
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : null;
}

const NUMBER_FORMAT = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 3 });

export function formatNumber(value: number): string {
  return NUMBER_FORMAT.format(value);
}

/** Значение поля для списка записей: число с единицей, код ссылки, «да/нет». */
export function formatFieldValue(value: unknown, field: FieldDescriptor | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  if (!field) return String(value);
  switch (field.kind) {
    case "boolean":
      return value === true ? "да" : "нет";
    case "number": {
      const parsed = parseNumber(value);
      if (parsed === null) return String(value);
      return field.unit ? `${formatNumber(parsed)} ${field.unit}` : formatNumber(parsed);
    }
    case "list":
      return Array.isArray(value) ? `${value.length}` : "—";
    default:
      return String(value);
  }
}
