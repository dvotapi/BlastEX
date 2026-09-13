import { describe, expect, it } from "vitest";
import {
  decimalText,
  defaultPayload,
  describeField,
  fieldErrorShown,
  formatFieldValue,
  formFieldsets,
  listCellText,
  listItemErrors,
  newListRow,
  normalizeListRows,
  numericPayloadKeys,
  sectionFields,
  toFormValues,
  toPayload,
  withoutVat,
} from "./schemaFields";
import type { JsonSchemaObject, ReferenceSectionSchema } from "../../types/referenceSchema";

// Фрагмент реального ответа `/references/schema` для раздела «Должности».
const POSITIONS_SCHEMA: JsonSchemaObject = {
  type: "object",
  additionalProperties: false,
  properties: {
    legacy_ref: {
      anyOf: [{ type: "string" }, { type: "null" }],
      default: null,
      title: "Legacy Ref",
      "x-internal": true,
    },
    category: {
      default: "DIRECT",
      description: "Прямой персонал блока или косвенный персонал юнита",
      enum: ["DIRECT", "INDIRECT"],
      title: "Категория",
      type: "string",
    },
    operation_code: {
      anyOf: [{ type: "string" }, { type: "null" }],
      default: null,
      description: "Операция пакета",
      title: "Операция пакета",
      "x-ref": "operations",
    },
    norm_shifts_per_month: {
      anyOf: [{ minimum: 0, type: "number" }, { pattern: "^\\d+$", type: "string" }],
      default: "21",
      description: "Нормативных смен в месяц",
      title: "Нормативных смен в месяц",
      "x-unit": "см/мес",
    },
    per_diem_applies: { default: true, title: "Суточные и проживание", type: "boolean" },
  },
};

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

describe("описание полей по схеме", () => {
  it("узнаёт ссылку, перечисление, число с единицей и флаг", () => {
    const fields = new Map(sectionFields(POSITIONS_SCHEMA).map((field) => [field.name, field]));

    expect(fields.get("operation_code")?.kind).toBe("ref");
    expect(fields.get("operation_code")?.ref).toBe("operations");
    expect(fields.get("operation_code")?.optional).toBe(true);
    expect(fields.get("category")?.kind).toBe("enum");
    expect(fields.get("category")?.options).toEqual(["DIRECT", "INDIRECT"]);
    expect(fields.get("norm_shifts_per_month")?.kind).toBe("number");
    expect(fields.get("norm_shifts_per_month")?.unit).toBe("см/мес");
    expect(fields.get("norm_shifts_per_month")?.optional).toBe(false);
    expect(fields.get("per_diem_applies")?.kind).toBe("boolean");
  });

  it("подпись поля берётся из title каталога схем", () => {
    const fields = new Map(sectionFields(POSITIONS_SCHEMA).map((field) => [field.name, field]));
    expect(fields.get("norm_shifts_per_month")?.title).toBe("Нормативных смен в месяц");
    expect(fields.get("category")?.title).toBe("Категория");
    // Поле без заголовка показывается по имени, а не пустой строкой.
    expect(describeField("headcount", { description: "Сколько человек", type: "number" }).title).toBe("headcount");
  });

  it("не показывает служебные поля", () => {
    expect(sectionFields(POSITIONS_SCHEMA).map((field) => field.name)).not.toContain("legacy_ref");
  });

  it("раскрывает элемент списка объектов в подполя", () => {
    const members = sectionFields(CREW_SCHEMA)[0];
    expect(members.kind).toBe("list");
    expect(members.itemKind).toBe("object");
    expect(members.itemFields?.map((field) => field.name)).toEqual(["position_code", "headcount"]);
    expect(members.itemFields?.[0].kind).toBe("ref");
  });

  it("группы полей берутся с сервера, а без них поля идут одним набором", () => {
    const section = {
      code: "positions",
      label: "Должности",
      group: "labor",
      view: "table",
      deprecated: false,
      list_columns: [],
      fieldsets: [{ title: "Роль", fields: ["category", "operation_code"] }],
      json_schema: POSITIONS_SCHEMA,
    } as ReferenceSectionSchema;

    expect(formFieldsets(section)).toHaveLength(1);
    expect(formFieldsets(section)[0].fields.map((field) => field.name)).toEqual(["category", "operation_code"]);
    expect(formFieldsets({ ...section, fieldsets: [] })[0].fields).toHaveLength(4);
  });
});

