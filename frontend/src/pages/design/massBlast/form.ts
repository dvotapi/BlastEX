// Форма окна проекта МВ по форме ВМ.09.03 (TASK-018, PR 6): проект ↔ поля
// окна. Числа вводятся с запятой; пустое поле — «не задано» (берётся
// справочник или расчёт), а не 0. Поля, которых окно не правит (обмен с
// прежней формой, план сигналов, уведомления v1), переносятся как есть.
import type { MassBlastGuardPost, MassBlastResponsibility } from "../../../types/design";
import type {
  LayoutPointKind,
  MassBlastExplosives,
  MassBlastIssue,
  MassBlastLayoutPoint,
  MassBlastPerson,
  MassBlastProjectInputV2,
  MassBlastProjectV2,
  MassBlastProtectedObject,
  MassBlastRequisites,
  MassBlastSchedule,
  MassBlastSigner,
} from "../../../types/massBlast";

export const APPROVAL_ROLES = [
  { code: "blast_manager", label: "Ответственный руководитель массового взрыва", position: "Руководитель взрывных работ" },
  { code: "explosives_supervisor", label: "Ответственный за выдачу ВМ", position: "Ответственный за ВМ" },
] as const;
export type ApprovalRole = (typeof APPROVAL_ROLES)[number]["code"];

export const ZONE_KINDS = [
  { code: "people", label: "для людей" },
  { code: "mechanisms", label: "для механизмов" },
  { code: "buildings", label: "для зданий и сооружений" },
] as const;
export type ZoneKind = (typeof ZONE_KINDS)[number]["code"];

export const POINT_KINDS: Array<{ code: LayoutPointKind; label: string }> = [
  { code: "guard_post", label: "Пост охраны" },
  { code: "blast_station", label: "Взрывная станция" },
  { code: "shelter", label: "Укрытие" },
  { code: "gather", label: "Место сбора" },
];

export type SignerForm = { position: string; name: string; authority: string; is_head: "" | "yes" | "no" };
export type BlockForm = {
  design_id: string;
  technical_passport_id: string | null;
  code: string;
  horizon: string;
  rock_text: string;
  hydro_text: string;
  purpose: "" | "MINING" | "STRIPPING";
  area_m2: string;
  hole_notes: Array<{ hole: string; note: string }>;
};
export type ObjectForm = Omit<MassBlastProtectedObject, "distance_m" | "k_ground" | "k_structure"> & {
  distance_m: string;
  k_ground: string;
  k_structure: string;
};
export type PointForm = Omit<MassBlastLayoutPoint, "x" | "y"> & { x: string; y: string };
export type ApprovalForm = { name: string; position: string; code: string; account: string };

export type ProjectForm = {
  name: string;
  object_name: string;
  blast_date: string;
  blast_time: string;
  blocks: BlockForm[];
  requisites: Omit<MassBlastRequisites, "customer_approver" | "contractor_approver"> & {
    customer_approver: SignerForm;
    contractor_approver: SignerForm;
  };
  explosives: Omit<MassBlastExplosives, "bit_mm" | "reaming_k" | "q_tp_kg_m3"> & {
    bit_mm: string;
    reaming_k: string;
    q_tp_kg_m3: string;
  };
  schedule: MassBlastSchedule;
  personnel: Record<string, MassBlastPerson>;
  approvals: Record<ApprovalRole, ApprovalForm>;
  guard_posts: MassBlastGuardPost[];
  objects: ObjectForm[];
  /** Ручные коэффициенты: «» — как в справочнике, «true»/«false» — флажок, иначе число. */
  overrides: Record<string, string>;
  zones: Record<ZoneKind, { value: string; reason: string }>;
  points: PointForm[];
};

/** Поля проекта, которых окно не правит, — переносятся в сохранение как есть. */
type Carried = Pick<
  MassBlastProjectV2,
  "site_code" | "customer_code" | "document_profile_code" | "reference_revision_id" | "charging_schedule" | "signal_plan" | "notifications"
> & { safety_plan: Record<string, unknown> };

const EMPTY_PERSON: MassBlastPerson = { position: "", name: "" };

const text = (value: unknown) => (value === null || value === undefined ? "" : String(value));
/** Число для поля: «1,03» — с запятой, как вводит пользователь. */
export const numberText = (value: unknown) =>
  value === null || value === undefined || value === "" ? "" : String(value).replace(".", ",");

/** Разбор числа поля: «» — null, иначе число (запятая или точка, пробелы — разряды). */
export function parseNumber(value: string): number | null | "invalid" {
  const clean = value.trim().replace(/[\s ]/g, "").replace(",", ".");
  if (!clean) return null;
  const number = Number(clean);
  return Number.isFinite(number) ? number : "invalid";
}

