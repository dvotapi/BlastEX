// Формы ручного ввода слоёв дня взрыва (TASK-018, PR 6, §6). Поля — схемы
// payload слоёв из api/schemas/mass_blast.py; перенесённое из проекта и
// посчитанное сервером (`seed`, `view`) показывается только для чтения.
import { useEffect, useState } from "react";
import { api } from "../../../../api/endpoints";
import type { MagexAvailability, MagexOption, MassBlastLayer, NaryadChoice, NaryadLine, NaryadOptions } from "../../../../types/massBlast";
import { numberText, parseNumber } from "../form";
import { Field, ruNum, TextInput, type AutoValue, type RememberControl } from "../ui";
import { magexState } from "./MagexPanel";

/** Ручной ввод слоя в окне: числа — текстом, как их вводит пользователь. */
export type LayerDraft = Record<string, unknown>;

const DICTS = ["reserve", "issued", "consumed", "returned"] as const;

export function draftFromPayload(layer: MassBlastLayer): LayerDraft {
  const draft: LayerDraft = { ...layer.payload };
  for (const key of DICTS) {
    const source = (layer.payload[key] ?? {}) as Record<string, number>;
    if (key in layer.payload || layer.kind === "NARYAD") {
      draft[key] = Object.fromEntries(Object.entries(source).map(([line, value]) => [line, numberText(value)]));
    }
  }
  if (layer.kind === "ACCEPTANCE_ACT") draft.accepted_volume_m3 = numberText(layer.payload.accepted_volume_m3);
  if (layer.kind === "EXECUTION") {
    draft.misfired_text = ((layer.payload.misfired_holes ?? []) as string[]).join(", ");
    draft.note_rows = Object.entries((layer.payload.hole_notes ?? {}) as Record<string, string>).map(([hole, note]) => ({ hole, note }));
  }
  return draft;
}

/** Payload слоя для сохранения; ошибки ввода — по ключу поля. */
export function payloadFromDraft(kind: MassBlastLayer["kind"], draft: LayerDraft): { payload: Record<string, unknown>; errors: Record<string, string> } {
  const errors: Record<string, string> = {};
  const payload: Record<string, unknown> = { ...draft };
  for (const key of DICTS) {
    if (!(key in draft)) continue;
    const values: Record<string, number> = {};
    for (const [line, text] of Object.entries((draft[key] ?? {}) as Record<string, string>)) {
      const parsed = parseNumber(String(text ?? ""));
      if (parsed === null) continue;
      if (parsed === "invalid" || parsed < 0) errors[`${key}:${line}`] = "Число не меньше нуля";
      else values[line] = parsed;
    }
    payload[key] = values;
  }
  if (kind === "ACCEPTANCE_ACT") {
    const parsed = parseNumber(String(draft.accepted_volume_m3 ?? ""));
    if (parsed === "invalid" || (typeof parsed === "number" && parsed < 0)) errors.accepted_volume_m3 = "Число не меньше нуля";
    payload.accepted_volume_m3 = typeof parsed === "number" ? parsed : null;
  }
  if (kind === "EXECUTION") {
    payload.misfired_holes = String(draft.misfired_text ?? "")
      // Только явные разделители: код блока может содержать пробел («66 север:1»).
      .split(/[,;\n]+/)
      .map((item) => item.trim())
      .filter(Boolean);
    payload.hole_notes = Object.fromEntries(
      ((draft.note_rows ?? []) as Array<{ hole: string; note: string }>)
        .filter((row) => row.hole.trim() && row.note.trim())
        .map((row) => [row.hole.trim(), row.note.trim()]),
    );
    delete payload.misfired_text;
    delete payload.note_rows;
  }
  return { payload, errors };
}

type FormProps = {
  layer: MassBlastLayer;
  draft: LayerDraft;
  set: (key: string, value: unknown) => void;
  disabled: boolean;
  errors: Record<string, string>;
  afterBlast: boolean;
  /** «Запомнить для объекта» у поля слоя (В8); null — не показывать. */
  remember: (name: string, own: string) => RememberControl | null;
};

type TextProps = Pick<FormProps, "draft" | "set" | "disabled" | "layer" | "remember">;

/** Значения по умолчанию ручного ввода слоя (сервер, `view.defaults`). */
function layerDefaults(layer: MassBlastLayer): Record<string, AutoValue> {
  return ((layer.view ?? {}).defaults ?? {}) as Record<string, AutoValue>;
}

