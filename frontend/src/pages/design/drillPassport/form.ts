// Модель формы паспорта на бурение (TASK-015, PR 6): поля, форма ⇄ payload,
// источники величин и строки «Проверки первого ряда». Только чистые функции —
// окно и панель их рисуют. Пределы длины — как в
// `api/schemas/drilling_passport.py` (TEXT_LIMITS, SIGNER_LIMITS, PERSON_LIMITS).
import { ruNumber } from "../../../lib/format";
import type {
  DrillPassport,
  DrillPassportIssue,
  DrillPassportPayload,
  DrillPassportUpdate,
  DrillPassportValidation,
  DrillPerson,
  DrillSigner,
  Provenance,
} from "../../../types/drillPassport";

export type ReferenceSection = "sites" | "equipment_types" | "drill_passport_profiles";

/** Поля с одним значением: номер и дата паспорта и простые поля payload. */
export type ScalarKey =
  | "passport_no"
  | "passport_date"
  | Exclude<keyof DrillPassportPayload, SignerKey | "extra_approvals" | "personnel">;

export type SignerKey = "agreed_by" | "approved_by" | "compiled_by";

export type FieldSpec = {
  key: ScalarKey;
  label: string;
  kind: "text" | "textarea" | "number" | "date" | "reference";
  maxLength?: number;
  unit?: string;
  section?: ReferenceSection;
  hint?: string;
  /** Пределы числа — как `gt`/`ge`/`le` схемы API (иначе 422 без русского текста). */
  range?: { min: number; max?: number; minExclusive?: boolean };
};

export const MAX_PERSONNEL = 20;
export const PERSON_LIMITS = { name: 60, position: 100 } as const;
export const SIGNER_LIMITS = { position: 120, organization: 200, name: 120 } as const;
export const APPROVAL_LIMIT = 120;
const DEFAULT_TOLERANCE_M = 0.3;

const text = (key: ScalarKey, label: string, maxLength: number, hint?: string): FieldSpec => ({
  key, label, kind: "text", maxLength, hint,
});
const area = (key: ScalarKey, label: string): FieldSpec => ({ key, label, kind: "textarea", maxLength: 300 });
const number = (key: ScalarKey, label: string, unit: string, range: FieldSpec["range"], hint?: string): FieldSpec => ({
  key, label, kind: "number", unit, range, hint,
});
const POSITIVE = { min: 0, minExclusive: true };