function person(value: Partial<MassBlastPerson> | undefined | null): MassBlastPerson {
  return { position: text(value?.position), name: text(value?.name) };
}

function signer(value: Partial<MassBlastSigner> | undefined | null): SignerForm {
  const head = value?.is_head;
  return { ...person(value), authority: text(value?.authority), is_head: head === true ? "yes" : head === false ? "no" : "" };
}

const SCHEDULE_KEYS: Array<keyof MassBlastSchedule> = [
  "charging_from", "charging_shift_from", "charging_shift_to", "charging_order", "network_order", "station", "shelter",
  "gather", "exit_route", "siren", "measures", "other_conditions", "airblast_buildings", "transport", "cleaning",
  "briefing_date", "szm_start_flank",
];

export function formFromProject(project: MassBlastProjectV2): ProjectForm {
  const requisites = project.requisites ?? {};
  const explosives = project.explosives ?? {};
  const schedule = project.schedule ?? {};
  const personnel: Record<string, MassBlastPerson> = {};
  for (const item of project.personnel ?? []) personnel[item.role_code] = person(item);
  const approvals = Object.fromEntries(
    APPROVAL_ROLES.map((role) => {
      const item = (project.responsibilities ?? []).find((entry) => entry.role_code === role.code);
      return [role.code, {
        name: text(item?.employee_name),
        position: text(item?.position_name) || role.position,
        code: text(item?.employee_code),
        account: text(item?.account_email),
      }];
    }),
  ) as Record<ApprovalRole, ApprovalForm>;
  const manual = ((project.safety_plan ?? {}) as { manual_zones?: Record<string, { value?: unknown; reason?: unknown }> }).manual_zones ?? {};
  const zones = Object.fromEntries(
    ZONE_KINDS.map((zone) => [zone.code, { value: numberText(manual[zone.code]?.value), reason: text(manual[zone.code]?.reason) }]),
  ) as ProjectForm["zones"];
  const overrides: Record<string, string> = {};
  for (const [key, value] of Object.entries(project.safety_overrides ?? {})) {
    if (value === null || value === undefined) continue;
    overrides[key] = typeof value === "boolean" ? String(value) : numberText(value);
  }
  return {
    name: project.name,
    object_name: project.object_name,
    blast_date: project.blast_date,
    blast_time: project.blast_time ?? "",
    blocks: (project.blocks ?? []).map((block) => {
      const details = block.details ?? null;
      return {
        design_id: text(block.design_id),
        technical_passport_id: (block.technical_passport_id as string | null | undefined) ?? null,
        code: text(block.code),
        horizon: text(block.horizon),
        rock_text: text(details?.rock_text),
        hydro_text: text(details?.hydro_text),
        purpose: (details?.purpose ?? "") as BlockForm["purpose"],
        area_m2: numberText(details?.area_m2),
        hole_notes: Object.entries(details?.hole_notes ?? {}).map(([hole, note]) => ({ hole, note })),
      };
    }),
    requisites: {
      project_no: text(requisites.project_no),
      project_date: text(requisites.project_date),
      tp_basis: text(requisites.tp_basis),
      made_by: person(requisites.made_by),
      checked_by: person(requisites.checked_by),
      customer_name: text(requisites.customer_name),
      contractor_name: text(requisites.contractor_name),
      customer_approver: signer(requisites.customer_approver),
      contractor_approver: signer(requisites.contractor_approver),
      agreements: [0, 1].map((index) => person(requisites.agreements?.[index])),
      surveyor_name: text(requisites.surveyor_name),
      drilled_by: (requisites.drilled_by ?? "") as MassBlastRequisites["drilled_by"],
    },
    explosives: {
      bit_mm: numberText(explosives.bit_mm),
      reaming_k: numberText(explosives.reaming_k),
      initiation: text(explosives.initiation),
      scheme: text(explosives.scheme),
      charge_design: text(explosives.charge_design),
      stemming_material: text(explosives.stemming_material),
      starter_product: text(explosives.starter_product),
      q_tp_kg_m3: numberText(explosives.q_tp_kg_m3),
      q_just: text(explosives.q_just),
    },
    schedule: Object.fromEntries(SCHEDULE_KEYS.map((key) => [key, text(schedule[key])])) as MassBlastSchedule,
    personnel,
    approvals,
    guard_posts: (project.guard_posts ?? []).map((post) => ({ ...post })),
    objects: (project.protected_objects ?? []).map((item) => ({
      ...item,
      distance_m: numberText(item.distance_m),
      k_ground: numberText(item.k_ground),
      k_structure: numberText(item.k_structure),
    })),
    overrides,
    zones,
    points: (project.layout_points ?? []).map((point) => ({ ...point, x: numberText(point.x), y: numberText(point.y) })),
  };
}