const str = (value: unknown) => (value === null || value === undefined ? "" : String(value));

function Text({ draft, set, disabled, layer, remember, name, label, type, max, wide, hint }: TextProps & {
  name: string; label: string; type?: "date" | "time"; max?: number; wide?: boolean; hint?: string;
}) {
  return (
    <TextInput label={label} value={str(draft[name])} type={type} maxLength={max} wide={wide} hint={hint} disabled={disabled}
      multiline={(max ?? 0) > 300} auto={layerDefaults(layer)[name]} remember={remember(name, str(draft[name]))}
      onChange={(value) => set(name, value)} />
  );
}

function setIn(draft: LayerDraft, set: FormProps["set"], dict: string, key: string, value: string) {
  set(dict, { ...((draft[dict] ?? {}) as Record<string, string>), [key]: value });
}

/** Выбор из списка сервера (склады MagEX, взрывники); пустое — значение по умолчанию. */
function Choice({ layer, draft, set, disabled, name, label, options, empty, hint }: Pick<FormProps, "layer" | "draft" | "set" | "disabled"> & {
  name: string; label: string; options: MagexOption[]; empty: string; hint?: string;
}) {
  const auto = layerDefaults(layer)[name];
  const own = str(draft[name]);
  const known = own && !options.some((option) => option.value === own);
  return (
    <Field label={label} hint={hint} auto={auto} own={own} disabled={disabled}>
      {(id) => (
        <select id={id} value={own} disabled={disabled} onChange={(event) => set(name, event.target.value)}>
          <option value="">{empty}</option>
          {known && <option value={own}>сохранённое значение</option>}
          {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      )}
    </Field>
  );
}

/** Выбор из справочника (взрывники, спецавтомобили): выбор подставляет поля наряда, которые
 * назвал сервер (`fill`); пустое — снять выбор, поля остаются как есть. */
function ChoicePick({ draft, set, disabled, name, label, options, empty, hint }: ChoicePickProps & {
  name: string; label: string; options: NaryadChoice[]; empty: string; hint?: string;
}) {
  const own = str(draft[name]);
  const known = own && !options.some((option) => option.value === own);
  return (
    <Field label={label} hint={hint} disabled={disabled}>
      {(id) => (
        <select id={id} value={own} disabled={disabled} onChange={(event) => {
          const choice = options.find((option) => option.value === event.target.value);
          set(name, event.target.value);
          for (const [key, value] of Object.entries(choice?.fill ?? {})) set(key, value);
        }}>
          <option value="">{empty}</option>
          {known && <option value={own}>выбрано ранее — нет в справочнике</option>}
          {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      )}
    </Field>
  );
}

type ChoicePickProps = Pick<FormProps, "draft" | "set" | "disabled">;

const NO_OPTIONS: NaryadOptions = { warehouses: [], blasters: [], vehicles: [], drivers: [], escorts: [] };

/** Поля MagEX (TASK-018 PR 7): подтверждение допусков. Склад MagEX — от выбранного склада выдачи
 * (справочник «Склады») или реквизитов объекта; здесь он показывается названием. */
function MagexFields({ layer, draft, set, disabled, locked }: TextProps & { locked: (name: string) => boolean }) {
  const [warehouses, setWarehouses] = useState<MagexOption[]>([]);
  useEffect(() => {
    let alive = true;
    api.massBlast.magexWarehouses().then((items) => alive && setWarehouses(items)).catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);
  // Выбран склад из справочника — его склад MagEX, без подстановки склада объекта.
  const picked = Boolean(str(draft.warehouse_code));
  const chosen = str(draft.magex_warehouse_id) || (picked ? "" : str(layerDefaults(layer).magex_warehouse_id?.value));
  const label = warehouses.find((item) => item.value === chosen)?.label;
  return (
    <div className="drill-grid">
      <small className={chosen ? "drill-hint" : "form-error"}>
        {chosen ? `Склад MagEX: ${label ?? "указан"} — с него MagEX резервирует и выдаёт ВМ.`
          : picked ? "У выбранного склада выдачи нет «Склада MagEX» в справочнике «Склады»."
            : "Склад MagEX не задан: укажите его у склада в справочнике «Склады» или в реквизитах объекта."}
      </small>
      <Field label="Допуски взрывника, водителя и спецавтомобиля проверены" hint="подтверждает начальник участка: источника допусков в SafetyMAIN пока нет">
        {(id) => (
          <input id={id} type="checkbox" checked={Boolean(draft.admissions_confirmed)} disabled={disabled || locked("admissions_confirmed")}
            onChange={(event) => set("admissions_confirmed", event.target.checked)} />
        )}
      </Field>
    </div>
  );
}

export function NaryadForm({ layer, draft, set, disabled, errors, afterBlast, remember }: FormProps) {
  const magex = magexState(layer);
  const lockedFields = new Set(magex?.locked_fields ?? []);
  const locked = (name: string) => lockedFields.has(name);
  const online = magex?.mode === "ONLINE";
  const [availability, setAvailability] = useState<MagexAvailability | null>(null);
  const [options, setOptions] = useState<NaryadOptions>(NO_OPTIONS);
  // Списки взрывников и спецавтомобилей — из справочников (сервер называет, что подставить).
  useEffect(() => {
    let alive = true;
    api.massBlast.naryadOptions().then((value) => alive && setOptions({ ...NO_OPTIONS, ...value })).catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);
  // «Доступно на складе» — по сохранённому наряду: при открытии и после каждого сохранения.
  useEffect(() => {
    if (!online) return;
    let alive = true;
    api.massBlast.magexAvailability(layer.id).then((value) => alive && setAvailability(value)).catch(() => alive && setAvailability(null));
    return () => {
      alive = false;
    };
  }, [online, layer.id, layer.version]);
  const common = { draft, set, disabled, layer, remember };
  const lines = ((layer.view.lines ?? []) as NaryadLine[]);
  // «К выдаче» по форме (с несохранённым запасом); у строк одной позиции MagEX — сумма по позиции.
  const toIssueNow = (line: NaryadLine): number | null => {
    const own = ((draft.reserve ?? {}) as Record<string, string>)[line.key];
    const parsed = parseNumber(own ?? "");
    if (typeof parsed === "number") return line.project_qty + parsed;
    return own?.trim() ? null : line.project_qty + line.reserve_qty;
  };
  // Нехватка по позиции MagEX: строки позиции — в её единице учёта (кг ↔ шт по множителю
  // сервера, штуки — вверх до целого), сравнение с доступным в той же единице.
  const shortFor = (key: string): boolean | null => {
    const item = availability?.items?.[key];
    if (!item) return null;
    const group = item.material_id;
    const members = group ? lines.filter((line) => availability?.items?.[line.key]?.material_id === group) : lines.filter((line) => line.key === key);
    let total = 0;
    for (const line of members) {
      const value = toIssueNow(line);
      if (value === null) return null;
      const converted = value * (availability?.items?.[line.key]?.factor ?? 1);
      // Штучная позиция: каждая строка — вверх до целого, как в выписке (`magex_lines`).
      total += item.whole ? Math.ceil(converted - 1e-9) : converted;
    }
    return total > (item.available_magex ?? item.available) + 1e-9;
  };
  const reserve = (draft.reserve ?? {}) as Record<string, string>;
  const issued = (draft.issued ?? {}) as Record<string, string>;
  const consumed = (draft.consumed ?? {}) as Record<string, string>;
  const returned = (draft.returned ?? {}) as Record<string, string>;
  const vvSite = Boolean(draft.vv_site);
  return (
    <>
      <div className="drill-grid">
        <Text {...common} disabled={disabled || locked("number")} name="number" label="№ наряда-путёвки" max={40} />
        <Text {...common} disabled={disabled || locked("issue_date")} name="issue_date" label="Дата выписки" type="date" />
        <ChoicePick draft={draft} set={set} disabled={disabled || locked("warehouse_code")} name="warehouse_code" label="Склад выдачи (справочник)"
          options={options.warehouses} empty="не выбран — из реквизитов объекта"
          hint="справочник «Склады»: подставляет склад и его склад в MagEX" />
        <Text {...common} disabled={disabled || locked("warehouse_code")} name="warehouse" label="Склад выдачи" max={200} />
        <Text {...common} name="permit_number" label="Разрешение на ВР: №" max={200} />
        <Text {...common} name="permit_date" label="Разрешение на ВР: дата" type="date" />
        <ChoicePick draft={draft} set={set} disabled={disabled || locked("blaster_code")} name="blaster_code" label="Взрывник (справочник)"
          options={options.blasters} empty={online ? "по персоналу проекта" : "не выбран — ФИО из персонала проекта"}
          hint="справочник «Взрывники»: подставляет ФИО и индивидуальный индекс" />
        {/* В учёте MagEX индекс — из справочника «Взрывники» (он же в выписке); вне учёта — правится здесь. */}
        <Text {...common} disabled={disabled || online || locked("blaster_index")} name="blaster_index" label="Индивидуальный индекс взрывника" max={40} />
        <ChoicePick draft={draft} set={set} disabled={disabled} name="vehicle_code" label="Спецавтомобиль (справочник)"
          options={options.vehicles} empty="не выбран — из реквизитов объекта"
          hint="справочник «Спецавтомобили ВМ»: подставляет марку, гос. номер и водителя" />
        <Text {...common} name="vehicle_model" label="Спецавтомобиль: марка" max={200} />
        <Text {...common} name="vehicle_plate" label="Спецавтомобиль: гос. номер" max={200} />
        <ChoicePick draft={draft} set={set} disabled={disabled} name="driver_code" label="Водитель (справочник)"
          options={options.drivers} empty="не выбран" hint="справочник «Водители и сопровождающие ВМ»" />
        <Text {...common} name="driver" label="Водитель" max={200} />
        <ChoicePick draft={draft} set={set} disabled={disabled} name="escort_code" label="Сопровождающее лицо (справочник)"
          options={options.escorts} empty="не выбрано" hint="подставляет ФИО в «Лица, привлекаемые к доставке»; ещё — через «;»" />
        <Text {...common} name="delivery" label="Лица, привлекаемые к доставке" max={300} />
        <Field label="ВВ изготавливаются на месте (СЗМ)" hint="возврата ВВ нет: остаток заряжается в крайние скважины">
          {(id) => <input id={id} type="checkbox" checked={vvSite} disabled={disabled} onChange={(event) => set("vv_site", event.target.checked)} />}
        </Field>
      </div>
      {magex && <MagexFields {...common} locked={locked} />}
      <table className="drill-check mb-naryad" aria-label="ВМ наряда-путёвки">
        <thead>
          <tr>
            <th>ВМ</th><th>По проекту</th><th>Запас</th><th>К выдаче</th>
            {online && <th>Доступно на складе</th>}
            {afterBlast && <><th>Выдано</th><th>Израсходовано</th><th>Возвращено</th></>}
          </tr>
        </thead>
        <tbody>
          {lines.map((line) => {
            const own = reserve[line.key];
            const parsed = parseNumber(own ?? "");
            // Очищенный ручной запас: значение справочника станет известно после сохранения.
            const cleared = own !== undefined && !own.trim() && line.reserve_source === "MANUAL_OVERRIDE";
            const extra = typeof parsed === "number" ? parsed : own?.trim() || cleared ? null : line.reserve_qty;
            // Килограммы — до 0,1 кг, штуки — целые (как в печатной форме).
            const digits = line.unit === "кг" ? 1 : 3;
            const toIssue = extra === null ? "—" : ruNum(line.project_qty + extra, digits);
            const noReturn = vvSite && line.kind === "explosive";
            return (
              <tr key={line.key}>
                <th scope="row">
                  {line.name}{line.delay_ms !== null && line.delay_ms !== undefined ? ` (${ruNum(line.delay_ms, 0)} мс)` : ""}, {line.unit}
                  {line.outside_project ? " — вне проекта" : ""}
                </th>
                <td>{ruNum(line.project_qty, digits)}</td>
                <td>
                  <input aria-label={`Запас: ${line.name}`} inputMode="decimal" value={own ?? ""} disabled={disabled || line.outside_project || locked("reserve")}
                    placeholder={line.reserve_source === "MANUAL_OVERRIDE" ? "как в справочнике" : line.reserve_qty ? `${ruNum(line.reserve_qty, 3)} (справочник)` : "0"}
                    onChange={(event) => setIn(draft, set, "reserve", line.key, event.target.value)} />
                  {errors[`reserve:${line.key}`] && <small className="form-error">{errors[`reserve:${line.key}`]}</small>}
                </td>
                <td title={extra === null ? "пересчитается после сохранения" : undefined}>{toIssue}</td>
                {online && <AvailableCell availability={availability} line={line} short={shortFor(line.key)} digits={digits} />}
                {afterBlast && (
                  <>
                    <td>
                      <input aria-label={`Выдано: ${line.name}`} inputMode="decimal"
                        value={line.issued_source === "MAGEX" ? magexValue(line.issued_qty) : issued[line.key] ?? ""}
                        disabled={disabled || line.issued_source === "MAGEX"}
                        placeholder={line.issued_source === "MAGEX" && line.issued_qty !== null && line.issued_qty !== undefined ? `${ruNum(line.issued_qty, 3)} (MagEX)` : ""}
                        onChange={(event) => setIn(draft, set, "issued", line.key, event.target.value)} />
                    </td>
                    <td>
                      <input aria-label={`Израсходовано: ${line.name}`} inputMode="decimal"
                        value={line.consumed_source === "MAGEX" ? magexValue(line.consumed_qty) : consumed[line.key] ?? ""}
                        disabled={disabled || line.consumed_source === "MAGEX"}
                        placeholder={line.consumed_qty === null || line.consumed_qty === undefined ? "" : `${ruNum(line.consumed_qty, 3)} (${line.consumed_source === "MAGEX" ? "MagEX" : "факт"})`}
                        onChange={(event) => setIn(draft, set, "consumed", line.key, event.target.value)} />
                    </td>
                    <td>
                      {noReturn ? "—" : (
                        <input aria-label={`Возвращено: ${line.name}`} inputMode="decimal"
                          value={line.returned_source === "MAGEX" ? magexValue(line.returned_qty) : returned[line.key] ?? ""}
                          disabled={disabled || line.returned_source === "MAGEX"}
                          placeholder={line.returned_qty === null || line.returned_qty === undefined ? "" : `${ruNum(line.returned_qty, 3)} (${line.returned_source === "MAGEX" ? "MagEX" : "выдано − израсходовано"})`}
                          onChange={(event) => setIn(draft, set, "returned", line.key, event.target.value)} />
                      )}
                    </td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
      {online && availability && (
        <small className={availability.error ? "frag-warnings" : "drill-hint"}>
          {availability.error
            ? `«Доступно на складе»: ${availability.error}`
            : `Доступно на складе — годный остаток минус резервы других нарядов${availability.calculated_at ? ` на ${new Date(availability.calculated_at).toLocaleString("ru-RU")}` : ""}; по сохранённому наряду.`}
        </small>
      )}
      <small className="drill-hint">
        Запас добавляет менеджер на случай, если понадобится; «к выдаче» = по проекту + запас. Расчёты проекта
        (опасные зоны, Q_э, сейсмика) запас не меняет. Больше ВМ после выдачи — новая наряд-путёвка, а не правка этой.
      </small>
    </>
  );
}

/** Значение графы после взрыва из MagEX — в поле, а не подсказкой: ручной ввод закрыт. */
function magexValue(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : ruNum(value, 3);
}

/** Графа «Доступно на складе»: в единице строки; нехватка — по выписанному сейчас в форме. */
function AvailableCell({ availability, line, short: computed, digits }: {
  availability: MagexAvailability | null; line: NaryadLine; short: boolean | null; digits: number;
}) {
  const item = availability?.items?.[line.key];
  if (!item) return <td>—</td>;
  // Нехватка — по всей позиции MagEX (сумма строк в её единице), как её проверит MagEX.
  const short = computed === null ? item.short : computed;
  return (
    <td className={short ? "form-error" : undefined} title={item.shared ? "одна позиция MagEX на несколько строк наряда" : undefined}>
      {ruNum(item.available, digits)}{short ? " — не хватает" : ""}{item.shared ? " *" : ""}
    </td>
  );
}

export function NotificationForm({ layer, draft, set, disabled, remember }: FormProps) {
  const common = { draft, set, disabled, layer, remember };
  const registry = (layer.seed.addressee ?? {}) as Record<string, unknown>;
  const fromRegistry = Object.keys(registry).length > 0;
  return (
    <>
      {fromRegistry ? (
        <small className="drill-hint">
          Адресат — из справочника уведомлений карьера: {[registry.recipient_position, registry.recipient_name].filter(Boolean).join(" ")}
        </small>
      ) : (
        <div className="drill-grid">
          <Text {...common} name="recipient_position" label="Адресат — должность, орган" max={300} />
          <Text {...common} name="recipient_name" label="Адресат — фамилия, инициалы (дательный падеж)" max={120} />
          <Text {...common} name="salutation" label="Обращение" max={200} />
        </div>
      )}
      <div className="drill-grid">
        <Text {...common} name="out_no" label="Исх. №" max={40} />
        <Text {...common} name="out_date" label="Дата" type="date" />
        {/* Подписант из справочника уведомлений печатается всегда — поле только для показа. */}
        {fromRegistry && str(registry.signer) ? (
          <Field label="Подписывает" hint="из справочника уведомлений карьера">
            {(id) => <input id={id} value={str(registry.signer)} disabled readOnly />}
          </Field>
        ) : (
          <Text {...common} name="signer" label="Подписывает" max={200} />
        )}
      </div>
    </>
  );
}

export function ReadinessForm({ layer, draft, set, disabled, remember }: FormProps) {
  const common = { draft, set, disabled, layer, remember };
  const conditions = (layer.seed.conditions ?? []) as string[];
  const marks = (draft.conditions ?? {}) as Record<string, boolean | null>;
  return (
    <>
      <div className="drill-grid">
        <Text {...common} name="act_date" label="Дата составления акта" type="date" />
        <Text {...common} name="handed_by" label="Блок передал (должность, Ф. И. О.)" max={200} />
        <Text {...common} name="accepted_by" label="Блок принял (должность, Ф. И. О.)" max={200} />
        <Field label="Заключение">
          {(id) => (
            <select id={id} value={str(draft.conclusion)} disabled={disabled} onChange={(event) => set("conclusion", event.target.value)}>
              <option value="">— не отмечено —</option>
              <option value="READY">готов</option>
              <option value="NOT_READY">не готов</option>
            </select>
          )}
        </Field>
        <Field label="Исполнительная съёмка блока выполнена и передана (маркшейдер)">
          {(id) => <input id={id} type="checkbox" checked={Boolean(draft.survey_handed_over)} disabled={disabled} onChange={(event) => set("survey_handed_over", event.target.checked)} />}
        </Field>
      </div>
      <table className="drill-check" aria-label="Условия готовности">
        <tbody>
          {conditions.map((condition, index) => {
            const key = String(index + 1);
            const mark = marks[key];
            return (
              <tr key={key}>
                <th scope="row">{index + 1}. {condition}</th>
                <td>
                  <select aria-label={`Условие ${index + 1}`} value={mark === true ? "yes" : mark === false ? "no" : ""} disabled={disabled}
                    onChange={(event) => set("conditions", { ...marks, [key]: event.target.value === "yes" ? true : event.target.value === "no" ? false : null })}>
                    <option value="">—</option>
                    <option value="yes">да</option>
                    <option value="no">нет</option>
                  </select>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <Text {...common} name="remarks" label="Замечания" max={1000} wide />
    </>
  );
}

export function TalonForm({ layer, draft, set, disabled, remember }: FormProps) {
  const common = { draft, set, disabled, layer, remember };
  const notBefore = str(layer.view.admittance_not_before);
  const source = layer.view.admittance_source === "FACT" ? "по фактическому времени взрыва" : "по проектному времени взрыва";
  return (
    <>
      <div className="drill-grid">
        <Text {...common} name="fired_date" label="Взрыв произведён — дата" type="date" />
        <Text {...common} name="fired_time" label="Взрыв произведён — время" type="time" />
        <Text {...common} name="issued_date" label="Дата выдачи талона" type="date" />
        <Text {...common} name="issued_time" label="Время выдачи" type="time" />
        <Text {...common} name="issued_by" label="Выдал" max={200} />
        <Text {...common} name="received_by" label="Получил" max={200} />
      </div>
      {notBefore && (
        <small className="drill-hint">
          Допуск не ранее {notBefore}{layer.view.admittance_date ? ` ${str(layer.view.admittance_date).split("-").reverse().join(".")}` : ""} — {source}, + 30 мин (п. 422). Пересчитывается после сохранения.
        </small>
      )}
    </>
  );
}

export function AcceptanceForm({ layer, draft, set, disabled, errors, remember }: FormProps) {
  const common = { draft, set, disabled, layer, remember };
  const fact = (layer.view.fact ?? {}) as { basis?: string; explosive_kg?: number; q_kg_m3?: number | null; volume_basis?: string };
  const contour = layer.seed.volume_contour_m3 as number | null | undefined;
  return (
    <>
      <div className="drill-grid">
        <Text {...common} name="act_date" label="Дата акта" type="date" />
        <Text {...common} name="contract_no" label="Договор №" max={80} />
        <Text {...common} name="contract_date" label="Дата договора" type="date" />
        <Text {...common} name="appendix_no" label="Приложение №" max={20} />
        <Text {...common} name="customer_person" label="Ответственное лицо заказчика" max={300} />
        <TextInput label="К оплате по технологическому взрыванию, м³" value={str(draft.accepted_volume_m3)} inputMode="decimal" disabled={disabled}
          error={errors.accepted_volume_m3}
          hint={contour ? `объём по маркшейдерскому контуру: ${ruNum(contour, 0)} м³` : undefined}
          onChange={(value) => set("accepted_volume_m3", value)} />
      </div>
      <Text {...common} name="remarks" label="Особые замечания" max={1000} wide />
      <small className="drill-hint">
        {fact.basis === "FACT"
          ? `Параметры — по факту: расход ВВ ${ruNum(fact.explosive_kg, 0)} кг, удельный расход ${ruNum(fact.q_kg_m3 ?? null, 2)} кг/м³ (${fact.volume_basis === "ACCEPTED" ? "к объёму к оплате" : "к объёму по контуру"}).`
          : "Параметры — по проекту: слой «Факт» не выпущен."}
        {" "}Пустые реквизиты договора берутся из справочника объекта.
      </small>
    </>
  );
}

export function ExecutionForm({ layer, draft, set, disabled, remember }: FormProps) {
  const common = { draft, set, disabled, layer, remember };
  const blocks = (layer.view.blocks ?? []) as Array<{ code: string; parameter_table: { rows: Array<Record<string, unknown>> } }>;
  const rows = (draft.note_rows ?? []) as Array<{ hole: string; note: string }>;
  const multi = blocks.length > 1;
  return (
    <>
      <div className="drill-grid">
        <Text {...common} name="blast_date" label="Дата взрыва по факту" type="date" />
        <Text {...common} name="blast_time" label="Время взрыва по факту" type="time" />
        <TextInput label={multi ? "Отказы — «блок:номер» через запятую" : "Отказы — номера скважин через запятую"} value={str(draft.misfired_text)} disabled={disabled}
          wide hint="пусто — отказов нет" onChange={(value) => set("misfired_text", value)} />
      </div>
      <h4>Примечания по факту к скважинам</h4>
      {rows.map((row, index) => (
        <div key={index} className="drill-grid drill-person">
          <TextInput label={multi ? "Скважина (блок:номер)" : "Скважина №"} value={row.hole} disabled={disabled} maxLength={40}
            onChange={(value) => set("note_rows", rows.map((item, at) => (at === index ? { ...item, hole: value } : item)))} />
          <TextInput label="Примечание" value={row.note} disabled={disabled} maxLength={200}
            onChange={(value) => set("note_rows", rows.map((item, at) => (at === index ? { ...item, note: value } : item)))} />
          {!disabled && (
            <button type="button" className="link-button" onClick={() => set("note_rows", rows.filter((_, at) => at !== index))}>Удалить</button>
          )}
        </div>
      ))}
      {!disabled && (
        <button type="button" className="secondary-button" onClick={() => set("note_rows", [...rows, { hole: "", note: "" }])}>
          Добавить примечание
        </button>
      )}
      {blocks.map((block) => {
        const total = block.parameter_table.rows.length;
        // Пробурена — есть запись факта (`drilled`): у съёмки без замера глубины глубины Ф нет.
        const drilled = block.parameter_table.rows.filter(
          (row) => row.drilled === true || (row.depth_fact_m !== null && row.depth_fact_m !== undefined),
        ).length;
        const charged = block.parameter_table.rows.filter((row) => row.charged).length;
        return (
          <small key={block.code} className="drill-hint">
            Блок {block.code}: факт бурения — {drilled} из {total}, заряжания — {charged} из {total} скважин. Факт вводится в
            панелях «Факт бурения / заряжания» «Проектирования».
          </small>
        );
      })}
    </>
  );
}

export const LAYER_FORMS = {
  NARYAD: NaryadForm,
  NOTIFICATION: NotificationForm,
  READINESS_ACT: ReadinessForm,
  TALON: TalonForm,
  ACCEPTANCE_ACT: AcceptanceForm,
  EXECUTION: ExecutionForm,
} as const;