export const FIELD_GROUPS: { title: string; fields: FieldSpec[] }[] = [
  {
    title: "Паспорт",
    fields: [
      text("passport_no", "№ паспорта", 120),
      { key: "passport_date", label: "Дата паспорта", kind: "date" },
    ],
  },
  {
    title: "Объект и блок",
    fields: [
      { key: "site_code", label: "Объект", kind: "reference", section: "sites", maxLength: 80 },
      text("object_name", "Объект в паспорте", 200),
      text("customer", "Заказчик", 200),
      text("block", "Блок", 40, "Из номера блока складываются имена точек для GNSS-приёмника."),
      text("horizon", "Горизонт", 40),
      number("block_area_m2", "Площадь блока", "м²", POSITIVE),
    ],
  },
  {
    title: "Станок",
    fields: [
      { key: "rig_type_code", label: "Тип станка", kind: "reference", section: "equipment_types", maxLength: 80 },
      text("rig_name", "Буровая установка", 80),
      text("rig_number", "№ станка", 40),
      number("bit_diameter_mm", "Диаметр инструмента", "мм", POSITIVE),
      { key: "drilling_start", label: "Начало бурения", kind: "date" },
      { key: "drilling_end", label: "Окончание бурения (план)", kind: "date", hint: "По нормативу станка; правится." },
    ],
  },
  {
    title: "Первый ряд и безопасное расстояние",
    fields: [
      number("alpha_deg", "Угол откоса рабочего уступа α", "°", { min: 30, max: 90 }),
      number("gamma_deg", "Угол устойчивого борта γ", "°", { min: 20, max: 90 }),
      number("bench_height_for_s_m", "Высота уступа для s, Hs", "м", { min: 0, max: 30, minExclusive: true }, "Проектная высота рабочего уступа."),
      number("axis_offset_m", "Вылет оси скважины e", "м", { min: 0, max: 5 }),
    ],
  },
  {
    title: "Порядок работ",
    fields: [
      area("site_preparation", "Подготовка площадки"),
      area("stakeout", "Вынос точек"),
      area("drilling_order", "Порядок обуривания"),
      area("access_route", "Въезд и перегон"),
      area("power_lines", "ЛЭП и кабели"),
      area("adjacent_works", "Совмещённые работы"),
      area("acceptance", "Приёмка блока"),
    ],
  },
  {
    title: "Допуски",
    fields: [
      number("tol_depth_m", "По глубине скважины, ±", "м", { min: 0, max: 2, minExclusive: true }),
      number("tol_collar_m", "По положению устья, ±", "м", { min: 0, max: 2, minExclusive: true }),
    ],
  },
  {
    title: "Тексты паспорта",
    fields: [
      { key: "profile_code", label: "Профиль паспорта", kind: "reference", section: "drill_passport_profiles", maxLength: 80,
        hint: "Тексты мер безопасности и технологии бурения; порядок работ нового паспорта — тоже из профиля объекта. Пусто — тексты формы по умолчанию." },
      { key: "basis", label: "Составлен на основании", kind: "textarea", maxLength: 300 },
    ],
  },
];

export const SIGNERS: { key: SignerKey; label: string }[] = [
  { key: "agreed_by", label: "СОГЛАСОВАНО" },
  { key: "approved_by", label: "УТВЕРЖДАЮ" },
  { key: "compiled_by", label: "Паспорт составил" },
];

const FIELDS = FIELD_GROUPS.flatMap((group) => group.fields);
const REQUIRED_NUMBERS = new Set<ScalarKey>(["tol_depth_m", "tol_collar_m"]);

export type PassportForm = {
  values: Record<ScalarKey, string>;
  signers: Record<SignerKey, DrillSigner>;
  extra_approvals: [string, string];
  personnel: DrillPerson[];
};

function numberText(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value).replace(".", ",");
}