function carried(project: MassBlastProjectV2): Carried {
  return {
    site_code: project.site_code,
    customer_code: project.customer_code ?? "",
    document_profile_code: project.document_profile_code || "STANDARD",
    reference_revision_id: project.reference_revision_id ?? null,
    charging_schedule: project.charging_schedule ?? [],
    signal_plan: project.signal_plan ?? {},
    notifications: project.notifications ?? [],
    safety_plan: { ...(project.safety_plan ?? {}) },
  };
}

/** Ошибки ввода по пути поля — сохранение с ними не отправляется. */
export function formErrors(form: ProjectForm): Record<string, string> {
  const errors: Record<string, string> = {};
  const number = (path: string, value: string, check?: (n: number) => string) => {
    const parsed = parseNumber(value);
    if (parsed === "invalid") errors[path] = "Введите число";
    else if (parsed !== null && check) {
      const problem = check(parsed);
      if (problem) errors[path] = problem;
    }
  };
  const positive = (n: number) => (n > 0 ? "" : "Больше нуля");
  if (!form.name.trim()) errors.name = "Укажите наименование проекта";
  if (!form.blast_date) errors.blast_date = "Укажите дату взрыва";
  form.blocks.forEach((block, index) => number(`blocks[${index}].details.area_m2`, block.area_m2, positive));
  number("explosives.bit_mm", form.explosives.bit_mm, positive);
  number("explosives.reaming_k", form.explosives.reaming_k, (n) => (n > 0 && n <= 2 ? "" : "От 0 до 2"));
  number("explosives.q_tp_kg_m3", form.explosives.q_tp_kg_m3, (n) => (n > 0 && n <= 10 ? "" : "От 0 до 10 кг/м³"));
  form.objects.forEach((item, index) => {
    number(`protected_objects[${index}].distance_m`, item.distance_m, (n) => (n >= 0 ? "" : "Не меньше нуля"));
    number(`protected_objects[${index}].k_ground`, item.k_ground, positive);
    number(`protected_objects[${index}].k_structure`, item.k_structure, positive);
  });
  for (const [key, value] of Object.entries(form.overrides)) {
    if (value !== "true" && value !== "false") number(`safety_overrides.${key}`, value);
  }
  for (const zone of ZONE_KINDS) {
    const entry = form.zones[zone.code];
    number(`safety_plan.manual_zones.${zone.code}`, entry.value, positive);
    if (entry.value.trim() && !entry.reason.trim()) errors[`safety_plan.manual_zones.${zone.code}`] ??= "Укажите причину";
  }
  form.points.forEach((point, index) => {
    if (parseNumber(point.x) === null || parseNumber(point.x) === "invalid") errors[`layout_points[${index}].x`] = "Введите X";
    if (parseNumber(point.y) === null || parseNumber(point.y) === "invalid") errors[`layout_points[${index}].y`] = "Введите Y";
  });
  form.guard_posts.forEach((post, index) => {
    if (!post.code.trim()) errors[`guard_posts[${index}].code`] = "Укажите № поста";
    if (!post.location.trim()) errors[`guard_posts[${index}].location`] = "Укажите место поста";
  });
  const codes = form.guard_posts.map((post) => post.code.trim()).filter(Boolean);
  if (new Set(codes).size !== codes.length) errors.guard_posts = "Номера постов повторяются";
  for (const role of APPROVAL_ROLES) {
    const item = form.approvals[role.code];
    if (item.account && !item.name.trim()) errors[`responsibilities.${role.code}`] = "Учётка назначается человеку: укажите Ф. И. О.";
  }
  return errors;
}

const num = (value: string): number | null => {
  const parsed = parseNumber(value);
  return parsed === "invalid" ? null : parsed;
};

function signerPayload(value: SignerForm): MassBlastSigner {
  return {
    position: value.position.trim(),
    name: value.name.trim(),
    authority: value.authority.trim(),
    is_head: value.is_head === "yes" ? true : value.is_head === "no" ? false : null,
  };
}

const trimPerson = (value: MassBlastPerson): MassBlastPerson => ({ position: value.position.trim(), name: value.name.trim() });

