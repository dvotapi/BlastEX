// Вкладки формы проекта МВ по разделам §5 TASK-018 (PR 6). Поля — payload
// проекта; значения из справочников и расчёта — только из контекста,
// посчитанного сервером (`POST /validate`), подсказкой у пустого поля.
import type { MassBlastAccount } from "../../../types/design";
import type { FieldDescriptor } from "../../references/schemaFields";
import type {
  MassBlastContextV2,
  MassBlastHints,
  MassBlastIssue,
  MassBlastValue,
  ProtectedObjectRow,
} from "../../../types/massBlast";
import { APPROVAL_ROLES, EMPTY_PERSON, issuesFor, ZONE_KINDS, type ObjectForm, type ProjectForm, type SignerForm } from "./form";
import { autoText, Field, Issues, ruNum, SOURCE_LABELS, TextInput, type AutoValue, type RememberControl } from "./ui";

export type TabProps = {
  form: ProjectForm;
  edit: (mutate: (draft: ProjectForm) => void) => void;
  editable: boolean;
  errors: Record<string, string>;
  issues: MassBlastIssue[];
  context: MassBlastContextV2 | null;
  /** Значения по умолчанию полей (сервер, §14 плана PR 6): путь → значение и источник. */
  defaults: Record<string, AutoValue>;
  /** Галочка «Запомнить для объекта» у поля объекта (null — не показывать). */
  remember: (path: string, own: string) => RememberControl | null;
};

/** Пустой вариант списка: значение по умолчанию и его источник, иначе «не указано». */
function autoOption(auto: AutoValue | undefined, labels: Record<string, string>): string {
  const value = autoText(auto);
  if (!value || !auto) return "— не указано —";
  return `${labels[value] ?? value} (${SOURCE_LABELS[auto.source] ?? "автоматически"})`;
}

const PARAM_SOURCE_LABELS: Record<string, string> = {
  REFERENCE: "справочник",
  MANUAL_OVERRIDE: "задано в проекте",
  DESIGN: "проект блока",
  CALCULATED: "расчёт",
  FORM_DEFAULT: "форма v0.11",
};
const sourceLabel = (source: string | undefined) => (source ? PARAM_SOURCE_LABELS[source] ?? "справочник" : "");

const valueText = (value: MassBlastValue) =>
  typeof value.value === "number" ? `${ruNum(value.value, 3)}${value.unit ? ` ${value.unit}` : ""}` : `${value.value ?? "—"}${value.unit ? ` ${value.unit}` : ""}`;

