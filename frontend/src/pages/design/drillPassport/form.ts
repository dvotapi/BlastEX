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
const number = (key: ScalarKey, label: string, unit: string, hint?: string): FieldSpec => ({
  key, label, kind: "number", unit, hint,
});

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
      number("block_area_m2", "Площадь блока", "м²"),
    ],
  },
  {
    title: "Станок",
    fields: [
      { key: "rig_type_code", label: "Тип станка", kind: "reference", section: "equipment_types", maxLength: 80 },
      text("rig_name", "Буровая установка", 80),
      text("rig_number", "№ станка", 40),
      number("bit_diameter_mm", "Диаметр инструмента", "мм"),
      text("drilling_start", "Начало бурения", 40),
      text("drilling_end", "Окончание бурения", 40),
    ],
  },
  {
    title: "Первый ряд и безопасное расстояние",
    fields: [
      number("alpha_deg", "Угол откоса рабочего уступа α", "°"),
      number("gamma_deg", "Угол устойчивого борта γ", "°"),
      number("bench_height_for_s_m", "Высота уступа для s, Hs", "м", "Проектная высота рабочего уступа."),
      number("axis_offset_m", "Вылет оси скважины e", "м"),
      number("first_row_offset_m", "От бровки до оси первого ряда c", "м"),
      number("w_max_m", "Допустимая ЛСПП Wпред", "м"),
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
      area("adjacent_works", "Соседние работы"),
      area("acceptance", "Приёмка блока"),
    ],
  },
  {
    title: "Допуски",
    fields: [
      number("tol_depth_m", "По глубине скважины, ±", "м"),
      number("tol_collar_m", "По положению устья, ±", "м"),
    ],
  },
  {
    title: "Тексты паспорта",
    fields: [
      { key: "profile_code", label: "Профиль паспорта", kind: "reference", section: "drill_passport_profiles", maxLength: 80,
        hint: "Тексты мер безопасности и технологии бурения; пусто — тексты формы по умолчанию." },
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
const NUMBER_KEYS = FIELDS.filter((field) => field.kind === "number").map((field) => field.key);
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

/** Ошибки ввода у полей: только «не число» — пределы проверяет сервер. */
export function formErrors(form: PassportForm): Partial<Record<ScalarKey, string>> {
  const errors: Partial<Record<ScalarKey, string>> = {};
  for (const key of NUMBER_KEYS) {
    if (form.values[key].trim() && parseFormNumber(form.values[key]) === null) errors[key] = "Введите число.";
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
  key: "s" | "hs" | "h1" | "c_min" | "c" | "w" | "w_max";
  label: string;
  value: string;
  status: "ok" | "warn" | "none" | "info";
  note: string;
};

const metres = (value: number | null, digits = 1) => (value === null ? "—" : `${ruNumber(value, digits)} м`);

/** Строки блока «Проверка первого ряда»: s, Hs, H₁, c_min, c, W, Wпред со статусами. */
export function checkRows(validation: DrillPassportValidation): CheckRow[] {
  const check = validation.first_row_check;
  const codes = new Set(validation.issues.map((issue) => issue.code));
  const offsetSource = validation.provenance.first_row_offset_m;
  const wStatus: CheckRow["status"] =
    check.w_m === null || check.w_max_m === null
      ? codes.has("first_row_tilt_direction_unknown") ? "warn" : "none"
      : codes.has("first_row_burden") || codes.has("first_row_tilt_direction_unknown") ? "warn" : "ok";
  return [
    {
      key: "s", label: "Безопасное расстояние s", value: metres(check.s_m),
      status: check.s_m === null ? "none" : "ok",
      note: check.s_m === null ? "нужны углы α и γ" : "печатается в паспорте",
    },
    {
      key: "hs", label: "Высота уступа для s, Hs", value: metres(check.hs_m),
      status: codes.has("bench_above_design") ? "warn" : check.hs_m === null ? "none" : "info",
      note: check.hs_source ? PROVENANCE_LABEL[check.hs_source] : "",
    },
    { key: "h1", label: "Наибольшая высота первого ряда, H₁", value: metres(check.h1_m), status: check.h1_m === null ? "none" : "info", note: "" },
    {
      key: "c_min", label: "Минимум от бровки до оси, c_min", value: metres(check.c_min_m),
      status: check.c_min_m === null ? "none" : codes.has("axis_offset_missing") || codes.has("axis_offset_exceeds_s") ? "warn" : "info",
      note: codes.has("axis_offset_missing") ? "e не задан — принято 0" : "s − e",
    },
    {
      key: "c", label: "От бровки до оси первого ряда, c", value: metres(check.c_m),
      status: codes.has("first_row_too_close") ? "warn" : check.c_m === null ? "none" : "info",
      note: offsetSource === "MANUAL_OVERRIDE" ? "вручную" : "принято c_min",
    },
    {
      key: "w", label: "ЛСПП у подошвы, W", value: metres(check.w_m, 2), status: wStatus,
      note: codes.has("first_row_tilt_direction_unknown") ? "направление наклона не определено" : "наибольшая по первому ряду",
    },
    {
      key: "w_max", label: "Допустимая ЛСПП, Wпред", value: metres(check.w_max_m, 2),
      status: check.w_max_m === null ? "none" : "info",
      note: check.w_max_m === null ? "не задана — проверка W пропущена" : "вручную",
    },
  ];
}

/** Ревизию можно выпустить: нет ошибок и все предупреждения отмечены «просмотрено». */
export function canRelease(validation: DrillPassportValidation | null, acknowledged: Set<string>): boolean {
  if (!validation) return false;
  if (validation.issues.some((issue) => issue.level === "error")) return false;
  return validation.issues.every((issue) => issue.level !== "warning" || acknowledged.has(issue.code));
}