/** Сохранение проекта: payload `MassBlastProjectInputSchema` (контекст v2). */
export function toInput(form: ProjectForm, project: MassBlastProjectV2): MassBlastProjectInputV2 {
  const base = carried(project);
  const manualZones: Record<string, { value: number | null; reason: string }> = {};
  for (const zone of ZONE_KINDS) {
    const entry = form.zones[zone.code];
    if (entry.value.trim()) manualZones[zone.code] = { value: num(entry.value), reason: entry.reason.trim() };
  }
  const safetyPlan: Record<string, unknown> = { ...base.safety_plan };
  if (Object.keys(manualZones).length) safetyPlan.manual_zones = manualZones;
  else delete safetyPlan.manual_zones;
  const overrides: Record<string, number | boolean | null> = {};
  for (const [key, value] of Object.entries(form.overrides)) {
    if (!value.trim()) continue;
    overrides[key] = value === "true" ? true : value === "false" ? false : num(value);
  }
  const responsibilities: MassBlastResponsibility[] = APPROVAL_ROLES.flatMap((role) => {
    const item = form.approvals[role.code];
    const name = item.name.trim();
    if (!name) return [];
    return [{
      role_code: role.code,
      employee_code: item.code.trim() || name,
      employee_name: name,
      position_name: item.position.trim() || role.position,
      account_email: item.account,
    }];
  });
  return {
    ...base,
    name: form.name.trim(),
    object_name: form.object_name.trim(),
    blast_date: form.blast_date,
    blast_time: form.blast_time,
    blocks: form.blocks.map((block) => ({
      design_id: block.design_id,
      technical_passport_id: block.technical_passport_id,
      code: block.code.trim(),
      horizon: block.horizon.trim(),
      details: {
        rock_text: block.rock_text.trim(),
        hydro_text: block.hydro_text.trim(),
        purpose: block.purpose,
        area_m2: num(block.area_m2),
        hole_notes: Object.fromEntries(
          block.hole_notes.filter((row) => row.hole.trim() && row.note.trim()).map((row) => [row.hole.trim(), row.note.trim()]),
        ),
      },
    })),
    responsibilities,
    safety_plan: safetyPlan,
    guard_posts: form.guard_posts.map((post) => ({
      code: post.code.trim(),
      location: post.location.trim(),
      responsible_employee_code: post.responsible_employee_code.trim(),
      notes: post.notes.trim(),
    })),
    context_version: 2,
    requisites: {
      ...form.requisites,
      project_no: form.requisites.project_no.trim(),
      tp_basis: form.requisites.tp_basis.trim(),
      made_by: trimPerson(form.requisites.made_by),
      checked_by: trimPerson(form.requisites.checked_by),
      customer_name: form.requisites.customer_name.trim(),
      contractor_name: form.requisites.contractor_name.trim(),
      customer_approver: signerPayload(form.requisites.customer_approver),
      contractor_approver: signerPayload(form.requisites.contractor_approver),
      // «Согласовано:» — пусто, строка не печатается.
      agreements: form.requisites.agreements.map(trimPerson).filter((item) => item.name || item.position),
      surveyor_name: form.requisites.surveyor_name.trim(),
    },
    explosives: {
      ...form.explosives,
      bit_mm: num(form.explosives.bit_mm),
      reaming_k: num(form.explosives.reaming_k),
      q_tp_kg_m3: num(form.explosives.q_tp_kg_m3),
    },
    schedule: form.schedule,
    personnel: Object.entries(form.personnel)
      .map(([role_code, item]) => ({ role_code, ...trimPerson(item) }))
      .filter((item) => item.name || item.position),
    protected_objects: form.objects.map((item) => ({
      ...item,
      name: item.name.trim(),
      measures: item.measures.trim(),
      distance_m: num(item.distance_m),
      k_ground: num(item.k_ground),
      k_structure: num(item.k_structure),
    })),
    safety_overrides: overrides,
    layout_points: form.points.map((point) => ({
      kind: point.kind,
      ref: point.ref,
      label: point.label.trim(),
      x: num(point.x) ?? 0,
      y: num(point.y) ?? 0,
    })),
    expected_version: project.version,
  };
}

/** Замечания по префиксу пути поля (`requisites`, `blocks[0]`, …). */
export function issuesFor(prefix: string, issues: MassBlastIssue[]): MassBlastIssue[] {
  return issues.filter((issue) => issue.path === prefix || issue.path.startsWith(`${prefix}.`) || issue.path.startsWith(`${prefix}[`));
}

export { EMPTY_PERSON };

/** Значение поля сохраняемого проекта по пути «a.b.c» (для «Запомнить для объекта»). */
export function valueAt(input: unknown, path: string): string {
  let current: unknown = input;
  for (const part of path.split(".")) {
    if (current === null || typeof current !== "object") return "";
    current = (current as Record<string, unknown>)[part];
  }
  return current === null || current === undefined ? "" : String(current);
}

/** Совпадает ли введённое с тем, что уже в справочнике (числа — по значению). */
export function sameAsReference(own: string, reference: unknown): boolean {
  if (reference === null || reference === undefined || reference === "") return false;
  if (typeof reference === "number") return parseNumber(own) === reference;
  return own.trim() === String(reference).trim();
}