function ValueRows({ items, label }: { items: MassBlastValue[]; label: string }) {
  if (!items.length) return null;
  return (
    <table className="drill-check" aria-label={label}>
      <tbody>
        {items.map((item, index) => (
          <tr key={`${item.label}:${index}`}>
            <th scope="row">{item.label}</th>
            <td>{valueText(item)}</td>
            <td>{[item.substitution, item.note].filter(Boolean).join(" · ")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// --- Реквизиты -------------------------------------------------------------

/** Пустой вариант «технический руководитель»: прошлый проект или справочник объекта. */
function isHeadOption(auto: AutoValue | undefined, computed: boolean | null | undefined): string {
  if (auto && typeof auto.value === "boolean") return `${auto.value ? "да" : "нет"} (${SOURCE_LABELS[auto.source] ?? "автоматически"})`;
  return `как в справочнике${computed === false ? " (нет)" : computed ? " (да)" : ""}`;
}

function SignerFields({
  title,
  prefix,
  value,
  computed,
  disabled,
  issues,
  onChange,
  defaults,
  remember,
}: {
  title: string;
  prefix: string;
  value: SignerForm;
  computed: { position?: string; name?: string; authority?: string; is_head?: boolean | null } | undefined;
  disabled: boolean;
  issues: MassBlastIssue[];
  onChange: (next: SignerForm) => void;
  defaults: Record<string, AutoValue>;
  remember: TabProps["remember"];
}) {
  return (
    <fieldset>
      <legend>{title}</legend>
      <div className="drill-grid">
        <TextInput label="Должность" value={value.position} disabled={disabled} maxLength={200}
          auto={defaults[`${prefix}.position`]} remember={remember(`${prefix}.position`, value.position)}
          onChange={(position) => onChange({ ...value, position })} />
        <TextInput label="Ф. И. О." value={value.name} disabled={disabled} maxLength={200}
          auto={defaults[`${prefix}.name`]} remember={remember(`${prefix}.name`, value.name)}
          onChange={(name) => onChange({ ...value, name })} />
        <Field label="Технический руководитель">
          {(id) => (
            <select id={id} value={value.is_head} disabled={disabled} onChange={(event) => onChange({ ...value, is_head: event.target.value as SignerForm["is_head"] })}>
              <option value="">{isHeadOption(defaults[`${prefix}.is_head`], computed?.is_head)}</option>
              <option value="yes">да</option>
              <option value="no">нет — по доверенности или приказу</option>
            </select>
          )}
        </Field>
        <TextInput label="Основание полномочий (приказ № и дата)" value={value.authority} disabled={disabled} maxLength={200}
          auto={defaults[`${prefix}.authority`]} remember={remember(`${prefix}.authority`, value.authority)}
          onChange={(authority) => onChange({ ...value, authority })} />
      </div>
      <Issues issues={issues} />
    </fieldset>
  );
}

export function RequisitesTab({ form, edit, editable, errors, issues, context, hints, defaults, remember }: TabProps & { hints: MassBlastHints | null }) {
  const req = form.requisites;
  const computed = context?.requisites ?? {};
  const disabled = !editable;
  const previous = hints?.previous_project_no
    ? `№ прошлого проекта объекта: ${hints.previous_project_no}${hints.previous_project_date ? ` от ${hints.previous_project_date.split("-").reverse().join(".")}` : ""}`
    : undefined;
  return (
    <>
      <fieldset>
        <legend>Проект</legend>
        <div className="drill-grid">
          <TextInput label="№ проекта" value={req.project_no} disabled={disabled} maxLength={40} auto={defaults["requisites.project_no"]}
            hint={req.project_no || defaults["requisites.project_no"] ? undefined : previous}
            onChange={(value) => edit((draft) => { draft.requisites.project_no = value; })} />
          <TextInput label="Дата проекта" type="date" value={req.project_date} disabled={disabled} auto={defaults["requisites.project_date"]}
            onChange={(value) => edit((draft) => { draft.requisites.project_date = value; })} />
          <TextInput label="Наименование проекта" value={form.name} disabled={disabled} maxLength={300} error={errors.name} wide
            onChange={(value) => edit((draft) => { draft.name = value; })} />
          <TextInput label="Объект (карьер)" value={form.object_name} disabled={disabled} maxLength={300}
            onChange={(value) => edit((draft) => { draft.object_name = value; })} />
          <TextInput label="Дата взрыва" type="date" value={form.blast_date} disabled={disabled} error={errors.blast_date}
            onChange={(value) => edit((draft) => { draft.blast_date = value; })} />
          <TextInput label="Время взрыва" type="time" value={form.blast_time} disabled={disabled}
            issues={issues.filter((issue) => issue.code === "blast_time_missing")}
            onChange={(value) => edit((draft) => { draft.blast_time = value; })} />
          <TextInput label="Составлен на основании (типовой проект)" value={req.tp_basis} disabled={disabled} maxLength={300} wide
            auto={defaults["requisites.tp_basis"]} remember={remember("requisites.tp_basis", req.tp_basis)}
            onChange={(value) => edit((draft) => { draft.requisites.tp_basis = value; })} />
        </div>
      </fieldset>
      <fieldset>
        <legend>Стороны</legend>
        <div className="drill-grid">
          <TextInput label="Заказчик" value={req.customer_name} disabled={disabled} maxLength={300} auto={defaults["requisites.customer_name"]}
            onChange={(value) => edit((draft) => { draft.requisites.customer_name = value; })} />
          <TextInput label="Подрядчик" value={req.contractor_name} disabled={disabled} maxLength={300} auto={defaults["requisites.contractor_name"]}
            onChange={(value) => edit((draft) => { draft.requisites.contractor_name = value; })} />
          <Field label="Бурение выполнил">
            {(id) => (
              <select id={id} value={req.drilled_by} disabled={disabled}
                onChange={(event) => edit((draft) => { draft.requisites.drilled_by = event.target.value as typeof req.drilled_by; })}>
                <option value="">{autoOption(defaults["requisites.drilled_by"], { CUSTOMER: "заказчик", CONTRACTOR: "Общество" })}</option>
                <option value="CUSTOMER">заказчик</option>
                <option value="CONTRACTOR">Общество (бурит и взрывает один участок — акт готовности не составляется)</option>
              </select>
            )}
          </Field>
          <TextInput label="Маркшейдер — исполнитель съёмки" value={req.surveyor_name} disabled={disabled} maxLength={200}
            auto={defaults["requisites.surveyor_name"]}
            onChange={(value) => edit((draft) => { draft.requisites.surveyor_name = value; })} />
        </div>
      </fieldset>
      <SignerFields title="«СОГЛАСОВАНО» / «УТВЕРЖДАЮ» — технический руководитель заказчика" value={req.customer_approver}
        prefix="requisites.customer_approver" defaults={defaults} remember={remember}
        computed={computed.customer_approver} disabled={disabled} issues={issuesFor("requisites.customer_approver", issues)}
        onChange={(next) => edit((draft) => { draft.requisites.customer_approver = next; })} />
      <SignerFields title="«УТВЕРЖДАЮ» — технический руководитель подрядчика" value={req.contractor_approver}
        prefix="requisites.contractor_approver" defaults={defaults} remember={remember}
        computed={computed.contractor_approver} disabled={disabled} issues={issuesFor("requisites.contractor_approver", issues)}
        onChange={(next) => edit((draft) => { draft.requisites.contractor_approver = next; })} />
      <fieldset>
        <legend>Составил и проверил</legend>
        {(["made_by", "checked_by"] as const).map((key) => (
          <div key={key} className="drill-grid">
            <TextInput label={key === "made_by" ? "Составил — должность" : "Проверил — должность"} value={req[key].position} disabled={disabled} maxLength={200}
              auto={defaults[`requisites.${key}.position`]}
              onChange={(value) => edit((draft) => { draft.requisites[key].position = value; })} />
            <TextInput label="Ф. И. О." value={req[key].name} disabled={disabled} maxLength={200} auto={defaults[`requisites.${key}.name`]}
              onChange={(value) => edit((draft) => { draft.requisites[key].name = value; })} />
          </div>
        ))}
      </fieldset>
      <fieldset>
        <legend>«Согласовано:» (маркшейдер, геолог — на рудных месторождениях; пусто — строка не печатается)</legend>
        {req.agreements.map((item, index) => (
          <div key={index} className="drill-grid">
            <TextInput label="Должность" value={item.position} disabled={disabled} maxLength={200}
              onChange={(value) => edit((draft) => { draft.requisites.agreements[index] = { ...(draft.requisites.agreements[index] ?? EMPTY_PERSON), position: value }; })} />
            <TextInput label="Ф. И. О." value={item.name} disabled={disabled} maxLength={200}
              onChange={(value) => edit((draft) => { draft.requisites.agreements[index] = { ...(draft.requisites.agreements[index] ?? EMPTY_PERSON), name: value }; })} />
          </div>
        ))}
      </fieldset>
      <Issues issues={issues.filter((issue) => issue.path === "requisites")} />
    </>
  );
}

// --- Блоки -----------------------------------------------------------------

export function BlocksTab({ form, edit, editable, errors, issues, context, defaults }: TabProps) {
  const disabled = !editable;
  return (
    <>
      {form.blocks.map((block, index) => {
        const table = context?.blocks_v2?.[index]?.parameter_table;
        const auto = (table?.rows ?? []).filter((row) => row.note && !block.hole_notes.some((note) => note.hole === row.hole_id));
        return (
          <fieldset key={block.design_id}>
            <legend>Блок {block.code || index + 1}</legend>
            <div className="drill-grid">
              <TextInput label="Блок №" value={block.code} disabled={disabled} maxLength={120}
                onChange={(value) => edit((draft) => { draft.blocks[index].code = value; })} />
              <TextInput label="Горизонт" value={block.horizon} disabled={disabled} maxLength={120}
                onChange={(value) => edit((draft) => { draft.blocks[index].horizon = value; })} />
              <Field label="Назначение">
                {(id) => (
                  <select id={id} value={block.purpose} disabled={disabled}
                    onChange={(event) => edit((draft) => { draft.blocks[index].purpose = event.target.value as typeof block.purpose; })}>
                    <option value="">{autoOption(defaults[`blocks[${index}].details.purpose`], { MINING: "добыча", STRIPPING: "вскрыша" })}</option>
                    <option value="MINING">добыча</option>
                    <option value="STRIPPING">вскрыша</option>
                  </select>
                )}
              </Field>
              <TextInput label="Площадь блока, м²" value={block.area_m2} disabled={disabled} inputMode="decimal"
                hint={block.area_m2 ? undefined : "пусто — по маркшейдерскому контуру"} error={errors[`blocks[${index}].details.area_m2`]}
                onChange={(value) => edit((draft) => { draft.blocks[index].area_m2 = value; })} />
              <TextInput label="Порода (текстом)" value={block.rock_text} disabled={disabled} maxLength={300} wide
                auto={defaults[`blocks[${index}].details.rock_text`]}
                onChange={(value) => edit((draft) => { draft.blocks[index].rock_text = value; })} />
              <TextInput label="Гидрогеология (обводнённость)" value={block.hydro_text} disabled={disabled} maxLength={200} wide
                auto={defaults[`blocks[${index}].details.hydro_text`]}
                onChange={(value) => edit((draft) => { draft.blocks[index].hydro_text = value; })} />
            </div>
            <h4>Примечания к скважинам (таблица параметров — только действие, например «снизить заряд»)</h4>
            {block.hole_notes.map((row, noteIndex) => (
              <div key={noteIndex} className="drill-grid drill-person">
                <TextInput label="Скважина №" value={row.hole} disabled={disabled} maxLength={40}
                  onChange={(value) => edit((draft) => { draft.blocks[index].hole_notes[noteIndex].hole = value; })} />
                <TextInput label="Примечание" value={row.note} disabled={disabled} maxLength={200}
                  onChange={(value) => edit((draft) => { draft.blocks[index].hole_notes[noteIndex].note = value; })} />
                {editable && (
                  <button type="button" className="link-button" onClick={() => edit((draft) => { draft.blocks[index].hole_notes.splice(noteIndex, 1); })}>
                    Удалить
                  </button>
                )}
              </div>
            ))}
            {editable && (
              <button type="button" className="secondary-button" onClick={() => edit((draft) => { draft.blocks[index].hole_notes.push({ hole: "", note: "" }); })}>
                Добавить примечание
              </button>
            )}
            {auto.length > 0 && (
              <small className="drill-hint">
                Расчёт сам отметит: {auto.slice(0, 40).map((row) => `скв. ${row.hole_id} — ${row.note}`).join("; ")}
                {auto.length > 40 ? `; … всего ${auto.length}` : ""}
                {table?.common_note ? `. Общее для всех скважин: ${table.common_note}` : ""}
              </small>
            )}
            <Issues issues={issuesFor(`blocks[${index}]`, issues).filter((issue) => !/consumption|technical_calculation|safety/.test(issue.path))} />
          </fieldset>
        );
      })}
    </>
  );
}

// --- ВМ и СИ ---------------------------------------------------------------

export function ExplosivesTab({ form, edit, editable, errors, issues, context, defaults, remember }: TabProps) {
  const ex = form.explosives;
  const disabled = !editable;
  return (
    <>
      <fieldset>
        <legend>Взрывчатые материалы и средства инициирования</legend>
        <div className="drill-grid">
          <TextInput label="Способ инициирования" value={ex.initiation} disabled={disabled} auto={defaults["explosives.initiation"]} maxLength={300} wide
            onChange={(value) => edit((draft) => { draft.explosives.initiation = value; })} />
          <TextInput label="Схема взрывания" value={ex.scheme} disabled={disabled} auto={defaults["explosives.scheme"]} maxLength={300} wide
            hint={context?.network_intervals?.length ? `интервалы сети: ${context.network_intervals.join(", ")}` : undefined}
            onChange={(value) => edit((draft) => { draft.explosives.scheme = value; })} />
          <TextInput label="Конструкция заряда" value={ex.charge_design} disabled={disabled} auto={defaults["explosives.charge_design"]} maxLength={300} wide
            onChange={(value) => edit((draft) => { draft.explosives.charge_design = value; })} />
          <TextInput label="Материал забойки" value={ex.stemming_material} disabled={disabled} auto={defaults["explosives.stemming_material"]} maxLength={120}
            onChange={(value) => edit((draft) => { draft.explosives.stemming_material = value; })} />
          <TextInput label="Марка стартера" value={ex.starter_product} disabled={disabled} auto={defaults["explosives.starter_product"]} maxLength={200}
            onChange={(value) => edit((draft) => { draft.explosives.starter_product = value; })} />
          <TextInput label="Долото, мм" value={ex.bit_mm} disabled={disabled} inputMode="decimal" error={errors["explosives.bit_mm"]}
            auto={defaults["explosives.bit_mm"]}
            hint="только для подписи «долото × k» в техрасчёте" onChange={(value) => edit((draft) => { draft.explosives.bit_mm = value; })} />
          <TextInput label="k разбуривания" value={ex.reaming_k} disabled={disabled} inputMode="decimal" error={errors["explosives.reaming_k"]}
            auto={defaults["explosives.reaming_k"]}
            onChange={(value) => edit((draft) => { draft.explosives.reaming_k = value; })} />
          <TextInput label="q по типовому проекту, кг/м³" value={ex.q_tp_kg_m3} disabled={disabled} inputMode="decimal" error={errors["explosives.q_tp_kg_m3"]}
            auto={defaults["explosives.q_tp_kg_m3"]} remember={remember("explosives.q_tp_kg_m3", ex.q_tp_kg_m3)}
            onChange={(value) => edit((draft) => { draft.explosives.q_tp_kg_m3 = value; })} />
          <TextInput label="Обоснование удельного расхода (при отклонении от ТП больше 10 %)" value={ex.q_just} disabled={disabled} maxLength={600} multiline
            auto={defaults["explosives.q_just"]} remember={remember("explosives.q_just", ex.q_just)}
            onChange={(value) => edit((draft) => { draft.explosives.q_just = value; })} />
        </div>
        <Issues issues={issuesFor("explosives", issues)} />
      </fieldset>
      {(context?.blocks_v2 ?? []).map((block, index) => {
        const section4 = (block.technical_calculation ?? []).find((section) => section.number === "4");
        return (
          <fieldset key={block.design_id || index}>
            <legend>Блок {block.code}: расход ВМ по проекту и параметры БВР (расчёт)</legend>
            <table className="drill-check" aria-label={`Расход ВМ блока ${block.code}`}>
              <thead><tr><th>Наименование</th><th>Количество</th><th>Масса, кг</th></tr></thead>
              <tbody>
                {(block.consumption ?? []).map((line, lineIndex) => (
                  <tr key={`${line.name}:${lineIndex}`}>
                    <th scope="row">{line.name}{line.delay_ms !== null && line.delay_ms !== undefined ? ` (${ruNum(line.delay_ms, 0)} мс)` : ""}</th>
                    <td>{ruNum(line.quantity, 0)} {line.unit}</td>
                    <td>{line.mass_kg === null ? "—" : ruNum(line.mass_kg, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ValueRows items={section4?.items ?? []} label={`Параметры БВР блока ${block.code}`} />
            <Issues issues={issues.filter((issue) => issue.path.startsWith(`blocks[${index}].consumption`) || issue.path.startsWith(`blocks[${index}].technical_calculation`))} />
          </fieldset>
        );
      })}
    </>
  );
}

// --- Безопасность ------------------------------------------------------------

export function SafetyTab({ form, edit, editable, errors, issues, context, fields }: TabProps & { fields: Map<string, FieldDescriptor> | null }) {
  const disabled = !editable;
  const params = context?.blocks_v2?.[0]?.safety?.params ?? {};
  const sources = (params.sources ?? {}) as Record<string, string>;
  const keys = Object.keys(params).filter((key) => key !== "sources" && !Array.isArray(params[key]) && fields?.has(key));
  return (
    <>
      <fieldset>
        <legend>Опасные зоны (расчёт по ФНП 494)</legend>
        <table className="drill-check" aria-label="Опасные зоны">
          <tbody>
            {ZONE_KINDS.map((zone) => {
              const value = context?.zones?.[zone.code];
              return (
                <tr key={zone.code}>
                  <th scope="row">{zone.label}</th>
                  <td>{value ? `${ruNum(Number(value.value), 0)} м` : "—"}</td>
                  <td>{value ? [value.factor, value.substitution, value.basis].filter(Boolean).join(" · ") : ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </fieldset>
      <fieldset>
        <legend>Ручная опасная зона (не меньше расчётной, с причиной)</legend>
        {ZONE_KINDS.map((zone) => (
          <div key={zone.code} className="drill-grid">
            <TextInput label={`Зона ${zone.label}, м`} value={form.zones[zone.code].value} disabled={disabled} inputMode="decimal"
              error={errors[`safety_plan.manual_zones.${zone.code}`]}
              onChange={(value) => edit((draft) => { draft.zones[zone.code].value = value; })} />
            <TextInput label="Причина" value={form.zones[zone.code].reason} disabled={disabled} maxLength={300}
              onChange={(value) => edit((draft) => { draft.zones[zone.code].reason = value; })} />
          </div>
        ))}
        <Issues issues={issuesFor("safety_plan", issues)} />
      </fieldset>
      <fieldset>
        <legend>Коэффициенты расчёта (пусто — как в справочнике объекта)</legend>
        {!fields && <small className="frag-warnings">Каталог справочников не прочитан: коэффициенты правятся в справочнике объекта.</small>}
        <div className="drill-grid">
          {keys.map((key) => {
            const field = fields!.get(key)!;
            const current = params[key];
            const own = form.overrides[key] ?? "";
            const shown = typeof current === "boolean" ? (current ? "да" : "нет") : current === null || current === undefined ? "—" : ruNum(Number(current), 3);
            const hint = `сейчас: ${shown}${field.unit ? ` ${field.unit}` : ""} — ${sourceLabel(sources[key])}`;
            // Поле схемы без заголовка (у крепости пород — только пояснение): подпись — из пояснения, не служебное имя.
            const untitled = field.title === key;
            const title = untitled ? field.description.split(/[;.]/)[0].trim() || key : field.title;
            const note = untitled ? "" : field.description;
            return (
              <Field key={key} label={field.unit ? `${title}, ${field.unit}` : title} hint={note ? `${hint}. ${note}` : hint}
                error={errors[`safety_overrides.${key}`]}>
                {(id) =>
                  typeof current === "boolean" ? (
                    <select id={id} value={own} disabled={disabled} onChange={(event) => edit((draft) => { draft.overrides[key] = event.target.value; })}>
                      <option value="">как в справочнике</option>
                      <option value="true">да</option>
                      <option value="false">нет</option>
                    </select>
                  ) : (
                    <input id={id} inputMode="decimal" value={own} disabled={disabled} placeholder="как в справочнике"
                      onChange={(event) => edit((draft) => { draft.overrides[key] = event.target.value; })} />
                  )
                }
              </Field>
            );
          })}
        </div>
        <Issues issues={issuesFor("safety_overrides", issues)} />
      </fieldset>
      <Issues issues={issues.filter((issue) => /^blocks\[\d+\]\.safety/.test(issue.path))} />
    </>
  );
}

// --- Охраняемые объекты --------------------------------------------------------

const OBJECT_KINDS: Array<{ code: ObjectForm["kind"]; label: string }> = [
  { code: "people", label: "люди" },
  { code: "buildings", label: "здания" },
  { code: "structures", label: "сооружения" },
  { code: "mechanisms", label: "механизмы" },
];

function emptyObject(source: ObjectForm["source"], key = "", name = ""): ObjectForm {
  return { source, key, name, kind: "", distance_m: "", sensitive: false, measures: "", k_ground: "", k_structure: "" };
}

function ObjectNotes({ value, disabled, onChange, prefix, errors }: {
  value: ObjectForm; disabled: boolean; onChange: (next: ObjectForm) => void; prefix: string; errors: Record<string, string>;
}) {
  return (
    <div className="drill-grid">
      <TextInput label="Мероприятия по защите объекта" value={value.measures} disabled={disabled} maxLength={600} multiline
        hint="Печатаются в п. 14 распорядка, когда объект «В ЗОНЕ». Объект в зоне без мероприятий — ошибка проверки."
        onChange={(measures) => onChange({ ...value, measures })} />
      <Field label="Лечебное или детское учреждение (п. 808)">
        {(id) => (
          <input id={id} type="checkbox" checked={value.sensitive} disabled={disabled} onChange={(event) => onChange({ ...value, sensitive: event.target.checked })} />
        )}
      </Field>
      <TextInput label="Свой K_г" value={value.k_ground} disabled={disabled} inputMode="decimal" error={errors[`${prefix}.k_ground`]}
        hint="пусто — как у проекта" onChange={(k_ground) => onChange({ ...value, k_ground })} />
      <TextInput label="Свой K_с" value={value.k_structure} disabled={disabled} inputMode="decimal" error={errors[`${prefix}.k_structure`]}
        hint="пусто — как у проекта" onChange={(k_structure) => onChange({ ...value, k_structure })} />
    </div>
  );
}

export function ObjectsTab({ form, edit, editable, errors, issues, context }: TabProps) {
  const disabled = !editable;
  const rows: ProtectedObjectRow[] = context?.protected_objects ?? [];
  const situation = rows.filter((row) => row.source === "SITUATION");
  function noteIndex(key: string) {
    return form.objects.findIndex((item) => item.source === "SITUATION" && item.key === key);
  }
  return (
    <>
      <fieldset>
        <legend>Объекты в радиусе наибольшей опасной зоны</legend>
        {!rows.length && <small className="drill-hint">Охраняемых объектов в зоне нет.</small>}
        {rows.length > 0 && (
          <table className="drill-check" aria-label="Охраняемые объекты">
            <thead><tr><th>Объект</th><th>Расстояние / безопасное, м</th><th>Оценка</th></tr></thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`${row.key}:${index}`} className={row.position === "В ЗОНЕ" ? "status-warn" : "status-ok"}>
                  <th scope="row">{row.name} ({row.kind_label ?? row.kind}{row.source === "SITUATION" ? ", ситуация карьера" : ""})</th>
                  <td>{ruNum(row.distance_m, 0)} / {ruNum(row.required_m, 0)}</td>
                  <td>{row.position}{row.factor ? ` · ${row.factor}` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </fieldset>
      {situation.map((row) => {
        const index = noteIndex(row.key);
        const value = index >= 0 ? form.objects[index] : emptyObject("SITUATION", row.key, row.name);
        return (
          <fieldset key={row.key}>
            <legend>{row.name} — пометки к объекту ситуации</legend>
            <ObjectNotes value={value} disabled={disabled} errors={errors} prefix={`protected_objects[${index}]`}
              onChange={(next) => edit((draft) => {
                const at = draft.objects.findIndex((item) => item.source === "SITUATION" && item.key === row.key);
                if (at >= 0) draft.objects[at] = next;
                else draft.objects.push(next);
              })} />
          </fieldset>
        );
      })}
      <fieldset>
        <legend>Объекты, добавленные вручную</legend>
        {form.objects.map((item, index) => item.source !== "MANUAL" ? null : (
          <div key={index} className="drill-object">
            <div className="drill-grid">
              <TextInput label="Наименование" value={item.name} disabled={disabled} maxLength={300}
                onChange={(name) => edit((draft) => { draft.objects[index].name = name; })} />
              <Field label="Тип">
                {(id) => (
                  <select id={id} value={item.kind} disabled={disabled} onChange={(event) => edit((draft) => { draft.objects[index].kind = event.target.value as ObjectForm["kind"]; })}>
                    <option value="">— выберите —</option>
                    {OBJECT_KINDS.map((kind) => <option key={kind.code} value={kind.code}>{kind.label}</option>)}
                  </select>
                )}
              </Field>
              <TextInput label="Расстояние от блока, м" value={item.distance_m} disabled={disabled} inputMode="decimal"
                error={errors[`protected_objects[${index}].distance_m`]}
                onChange={(distance_m) => edit((draft) => { draft.objects[index].distance_m = distance_m; })} />
            </div>
            <ObjectNotes value={item} disabled={disabled} errors={errors} prefix={`protected_objects[${index}]`}
              onChange={(next) => edit((draft) => { draft.objects[index] = next; })} />
            {editable && (
              <button type="button" className="link-button" onClick={() => edit((draft) => { draft.objects.splice(index, 1); })}>
                Удалить объект
              </button>
            )}
          </div>
        ))}
        {editable && (
          <button type="button" className="secondary-button" onClick={() => edit((draft) => { draft.objects.push(emptyObject("MANUAL")); })}>
            Добавить объект
          </button>
        )}
      </fieldset>
      <Issues issues={issuesFor("protected_objects", issues)} />
    </>
  );
}

// --- Распорядок ----------------------------------------------------------------

// Подсказка — где пункт печатается и что в него писать: номера пунктов в подписи не понятны.
const SCHEDULE_TEXTS: Array<{ key: keyof ProjectForm["schedule"]; label: string; hint: string; max: number; wide?: boolean }> = [
  { key: "charging_order", label: "Порядок заряжания", max: 300, wide: true,
    hint: "Распорядок, п. 9: в какой последовательности заряжают скважины (например, от вруба к флангам)." },
  { key: "network_order", label: "Порядок монтажа взрывной сети", max: 300, wide: true,
    hint: "Распорядок, п. 10: как и в каком порядке соединяют скважины и когда сеть подключают к магистрали." },
  { key: "station", label: "Место взрывной станции", max: 300,
    hint: "Распорядок, п. 11: откуда подают импульс на взрыв. Точку станции поставьте и на плане (вкладка «Посты и план»)." },
  { key: "shelter", label: "Место укрытия", max: 300,
    hint: "Распорядок, п. 11 (через «/» после станции): где укрываются взрывники во время взрыва." },
  { key: "gather", label: "Место сбора", max: 300,
    hint: "Таблица сигналов, п. 29.2: где собираются люди перед выходом из опасной зоны." },
  { key: "exit_route", label: "Куда удаляются люди", max: 300,
    hint: "Распорядок, п. 21 (строка ответственных за вывод людей): куда выводят людей из запретной и опасной зон." },
  { key: "siren", label: "Средство подачи сигналов", max: 200,
    hint: "Распорядок, п. 27 (строка ответственных за сигналы): чем подают звуковые сигналы — сирена, громкоговоритель и т. п." },
  { key: "transport", label: "Транспорт ВМ", max: 200,
    hint: "Распорядок, п. 19: на чём ВМ доставляют к блоку; сопровождающий — с вкладки «Персонал»." },
  { key: "cleaning", label: "Средства очистки скважин", max: 200,
    hint: "Распорядок, п. 20: чем очищают скважины перед заряжанием; бригада — с вкладки «Персонал»." },
  { key: "measures", label: "Мероприятия по защите охраняемых объектов", max: 600, wide: true,
    hint: "Распорядок, п. 14. Если у объектов «В ЗОНЕ» мероприятия заданы на вкладке «Охраняемые объекты», печатаются они, а это поле — нет. Пусто и объектов в зоне нет — «не требуются»." },
  { key: "other_conditions", label: "Особые условия", max: 600, wide: true,
    hint: "Техрасчёт, разд. 17 «Прочие сведения»: что ещё нужно учесть при этом взрыве (обводнённость, работающее рядом оборудование, мороз и т. п.). Пусто — в разделе только общая фраза о мероприятиях для объектов в зоне." },
  { key: "airblast_buildings", label: "Воздушная волна: вывод по зданиям и сооружениям", max: 300, wide: true,
    hint: "Техрасчёт, разд. 14, строка «На здания и сооружения (пп. 796–801)». Пусто — вывод строится сам по охраняемым объектам; заполняйте, только если нужен свой текст." },
];

export function ScheduleTab({ form, edit, editable, issues, context, defaults, remember }: TabProps) {
  const sch = form.schedule;
  const disabled = !editable;
  const signals = context?.schedule?.signals?.rows ?? [];
  return (
    <>
      <fieldset>
        <legend>Заряжание</legend>
        <div className="drill-grid">
          <TextInput label="Заряжание с (дата)" type="date" value={sch.charging_from} disabled={disabled} auto={defaults["schedule.charging_from"]}
            onChange={(value) => edit((draft) => { draft.schedule.charging_from = value; })} />
          <TextInput label="Смена с" type="time" value={sch.charging_shift_from} disabled={disabled} auto={defaults["schedule.charging_shift_from"]}
            onChange={(value) => edit((draft) => { draft.schedule.charging_shift_from = value; })} />
          <TextInput label="Смена до" type="time" value={sch.charging_shift_to} disabled={disabled} auto={defaults["schedule.charging_shift_to"]}
            onChange={(value) => edit((draft) => { draft.schedule.charging_shift_to = value; })} />
          <TextInput label="Дата инструктажа" type="date" value={sch.briefing_date} disabled={disabled} auto={defaults["schedule.briefing_date"]}
            onChange={(value) => edit((draft) => { draft.schedule.briefing_date = value; })} />
          <Field label="Заходки СЗМ (Г.3) нумеруются с фланга">
            {(id) => (
              <select id={id} value={sch.szm_start_flank} disabled={disabled}
                onChange={(event) => edit((draft) => { draft.schedule.szm_start_flank = event.target.value as typeof sch.szm_start_flank; })}>
                <option value="">по умолчанию</option>
                <option value="left">левого (с откоса вглубь)</option>
                <option value="right">правого (с откоса вглубь)</option>
              </select>
            )}
          </Field>
        </div>
      </fieldset>
      <fieldset>
        <legend>Пункты распорядка</legend>
        <div className="drill-grid">
          {SCHEDULE_TEXTS.map((item) => (
            <TextInput key={item.key} label={item.label} hint={item.hint} value={sch[item.key]} disabled={disabled} maxLength={item.max}
              auto={defaults[`schedule.${item.key}`]} remember={remember(`schedule.${item.key}`, sch[item.key])}
              multiline={item.max > 300} wide={item.wide}
              onChange={(value) => edit((draft) => { (draft.schedule[item.key] as string) = value; })} />
          ))}
        </div>
        <Issues issues={issuesFor("schedule", issues)} />
      </fieldset>
      {signals.length > 0 && (
        <fieldset>
          <legend>Сигналы и время (считается по времени взрыва)</legend>
          <table className="drill-check" aria-label="Сигналы">
            <tbody>
              {signals.map((row) => (
                <tr key={row.point}>
                  <th scope="row">п. {row.point}. {row.action}</th>
                  <td>{row.time ? `${row.not_earlier ? "не ранее " : ""}${row.time}` : "—"}</td>
                  <td>{row.signal}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </fieldset>
      )}
    </>
  );
}

// --- Персонал --------------------------------------------------------------------

function AccountSelect({ id, value, accounts, onChange, disabled }: {
  id: string; value: string; accounts: MassBlastAccount[]; onChange: (value: string) => void; disabled: boolean;
}) {
  const missing = value && !accounts.some((account) => account.email === value);
  return (
    <select id={id} value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled}>
      <option value="">— не назначена —</option>
      {accounts.map((account) => <option key={account.email} value={account.email}>{account.display_name}</option>)}
      {missing && <option value={value}>{value} (нет среди действующих)</option>}
    </select>
  );
}

export function PersonnelTab({ form, edit, editable, errors, issues, context, hints, accounts }: TabProps & {
  hints: MassBlastHints | null; accounts: MassBlastAccount[];
}) {
  const disabled = !editable;
  const roles = hints?.personnel_roles?.length
    ? hints.personnel_roles
    : (context?.personnel ?? []).map((item) => ({ code: item.role_code, label: item.role_label }));
  return (
    <>
      <fieldset>
        <legend>Согласуют ревизию (только назначенная учётка — п. 81 ФНП 494)</legend>
        {APPROVAL_ROLES.map((role) => {
          const item = form.approvals[role.code];
          return (
            <div key={role.code} className="drill-grid">
              <TextInput label={`${role.label} — Ф. И. О.`} value={item.name} disabled={disabled} maxLength={300}
                error={errors[`responsibilities.${role.code}`]}
                onChange={(value) => edit((draft) => { draft.approvals[role.code].name = value; })} />
              <TextInput label="Должность" value={item.position} disabled={disabled} maxLength={300}
                onChange={(value) => edit((draft) => { draft.approvals[role.code].position = value; })} />
              <Field label="Учётка, которая согласует">
                {(id) => (
                  <AccountSelect id={id} value={item.account} accounts={accounts} disabled={disabled}
                    onChange={(value) => edit((draft) => { draft.approvals[role.code].account = value; })} />
                )}
              </Field>
            </div>
          );
        })}
        <Issues issues={issuesFor("responsibilities", issues)} />
      </fieldset>
      <fieldset>
        <legend>Роли распорядка (один человек может занимать несколько)</legend>
        {roles.map((role) => {
          const item = form.personnel[role.code] ?? EMPTY_PERSON;
          return (
            <div key={role.code} className="drill-grid">
              <TextInput label={`${role.label} — должность`} value={item.position} disabled={disabled} maxLength={200}
                onChange={(value) => edit((draft) => { draft.personnel[role.code] = { ...(draft.personnel[role.code] ?? EMPTY_PERSON), position: value }; })} />
              <TextInput label="Ф. И. О." value={item.name} disabled={disabled} maxLength={300}
                onChange={(value) => edit((draft) => { draft.personnel[role.code] = { ...(draft.personnel[role.code] ?? EMPTY_PERSON), name: value }; })} />
            </div>
          );
        })}
        <Issues issues={issuesFor("personnel", issues)} />
      </fieldset>
    </>
  );
}