describe("значения формы и payload", () => {
  const fields = sectionFields(POSITIONS_SCHEMA);

  it("payload превращается в строки полей, а флаг остаётся флагом", () => {
    const values = toFormValues({ category: "INDIRECT", operation_code: null, norm_shifts_per_month: "21" }, fields);
    expect(values).toEqual({
      category: "INDIRECT",
      operation_code: "",
      norm_shifts_per_month: "21",
      per_diem_applies: true,
    });
  });

  it("отсутствующее поле показывается значением по умолчанию из схемы", () => {
    // Запись старой ревизии поля не знает, а сервер считает её значением по
    // умолчанию: форма не вправе показывать «— выберите —» вместо него.
    const values = toFormValues({ category: "DIRECT" }, fields);

    expect(values.norm_shifts_per_month).toBe("21");
    expect(values.per_diem_applies).toBe(true);
  });

  it("пустое необязательное поле сохраняется как null, пустое обязательное — не сохраняется", () => {
    const payload = toPayload(
      { category: "DIRECT", operation_code: "", norm_shifts_per_month: "", per_diem_applies: false },
      fields,
    );
    expect(payload.operation_code).toBeNull();
    expect("norm_shifts_per_month" in payload).toBe(false);
    expect(payload.per_diem_applies).toBe(false);
  });

  it("служебные поля не теряются при сохранении", () => {
    const payload = toPayload({ category: "DIRECT" }, fields, { legacy_ref: "V1-17" });
    expect(payload.legacy_ref).toBe("V1-17");
  });

  it("число с запятой и разрядами приводится к виду, который принимает схема", () => {
    const payload = toPayload({ category: "DIRECT", norm_shifts_per_month: "21,5" }, fields);
    expect(payload.norm_shifts_per_month).toBe("21.5");
    expect(decimalText("55 000")).toBe("55000");
    expect(decimalText("4,2")).toBe("4.2");
    // Не похожее на число оставляем как есть — об этом скажет валидация.
    expect(decimalText("две смены")).toBe("две смены");
  });

  it("текстовое поле запятую не трогает", () => {
    const textFields = sectionFields({
      type: "object",
      properties: { region: { type: "string", title: "Регион" } },
    });
    expect(toPayload({ region: "Пермский край, север" }, textFields).region).toBe("Пермский край, север");
  });

  it("новая запись получает значения по умолчанию из схемы", () => {
    expect(defaultPayload(fields)).toEqual({
      category: "DIRECT",
      norm_shifts_per_month: "21",
      per_diem_applies: true,
    });
  });
});

describe("НДС и форматирование", () => {
  it("сумма с НДС 20 % сохраняется без НДС", () => {
    expect(withoutVat(100000, 0.2)).toBe(83333.33);
  });

  it("нулевая ставка ничего не меняет", () => {
    expect(withoutVat(1000, 0)).toBe(1000);
  });

  it("число в списке показывается с единицей измерения", () => {
    const field = describeField("norm_shifts_per_month", POSITIONS_SCHEMA.properties!.norm_shifts_per_month);
    expect(formatFieldValue("21", field).replace(/\s/g, " ")).toBe("21 см/мес");
    expect(formatFieldValue(null, field)).toBe("—");
  });
});

describe("числовые поля раздела", () => {
  it("собирает ключи, у которых схема допускает число", () => {
    expect(numericPayloadKeys(POSITIONS_SCHEMA)).toEqual(new Set(["norm_shifts_per_month"]));
  });

  it("не считает числовым текстовое поле из цифр", () => {
    const schema: JsonSchemaObject = {
      type: "object",
      properties: {
        inn: { anyOf: [{ type: "string" }, { type: "null" }], title: "ИНН" },
        role: { enum: ["CUSTOMER"], type: "string", title: "Роль" },
      },
    };
    expect(numericPayloadKeys(schema)).toEqual(new Set());
  });

  it("принимает раздел без схемы", () => {
    expect(numericPayloadKeys(undefined)).toEqual(new Set());
  });
});

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

describe("listCellText: текст ячейки подполя списка", () => {
  const members = sectionFields(CREW_SCHEMA)[0];
  const headcount = members.itemFields!.find((field) => field.name === "headcount")!;
  const positionCode = members.itemFields!.find((field) => field.name === "position_code")!;

  it("отсутствующее подполе с умолчанием в схеме — умолчание", () => {
    expect(listCellText(undefined, headcount)).toBe("1");
  });

  it("отсутствующее подполе без умолчания в схеме — пустая строка", () => {
    expect(listCellText(undefined, positionCode)).toBe("");
  });

  it("null — пустая строка", () => {
    expect(listCellText(null, headcount)).toBe("");
  });

  it("число остаётся строкой числа", () => {
    expect(listCellText(45, headcount)).toBe("45");
  });
});

describe("fieldErrorShown: путь ошибки, который форма рисует полем", () => {
  const fields = sectionFields(CREW_SCHEMA);

  it("путь равен имени поля верхнего уровня", () => {
    expect(fieldErrorShown("members", fields)).toBe(true);
  });

  it("путь — вся строка списка объектов", () => {
    expect(fieldErrorShown("members.0", fields)).toBe(true);
  });

  it("путь — подполе строки, которое есть в схеме элемента", () => {
    expect(fieldErrorShown("members.0.headcount", fields)).toBe(true);
  });

  it("подполе, которого нет в схеме элемента (лишний ключ), форма не рисует", () => {
    expect(fieldErrorShown("members.0.unknown_key", fields)).toBe(false);
  });

  it("путь глубже одного уровня форма не рисует", () => {
    expect(fieldErrorShown("members.0.headcount.extra", fields)).toBe(false);
  });

  it("поле верхнего уровня вне переданного набора полей", () => {
    expect(fieldErrorShown("other_field", fields)).toBe(false);
  });
});
