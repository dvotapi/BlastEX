// Окно «Паспорт на бурение» (TASK-015, PR 6). Слева — форма полей паспорта
// (§3 спеки) с источником подставленных значений, справа — «Проверка первого
// ряда» для инженера, замечания с отметкой «просмотрено», выпуск ревизии и
// предпросмотр черновика. Расчёт и проверку делает сервер; окно показывает
// ответ и не показывает JSON. Паспорт строится по сохранённому проекту блока.
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent, type SyntheticEvent } from "react";
import { fetchBlob } from "../../../api/client";
import { api } from "../../../api/endpoints";
import type { DrillPassport, DrillPassportIssue, DrillPassportValidation } from "../../../types/drillPassport";
import type { EconomicsReferenceItem, EconomicsReferenceSnapshot } from "../../../types/economics";
import { DrillPassportHelp } from "./DrillPassportHelp";
import {
  ackKey,
  APPROVAL_LIMIT,
  canRelease,
  checkRows,
  FIELD_GROUPS,
  formErrors,
  formFromPassport,
  issuesFor,
  MAX_PERSONNEL,
  PERSON_LIMITS,
  SIGNER_LIMITS,
  SIGNERS,
  sourceHint,
  toUpdate,
  type FieldSpec,
  type PassportForm,
  type ReferenceSection,
  type ScalarKey,
} from "./form";

const CONFLICT_MESSAGE =
  "Паспорт изменён в другом окне или другим пользователем. Загрузите сохранённый паспорт — правки этого окна пропадут.";
const isConflict = (reason: unknown) => (reason as { status?: number } | null)?.status === 409;

const STATUS_LABEL: Record<DrillPassport["status"], string> = {
  draft: "черновик",
  approved: "утверждён",
  drilled: "пробурен",
  accepted: "принят",
};

// Величины, у которых сервер называет источник (`provenance`).
const SOURCED = new Set<ScalarKey>([
  "alpha_deg", "gamma_deg", "axis_offset_m", "bench_height_for_s_m", "first_row_offset_m", "w_max_m", "block_area_m2",
]);

function referenceOptions(snapshot: EconomicsReferenceSnapshot, section: ReferenceSection): EconomicsReferenceItem[] {
  return (snapshot.sections[section] ?? []).filter(
    (item) => item.is_active && (section !== "equipment_types" || !item.payload?.kind || item.payload.kind === "DRILL_RIG"),
  );
}

/** Подпись записи справочника — название; код — только у одинаковых названий. */
function optionLabels(items: EconomicsReferenceItem[]): Map<string, string> {
  const counts = new Map<string, number>();
  for (const item of items) counts.set(item.name, (counts.get(item.name) ?? 0) + 1);
  return new Map(items.map((item) => [item.code, (counts.get(item.name) ?? 0) > 1 ? `${item.name} (${item.code})` : item.name || item.code]));
}

function errorText(reason: unknown, fallback: string): string {
  return reason instanceof Error && reason.message ? reason.message : fallback;
}