export function parseFormNumber(value: string): number | null {
  const textValue = value.trim().replace(/\s| /g, "").replace(",", ".");
  if (!textValue) return null;
  const parsed = Number(textValue);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formFromPassport(passport: DrillPassport): PassportForm {
  const payload = passport.payload;
  const values = {} as Record<ScalarKey, string>;
  for (const field of FIELDS) {
    if (field.key === "passport_no") values.passport_no = passport.passport_no;
    else if (field.key === "passport_date") values.passport_date = passport.passport_date;
    else if (field.kind === "number") values[field.key] = numberText(payload[field.key] as number | null);
    else values[field.key] = String(payload[field.key] ?? "");
  }
  const approvals = payload.extra_approvals ?? [];
  return {
    values,
    signers: {
      agreed_by: { ...payload.agreed_by },
      approved_by: { ...payload.approved_by },
      compiled_by: { ...payload.compiled_by },
    },
    extra_approvals: [approvals[0] ?? "", approvals[1] ?? ""],
    personnel: payload.personnel.map((person) => ({ ...person })),
  };
}

function rangeText(range: NonNullable<FieldSpec["range"]>): string {
  const low = range.minExclusive ? `Больше ${range.min}` : `Не меньше ${range.min}`;
  if (range.max === undefined) return `${low}.`;
  return range.minExclusive ? `${low} и не больше ${range.max}.` : `От ${range.min} до ${range.max}.`;
}

function outOfRange(value: number, range: NonNullable<FieldSpec["range"]>): boolean {
  if (range.minExclusive ? value <= range.min : value < range.min) return true;
  return range.max !== undefined && value > range.max;
}

/**
 * Ошибки ввода у полей — до отправки на сервер: его 422 по пределам схемы
 * приходит с английскими текстами pydantic, и пользователь не увидел бы, какое
 * из полей неверно. Пределы — как в `DrillingPassportPayload`.
 */
export function formErrors(form: PassportForm): Partial<Record<ScalarKey, string>> {
  const errors: Partial<Record<ScalarKey, string>> = {};
  for (const key of ["passport_no", "passport_date"] as const) {
    if (!form.values[key].trim()) errors[key] = "Заполните.";
  }
  for (const field of FIELDS) {
    if (field.kind !== "number" || !form.values[field.key].trim()) continue;
    const value = parseFormNumber(form.values[field.key]);
    if (value === null) errors[field.key] = "Введите число.";
    else if (field.range && outOfRange(value, field.range)) errors[field.key] = rangeText(field.range);
  }
  return errors;
}

export function toUpdate(form: PassportForm, version: number): DrillPassportUpdate {
  const payload = {} as Record<string, unknown>;
  for (const field of FIELDS) {
    if (field.key === "passport_no" || field.key === "passport_date") continue;
    if (field.kind === "number") {
      const value = parseFormNumber(form.values[field.key]);
      // Пустое число — значение возьмётся из справочника или проекта; допуск — 0,3 м.
      payload[field.key] = value === null && REQUIRED_NUMBERS.has(field.key) ? DEFAULT_TOLERANCE_M : value;
    } else {
      payload[field.key] = form.values[field.key].trim();
    }
  }
  for (const signer of SIGNERS) {
    const value = form.signers[signer.key];
    payload[signer.key] = { position: value.position.trim(), organization: value.organization.trim(), name: value.name.trim() };
  }
  payload.extra_approvals = form.extra_approvals.map((line) => line.trim()).filter(Boolean);
  payload.personnel = form.personnel
    .map((person) => ({ name: person.name.trim(), position: person.position.trim() }))
    .filter((person) => person.name || person.position);
  return {
    passport_no: form.values.passport_no.trim(),
    passport_date: form.values.passport_date,
    payload: payload as DrillPassportPayload,
    expected_version: version,
  };
}

/** Поля «Порядка работ» — их же хранит профиль паспорта (`DrillPassportProfilePayload`). */
export const WORK_ORDER_KEYS = [
  "site_preparation", "stakeout", "drilling_order", "access_route", "power_lines", "adjacent_works", "acceptance",
] as const satisfies readonly ScalarKey[];

/** Порядок работ из профиля: непустой текст профиля заменяет поле, пустой — не трогает. */
export function applyProfileWorkOrder(form: PassportForm, profile: Record<string, unknown> | undefined): PassportForm {
  const values = { ...form.values };
  for (const key of WORK_ORDER_KEYS) {
    const text = typeof profile?.[key] === "string" ? (profile[key] as string).trim() : "";
    if (text) values[key] = text;
  }
  return { ...form, values };
}

export const PROVENANCE_LABEL: Record<Provenance, string> = {
  MANUAL_OVERRIDE: "вручную",
  REFERENCE: "справочник",
  DESIGN: "проект блока",
  CALCULATED: "расчёт",
};

const GROUPED = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 });

function withUnit(value: number, unit: string | undefined): string {
  const textValue = GROUPED.format(value).replace(/ /g, " ");
  if (!unit) return textValue;
  return unit === "°" ? `${textValue}°` : `${textValue} ${unit}`;
}

/** Подсказка пустого поля: какое значение и откуда возьмёт расчёт. */
export function sourceHint(key: ScalarKey, validation: DrillPassportValidation | null): string | null {
  if (!validation) return null;
  const value = validation.inputs[key];
  const source = validation.provenance[key];
  if (value === null || value === undefined || !source) return null;
  const unit = FIELDS.find((field) => field.key === key)?.unit;
  return `${withUnit(value, unit)} · ${PROVENANCE_LABEL[source]}`;
}

