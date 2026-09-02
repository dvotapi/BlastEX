/**
 * Ответ `GET /api/v1/economics/references/schema`.
 *
 * Фронт не хранит собственных знаний о полях payload: состав, единицы,
 * ссылки на другие разделы и группировка формы приходят с сервера.
 */

export type JsonSchemaNode = {
  type?: string;
  anyOf?: JsonSchemaNode[];
  enum?: string[];
  items?: JsonSchemaNode;
  $ref?: string;
  title?: string;
  description?: string;
  default?: unknown;
  minimum?: number;
  maximum?: number;
  format?: string;
  pattern?: string;
  properties?: Record<string, JsonSchemaNode>;
  additionalProperties?: boolean | JsonSchemaNode;
  "x-unit"?: string;
  "x-ref"?: string;
  "x-internal"?: boolean;
};

export type JsonSchemaObject = JsonSchemaNode & {
  properties?: Record<string, JsonSchemaNode>;
  $defs?: Record<string, JsonSchemaNode>;
  required?: string[];
};

export type ReferenceFieldset = {
  title: string;
  fields: string[];
};

export type ReferenceSectionSchema = {
  code: string;
  label: string;
  group: string;
  view: "table" | "matrix";
  deprecated: boolean;
  list_columns: string[];
  fieldsets: ReferenceFieldset[];
  json_schema: JsonSchemaObject;
};

export type ReferenceSchemaCatalog = {
  groups: Array<{ code: string; label: string }>;
  sections: Record<string, ReferenceSectionSchema>;
};