export function DrillPassportDialog({
  passport,
  designSaved,
  onClose,
  onChange,
}: {
  passport: DrillPassport;
  designSaved: boolean;
  onClose: () => void;
  onChange: (passport: DrillPassport) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [current, setCurrent] = useState(passport);
  const [form, setForm] = useState<PassportForm>(() => formFromPassport(passport));
  const [dirty, setDirty] = useState(false);
  const [validation, setValidation] = useState<DrillPassportValidation | null>(null);
  const [acknowledged, setAcknowledged] = useState<Set<string>>(new Set());
  // null — справочники ещё читаются, false — не прочитаны (коды вводятся текстом).
  const [references, setReferences] = useState<EconomicsReferenceSnapshot | null | false>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState("");
  // Сохранение или выпуск получили 409 по версии: окно предлагает загрузить паспорт заново.
  const [conflict, setConflict] = useState(false);
  const previewRef = useRef<string | null>(null);
  const alive = useRef(true);

  const errors = useMemo(() => formErrors(form), [form]);
  const issues = validation?.issues ?? [];
  const warnings = issues.filter((issue) => issue.level === "warning");
  const editable = current.status === "draft";
  // Ошибки проверки — у сохранённого паспорта. Правки формы могли их
  // исправить: предпросмотр и выпуск сами сохраняют форму и проверяют заново.
  const hasErrors = !dirty && issues.some((issue) => issue.level === "error");
  const locked = !editable || busy;
  const releasable =
    editable && designSaved && !busy && !conflict && Object.keys(errors).length === 0 &&
    (dirty ? validation !== null : canRelease(validation, acknowledged));

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  useEffect(() => {
    alive.current = true;
    api.economics
      .referenceSnapshot()
      .then((snapshot) => alive.current && setReferences(snapshot))
      .catch(() => alive.current && setReferences(false));
    // Только при открытии окна: дальше проверку перечитывают сохранение и выпуск.
    void refreshValidation(passport.id);
    return () => {
      alive.current = false;
      if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refreshValidation(id: string): Promise<DrillPassportValidation | null> {
    try {
      const result = await api.drillPassport.validate(id);
      setValidation(result);
      // Отметка живёт, пока предупреждение с тем же текстом есть: пропавшее,
      // вернувшееся или с другими числами — отмечается заново.
      const keys = new Set(result.issues.filter((issue) => issue.level === "warning").map(ackKey));
      setAcknowledged((previous) => new Set([...previous].filter((key) => keys.has(key))));
      return result;
    } catch (reason) {
      setMessage(errorText(reason, "Не удалось проверить паспорт."));
      return null;
    }
  }

  function setValue(key: ScalarKey, value: string) {
    setForm((previous) => ({ ...previous, values: { ...previous.values, [key]: value } }));
    setDirty(true);
  }

  function updateForm(change: (previous: PassportForm) => PassportForm) {
    setForm(change);
    setDirty(true);
  }

  // Сохранение и сразу проверка сохранённого: правка формы (объект, углы,
  // блок) меняет и s, и замечания — старая проверка справа была бы неверной.
  async function save(): Promise<{ passport: DrillPassport; validation: DrillPassportValidation | null } | null> {
    if (Object.keys(errors).length) {
      setMessage("Исправьте поля, отмеченные ошибкой.");
      return null;
    }
    let saved: DrillPassport;
    try {
      saved = await api.drillPassport.save(current.id, toUpdate(form, current.version));
    } catch (reason) {
      if (isConflict(reason)) setConflict(true);
      setMessage(isConflict(reason) ? CONFLICT_MESSAGE : errorText(reason, "Не удалось сохранить паспорт."));
      return null;
    }
    setCurrent(saved);
    setForm(formFromPassport(saved));
    setDirty(false);
    onChange(saved);
    return { passport: saved, validation: await refreshValidation(saved.id) };
  }

  // Загрузить паспорт с сервера заново (после конфликта версий).
  async function onReload() {
    setBusy(true);
    try {
      const fresh = await api.drillPassport.get(current.id);
      setCurrent(fresh);
      setForm(formFromPassport(fresh));
      setDirty(false);
      setConflict(false);
      onChange(fresh);
      setMessage("Загружен сохранённый паспорт.");
      await refreshValidation(fresh.id);
    } catch (reason) {
      setMessage(errorText(reason, "Не удалось загрузить паспорт."));
    } finally {
      setBusy(false);
    }
  }

  async function onSave() {
    setBusy(true);
    setMessage("");
    if (await save()) setMessage("Черновик паспорта сохранён.");
    setBusy(false);
  }

  async function onRelease() {
    setBusy(true);
    setMessage("");
    try {
      const result = dirty ? await save() : { passport: current, validation: await refreshValidation(current.id) };
      if (!result) return;
      const { passport: saved, validation: checked } = result;
      if (!checked) return;
      if (checked.issues.some((issue) => issue.level === "error")) {
        setMessage("Ревизию не выпустить: исправьте ошибки проверки.");
        return;
      }
      if (!canRelease(checked, acknowledged)) {
        setMessage("Отметьте просмотренными новые предупреждения проверки.");
        return;
      }
      const codes = checked.issues.filter((issue) => issue.level === "warning").map((issue) => issue.code);
      const previous = current.current_revision_id;
      const revision = await api.drillPassport.createRevision(saved.id, {
        expected_version: saved.version,
        acknowledged_warnings: [...new Set(codes)],
      });
      setMessage(
        revision.id === previous
          ? `Паспорт не изменился с ревизии № ${revision.revision_no} — новая не выпущена.`
          : `Ревизия № ${revision.revision_no} выпущена: документы — на панели «Паспорт на бурение».`,
      );
      // Выпуск меняет версию черновика; не прочитался — панель перечитает паспорт при закрытии окна.
      const updated = await api.drillPassport.get(saved.id).catch(() => null);
      if (updated) {
        setCurrent(updated);
        onChange(updated);
      } else {
        setConflict(true);
      }
    } catch (reason) {
      if (isConflict(reason)) {
        const checked = await refreshValidation(current.id);
        const pending = checked?.issues.some((issue: DrillPassportIssue) => issue.level === "warning" && !acknowledged.has(ackKey(issue)));
        const fresh = pending ? null : await api.drillPassport.get(current.id).catch(() => null);
        if (pending) {
          setMessage("Отметьте просмотренными новые предупреждения проверки.");
        } else if (fresh && fresh.status !== "draft") {
          // 409 «только из черновика»: паспорт уже утверждён — правки и выпуск закрыты.
          setCurrent(fresh);
          setForm(formFromPassport(fresh));
          setDirty(false);
          onChange(fresh);
          setMessage("Паспорт уже не черновик: правки и выпуск ревизии недоступны.");
        } else {
          setConflict(true);
          setMessage(CONFLICT_MESSAGE);
        }
      } else {
        setMessage(errorText(reason, "Не удалось выпустить ревизию."));
      }
    } finally {
      setBusy(false);
    }
  }

  async function onPreview() {
    setBusy(true);
    setPreviewError("");
    try {
      const saved = dirty ? (await save())?.passport : current;
      if (!saved) return;
      const blob = await fetchBlob(api.drillPassport.previewUrl(saved.id));
      if (!alive.current) return; // окно закрыли, пока PDF строился
      const url = URL.createObjectURL(blob);
      if (previewRef.current) URL.revokeObjectURL(previewRef.current);
      previewRef.current = url;
      setPreview(url);
    } catch (reason) {
      if (previewRef.current) URL.revokeObjectURL(previewRef.current);
      previewRef.current = null;
      setPreview(null);
      setPreviewError(errorText(reason, "Предпросмотр недоступен."));
    } finally {
      setBusy(false);
    }
  }

  function requestClose() {
    if (dirty && !window.confirm("В паспорте есть несохранённые правки. Закрыть без сохранения?")) return;
    onClose();
  }

  function onBackdropClick(event: MouseEvent<HTMLDialogElement>) {
    if (event.target === ref.current) requestClose();
  }

  // Esc при несохранённых правках — тот же вопрос, что у «×». Перехват — на
  // keydown: отмену `cancel` Chrome принимает лишь раз на действие
  // пользователя, и второй Esc подряд закрыл бы окно без вопроса.
  function onDialogKeyDown(event: KeyboardEvent<HTMLDialogElement>) {
    if (event.key !== "Escape" || !dirty) return;
    // Esc во вложенной справке закрывает только её.
    if (event.target instanceof Element && event.target.closest("dialog") !== ref.current) return;
    event.preventDefault();
    requestClose();
  }

  // Запасной путь (Esc мимо keydown): без правок — закрытие, с правками — вопрос.
  function onDialogCancel(event: SyntheticEvent<HTMLDialogElement>) {
    if (event.target !== ref.current) return;
    if (dirty && !window.confirm("В паспорте есть несохранённые правки. Закрыть без сохранения?")) event.preventDefault();
  }

  // `close` вложенной справки сюда не относится.
  function onDialogClose(event: SyntheticEvent<HTMLDialogElement>) {
    if (event.target === ref.current) onClose();
  }

  function toggle(issue: DrillPassportIssue, checked: boolean) {
    setAcknowledged((previous) => {
      const next = new Set(previous);
      if (checked) next.add(ackKey(issue));
      else next.delete(ackKey(issue));
      return next;
    });
  }

  function control(field: FieldSpec, id: string) {
    const value = form.values[field.key];
    const common = { id, disabled: !editable || busy };
    if (field.kind === "reference" && field.section && references) {
      const options = referenceOptions(references, field.section);
      const labels = optionLabels(options);
      const known = !value || options.some((item) => item.code === value);
      return (
        <select {...common} value={value} onChange={(event) => setValue(field.key, event.target.value)}>
          <option value="">— не выбран —</option>
          {options.map((item) => (
            <option key={item.code} value={item.code}>{labels.get(item.code)}</option>
          ))}
          {!known && <option value={value}>{`${value} (нет в справочнике)`}</option>}
        </select>
      );
    }
    if (field.kind === "textarea") {
      return (
        <textarea {...common} rows={2} maxLength={field.maxLength} value={value} onChange={(event) => setValue(field.key, event.target.value)} />
      );
    }
    return (
      <input
        {...common}
        type={field.kind === "date" ? "date" : "text"}
        inputMode={field.kind === "number" ? "decimal" : undefined}
        maxLength={field.maxLength}
        value={value}
        placeholder={field.kind === "number" ? (sourceHint(field.key, validation) ?? "") : ""}
        onChange={(event) => setValue(field.key, event.target.value)}
      />
    );
  }

  function fieldBlock(field: FieldSpec) {
    const id = `drill-${field.key}`;
    const fieldIssues = issuesFor(field.key, issues);
    const manual = SOURCED.has(field.key) && form.values[field.key].trim() !== "";
    return (
      <div key={field.key} className={`drill-field${field.kind === "textarea" ? " wide" : ""}`}>
        <label htmlFor={id}>{field.unit ? `${field.label}, ${field.unit}` : field.label}</label>
        {control(field, id)}
        {manual && <small className="drill-source">вручную</small>}
        {field.hint && <small className="drill-hint">{field.hint}</small>}
        {errors[field.key] && <small className="form-error">{errors[field.key]}</small>}
        {fieldIssues.map((issue) => (
          <small key={issue.code} className={issue.level === "error" ? "form-error" : "frag-warnings"}>
            {issue.message}
          </small>
        ))}
      </div>
    );
  }

  return (
    <dialog ref={ref} className="cad-dialog drill-dialog" aria-labelledby="drill-dialog-title" onCancel={onDialogCancel} onKeyDown={onDialogKeyDown} onClose={onDialogClose} onClick={onBackdropClick}>
      <header>
        <b id="drill-dialog-title">Паспорт на бурение № {current.passport_no}</b>
        <span className="cad-files">
          {STATUS_LABEL[current.status]}
          {current.current_revision_id ? " · ревизия выпущена" : " · ревизия не выпущена"}
          {dirty ? " · есть несохранённые правки" : ""}
        </span>
        <span className="cad-header-actions">
          <DrillPassportHelp />
        </span>
        <button type="button" className="cad-close" aria-label="Закрыть" onClick={requestClose}>
          ×
        </button>
      </header>
      <div className="drill-dialog-body">
        <div className="drill-form">
          {FIELD_GROUPS.map((group) => (
            <fieldset key={group.title} disabled={locked}>
              <legend>{group.title}</legend>
              <div className="drill-grid">{group.fields.map(fieldBlock)}</div>
            </fieldset>
          ))}
          <fieldset disabled={locked}>
            <legend>Подписи</legend>
            {SIGNERS.map((signer) => (
              <div key={signer.key} className="drill-grid">
                {(["position", "organization", "name"] as const).map((part) => (
                  <div key={part} className="drill-field">
                    <label htmlFor={`drill-${signer.key}-${part}`}>
                      {`${signer.label}: ${part === "position" ? "должность" : part === "organization" ? "организация" : "ФИО"}`}
                    </label>
                    <input
                      id={`drill-${signer.key}-${part}`}
                      maxLength={SIGNER_LIMITS[part]}
                      value={form.signers[signer.key][part]}
                      onChange={(event) =>
                        updateForm((previous) => ({
                          ...previous,
                          signers: { ...previous.signers, [signer.key]: { ...previous.signers[signer.key], [part]: event.target.value } },
                        }))
                      }
                    />
                  </div>
                ))}
              </div>
            ))}
            <div className="drill-grid">
              {[0, 1].map((index) => (
                <div key={index} className="drill-field">
                  <label htmlFor={`drill-approval-${index}`}>{`Согласовано, строка ${index + 1} (должность ФИО)`}</label>
                  <input
                    id={`drill-approval-${index}`}
                    maxLength={APPROVAL_LIMIT}
                    value={form.extra_approvals[index]}
                    onChange={(event) =>
                      updateForm((previous) => {
                        const lines: [string, string] = [...previous.extra_approvals];
                        lines[index] = event.target.value;
                        return { ...previous, extra_approvals: lines };
                      })
                    }
                  />
                </div>
              ))}
            </div>
          </fieldset>
          <fieldset disabled={locked}>
            <legend>Ознакомление</legend>
            {form.personnel.map((person, index) => (
              <div key={index} className="drill-grid drill-person">
                {(["name", "position"] as const).map((part) => (
                  <div key={part} className="drill-field">
                    <label htmlFor={`drill-person-${index}-${part}`}>{`${index + 1}. ${part === "name" ? "ФИО" : "Должность"}`}</label>
                    <input
                      id={`drill-person-${index}-${part}`}
                      maxLength={PERSON_LIMITS[part]}
                      value={person[part]}
                      onChange={(event) =>
                        updateForm((previous) => ({
                          ...previous,
                          personnel: previous.personnel.map((item, at) => (at === index ? { ...item, [part]: event.target.value } : item)),
                        }))
                      }
                    />
                  </div>
                ))}
                <button
                  type="button"
                  className="link-button"
                  onClick={() => updateForm((previous) => ({ ...previous, personnel: previous.personnel.filter((_, at) => at !== index) }))}
                >
                  Удалить
                </button>
              </div>
            ))}
            {form.personnel.length < MAX_PERSONNEL && (
              <button
                type="button"
                className="secondary-button"
                onClick={() => updateForm((previous) => ({ ...previous, personnel: [...previous.personnel, { name: "", position: "" }] }))}
              >
                Добавить человека
              </button>
            )}
          </fieldset>
        </div>

        <aside className="drill-side">
          {!designSaved && (
            <p className="frag-warnings">Паспорт строится по сохранённому проекту блока — сохраните правки, затем выпускайте ревизию.</p>
          )}
          {!editable && <p className="frag-warnings">Паспорт не в статусе черновика: правки и выпуск ревизии недоступны.</p>}

          <section>
            <h4>Проверка первого ряда</h4>
            {validation ? (
              <table className="drill-check" aria-label="Проверка первого ряда">
                <tbody>
                  {checkRows(validation).map((row) => (
                    <tr key={row.key} className={`status-${row.status}`}>
                      <th scope="row">{row.label}</th>
                      <td>{row.value}</td>
                      <td>{row.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <small>Проверяем…</small>
            )}
            <small>Для инженера: в паспорт печатается только s.</small>
          </section>

          <section>
            <h4>Замечания проверки</h4>
            {validation && issues.length === 0 && <small>Замечаний нет.</small>}
            <ul className="drill-issues">
              {issues.map((issue) => (
                <li key={`${issue.level}:${issue.code}`} className={issue.level === "error" ? "form-error" : "frag-warnings"}>
                  <span>{issue.level === "error" ? "Ошибка" : "Предупреждение"}: {issue.message}</span>
                  {issue.level === "warning" && (
                    <label className="drill-ack">
                      <input
                        type="checkbox"
                        checked={acknowledged.has(ackKey(issue))}
                        disabled={locked}
                        onChange={(event) => toggle(issue, event.target.checked)}
                      />
                      просмотрено
                    </label>
                  )}
                </li>
              ))}
            </ul>
            {warnings.length > 0 && <small>Перед выпуском отметьте каждое предупреждение «просмотрено».</small>}
          </section>

          <div className="plans-actions">
            <button type="button" className="secondary-button" onClick={onSave} disabled={locked || !dirty || conflict}>
              Сохранить
            </button>
            <button type="button" className="calculate-button" onClick={onRelease} disabled={!releasable}>
              Выпустить ревизию
            </button>
          </div>
          {message && <small className="drill-message">{message}</small>}
          {conflict && (
            <button type="button" className="secondary-button" onClick={() => void onReload()} disabled={busy}>
              Загрузить сохранённый паспорт
            </button>
          )}

          <section className="drill-preview">
            <h4>Предпросмотр PDF</h4>
            <button type="button" className="secondary-button" onClick={onPreview} disabled={busy || hasErrors || conflict}>
              Показать предпросмотр
            </button>
            {hasErrors && <small>Предпросмотр — после исправления ошибок проверки.</small>}
            {previewError && <small className="form-error">{previewError}</small>}
            {preview && <iframe title="Предпросмотр паспорта" src={preview} />}
          </section>
        </aside>
      </div>
    </dialog>
  );
}