export function issuesFor(path: string, issues: DrillPassportIssue[]): DrillPassportIssue[] {
  return issues.filter((issue) => issue.path === path);
}

export type CheckRow = {
  key: "s" | "hs" | "c" | "w";
  label: string;
  value: string;
  status: "ok" | "warn" | "none" | "info";
  note: string;
};

const metres = (value: number | null | undefined, digits = 1) =>
  value === null || value === undefined ? "—" : `${ruNumber(value, digits)} м`;

/**
 * Строки блока «Проверка первого ряда» (доработки 10.11.2026): s, расстояние
 * первого ряда от бровки и ЛСПП у подошвы — по проекту блока; Hs и H₁ — только
 * при предупреждении о высоте уступа.
 */
export function checkRows(validation: DrillPassportValidation): CheckRow[] {
  const check = validation.first_row_check;
  const codes = new Set(validation.issues.map((issue) => issue.code));
  const notMeasured = "нет бровки — не измерить";
  const rows: CheckRow[] = [
    {
      key: "s", label: "Безопасное расстояние s", value: metres(check.s_m),
      status: check.s_m === null ? "none" : "ok",
      note: check.s_m === null ? "нужны углы α и γ" : "печатается в паспорте",
    },
  ];
  if (codes.has("bench_above_design")) {
    rows.push({
      key: "hs", label: "Высота уступа первого ряда, H₁", value: metres(check.h1_m), status: "warn",
      note: `Hs ${metres(check.hs_m)}${check.hs_source ? ` · ${PROVENANCE_LABEL[check.hs_source]}` : ""}`,
    });
  }
  const cLow = check.c_m;
  const cHigh = check.c_max_m ?? check.c_m;
  rows.push({
    key: "c", label: "Первый ряд от бровки",
    value: cLow === null || cLow === undefined ? "—" : Math.abs((cHigh ?? cLow) - cLow) < 0.05 ? metres(cLow) : `${ruNumber(cLow, 1)}…${ruNumber(cHigh ?? cLow, 1)} м`,
    status: cLow === null || cLow === undefined ? "none" : codes.has("first_row_too_close") ? "warn" : "ok",
    note: cLow === null || cLow === undefined ? notMeasured : check.c_min_m === null ? "c_min не посчитан" : `нужно не меньше ${metres(check.c_min_m)} (s − e)`,
  });
  const beyond = codes.has("first_row_beyond_toe");
  const wNote =
    check.w_m === null
      ? codes.has("first_row_burden_not_measured") ? "нет линии подошвы — не посчитать" : notMeasured
      : check.w_max_m === null
        ? "W в проекте не задана — не проверить"
        : `допустимая ${metres(check.w_max_m, 2)} (W проекта + 3 %)`;
  rows.push({
    key: "w", label: "ЛСПП у подошвы", value: check.w_m === null ? "—" : `до ${metres(check.w_m, 2)}`,
    status: beyond || codes.has("first_row_burden") ? "warn" : check.w_m === null || check.w_max_m === null ? "none" : "ok",
    note: beyond ? `${wNote}; есть скважины, которые выходят в откос` : wNote,
  });
  return rows;
}

/**
 * Ключ отметки «просмотрено» — код и текст предупреждения: тот же код с
 * другими числами (W, номера скважин) инженер ещё не видел.
 */
export function ackKey(issue: DrillPassportIssue): string {
  return `${issue.code}\u0000${issue.message}`;
}

/** Ревизию можно выпустить: нет ошибок и все предупреждения отмечены «просмотрено». */
export function canRelease(validation: DrillPassportValidation | null, acknowledged: Set<string>): boolean {
  if (!validation) return false;
  if (validation.issues.some((issue) => issue.level === "error")) return false;
  return validation.issues.every((issue) => issue.level !== "warning" || acknowledged.has(ackKey(issue)));
}
