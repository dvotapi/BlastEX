// Окно «Проект массового взрыва» по форме ВМ.09.03 (TASK-018, PR 6). Слева —
// вкладки по разделам §5 TASK-018, справа — форма вкладки; внизу — число
// замечаний проверки и «Сохранить», «Проверить». Расчёт, проверку и печать
// делает сервер; окно показывает ответ и JSON не показывает.
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent, type SyntheticEvent } from "react";
import { api } from "../../../api/endpoints";
import type { MassBlastAccount } from "../../../types/design";
import type { MassBlastHints, MassBlastIssue, MassBlastProjectV2, MassBlastValidationV2 } from "../../../types/massBlast";
import { fieldIndex, type FieldDescriptor } from "../../references/schemaFields";
import { formErrors, formFromProject, toInput, type ProjectForm } from "./form";
import { MassBlastHelp } from "./MassBlastHelp";
import { DayTab } from "./layers/DayTab";
import { PostsTab } from "./PostsTab";
import { ProjectDocuments, STATUS_LABELS } from "./ProjectDocuments";
import { BlocksTab, ExplosivesTab, ObjectsTab, PersonnelTab, RequisitesTab, SafetyTab, ScheduleTab } from "./ProjectTabs";
import { errorText } from "./ui";

export type TabCode =
  | "requisites" | "blocks" | "explosives" | "safety" | "objects" | "schedule" | "personnel" | "posts" | "documents" | "day";

export const TABS: Array<{ code: TabCode; label: string }> = [
  { code: "requisites", label: "Реквизиты" },
  { code: "blocks", label: "Блоки" },
  { code: "explosives", label: "ВМ и СИ" },
  { code: "safety", label: "Безопасность" },
  { code: "objects", label: "Охраняемые объекты" },
  { code: "schedule", label: "Распорядок" },
  { code: "personnel", label: "Персонал" },
  { code: "posts", label: "Посты и план" },
  { code: "documents", label: "Проверка и документы" },
  { code: "day", label: "День взрыва" },
];

/** Вкладка, на которой поле замечания (по `path` сервера). */
export function tabForIssue(issue: MassBlastIssue): TabCode {
  const path = issue.path;
  const rules: Array<[RegExp, TabCode]> = [
    [/^requisites|^notifications/, "requisites"],
    [/^explosives|^blocks\[\d+\]\.(consumption|technical_calculation)/, "explosives"],
    [/^safety_plan|^safety_overrides|^zones|^blocks\[\d+\]\.safety/, "safety"],
    [/^blocks/, "blocks"],
    [/^protected_objects/, "objects"],
    [/^schedule/, "schedule"],
    [/^personnel|^responsibilities/, "personnel"],
    [/^guard_posts|^layout_points|^graphics/, "posts"],
  ];
  if (issue.code === "blast_time_missing") return "requisites";
  return rules.find(([rule]) => rule.test(path))?.[1] ?? "documents";
}

const CONFLICT = "Проект изменён в другом окне или другим пользователем. Закройте окно и откройте проект заново — правки этого окна пропадут.";
const isConflict = (reason: unknown) => (reason as { status?: number } | null)?.status === 409;

export function MassBlastDialog({
  project: initial,
  onClose,
  onChange,
}: {
  project: MassBlastProjectV2;
  onClose: () => void;
  onChange: (project: MassBlastProjectV2) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [project, setProject] = useState(initial);
  const [form, setForm] = useState<ProjectForm>(() => formFromProject(initial));
  const [dirty, setDirty] = useState(false);
  const [validation, setValidation] = useState<MassBlastValidationV2 | null>(null);
  const [hints, setHints] = useState<MassBlastHints | null>(null);
  const [accounts, setAccounts] = useState<MassBlastAccount[]>([]);
  const [fields, setFields] = useState<Map<string, FieldDescriptor> | null>(null);
  const [userEmail, setUserEmail] = useState("");
  const [hasGraphics, setHasGraphics] = useState(true);
  const [tab, setTab] = useState<TabCode>(() => (["approved", "executed", "closed"].includes(initial.lifecycle_status) ? "day" : "requisites"));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const alive = useRef(true);

  const errors = useMemo(() => formErrors(form), [form]);
  const editable = project.lifecycle_status === "draft" && !busy;
  const issues = validation?.issues ?? [];
  const errorCount = issues.filter((issue) => issue.level === "error").length;
  const warningCount = issues.length - errorCount;
  const context = validation?.context ?? null;

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal?.();
    alive.current = true;
    void check(initial, false);
    api.massBlast.hints(initial.id).then((value) => alive.current && setHints(value)).catch(() => undefined);
    api.massBlast.accounts().then((value) => alive.current && setAccounts(value)).catch(() => undefined);
    api.me().then((user) => alive.current && setUserEmail(String((user as { email?: string }).email ?? ""))).catch(() => undefined);
    api.economics
      .referenceSchema()
      .then((catalog) => {
        if (!alive.current) return;
        // Подписи ручных коэффициентов — по схемам справочников (CLAUDE.md, Cost V2).
        const merged = new Map<string, FieldDescriptor>();
        for (const section of ["rocks", "blast_safety"]) {
          for (const [key, field] of fieldIndex(catalog.sections[section]?.json_schema)) merged.set(key, field);
        }
        setFields(merged);
      })
      .catch(() => alive.current && setFields(null));
    return () => {
      alive.current = false;
    };
    // Только при открытии окна.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const revisionId = project.current_revision_id;
  useEffect(() => {
    if (!revisionId || !["approved", "executed", "closed"].includes(project.lifecycle_status)) return;
    api.massBlast
      .revision(revisionId)
      .then((revision) => {
        const ctx = revision.context as { graphics?: unknown; blocks_v2?: Array<{ graphics?: unknown }> };
        const blocks = ctx.blocks_v2 ?? [];
        if (alive.current) setHasGraphics(Boolean(ctx.graphics) && blocks.length > 0 && blocks.every((block) => Boolean(block.graphics)));
      })
      .catch(() => undefined);
  }, [revisionId, project.lifecycle_status]);

  function edit(mutate: (draft: ProjectForm) => void) {
    setForm((current) => {
      const next = structuredClone(current);
      mutate(next);
      return next;
    });
    setDirty(true);
  }

  function accept(next: MassBlastProjectV2) {
    setProject(next);
    onChange(next);
  }

  async function check(target: MassBlastProjectV2, report = true) {
    try {
      const result = await api.massBlast.validateV2(target.id);
      if (!alive.current) return;
      setValidation(result);
      if (report) {
        const count = result.issues.filter((issue) => issue.level === "error").length;
        setMessage({ text: count ? `Проверка: ошибок — ${count}.` : "Проверка пройдена.", error: count > 0 });
      }
    } catch (reason) {
      if (alive.current && report) setMessage({ text: errorText(reason, "Не удалось проверить проект."), error: true });
    }
  }

  async function save(): Promise<MassBlastProjectV2 | null> {
    if (!dirty) return project;
    if (Object.keys(errors).length) {
      setMessage({ text: "Исправьте поля, отмеченные в форме.", error: true });
      return null;
    }
    const saved = await api.massBlast.saveV2(project.id, toInput(form, project));
    if (!alive.current) return null;
    accept(saved);
    setForm(formFromProject(saved));
    setDirty(false);
    await check(saved, false);
    return saved;
  }

  async function run(action: () => Promise<void>, fallback: string) {
    setBusy(true);
    setMessage(null);
    try {
      await action();
    } catch (reason) {
      if (alive.current) setMessage({ text: isConflict(reason) ? CONFLICT : errorText(reason, fallback), error: true });
    } finally {
      if (alive.current) setBusy(false);
    }
  }

  const onSave = () => run(async () => {
    if (await save()) setMessage({ text: "Проект сохранён.", error: false });
  }, "Не удалось сохранить проект.");

  const onCheck = () => run(async () => {
    const saved = await save();
    if (saved) await check(saved);
  }, "Не удалось проверить проект.");

  const onRelease = () => run(async () => {
    const saved = await save();
    if (!saved) return;
    const revision = await api.massBlast.createRevision(saved.id, { expected_version: saved.version });
    accept(await api.massBlast.getV2(saved.id));
    setMessage({ text: `Ревизия № ${revision.revision_no} выпущена: её согласуют назначенные учётки ролей.`, error: false });
  }, "Не удалось выпустить ревизию.");

  const onApprove = (role: string) => run(async () => {
    if (!project.current_revision_id) return;
    await api.massBlast.approveRevision(project.current_revision_id, { role_code: role, decision: "approved" });
    setMessage({ text: "Согласование записано.", error: false });
  }, "Не удалось записать согласование.");

  const onTransition = (to: "draft" | "approved" | "executed" | "closed") => {
    const questions: Record<typeof to, string> = {
      draft: "Вернуть проект в черновик? Правка создаст следующую ревизию.",
      approved: "Утвердить проект? Нужны согласования обеих ролей.",
      executed: "Отметить, что взрыв произведён? После этого открываются талон-допуск и акт приёмки.",
      closed: "Закрыть проект? Из статуса «закрыт» вернуть проект нельзя.",
    };
    if (!window.confirm(questions[to])) return;
    let note = "";
    if (to === "executed" || to === "draft") {
      const answer = window.prompt("Примечание (необязательно)", "");
      if (answer === null) return;
      note = answer.trim();
    }
    void run(async () => {
      const updated = await api.massBlast.transition(project.id, { to_status: to, expected_version: project.version, confirm: true, note });
      const full = await api.massBlast.getV2(updated.id);
      accept(full);
      setForm(formFromProject(full));
      setDirty(false);
      setMessage({ text: `Статус проекта: ${STATUS_LABELS[full.lifecycle_status]}.`, error: false });
      if (to === "approved") setTab("day");
    }, "Не удалось сменить статус проекта.");
  };

  function requestClose() {
    if (dirty && !window.confirm("В проекте есть несохранённые правки. Закрыть без сохранения?")) return;
    ref.current?.close?.();
    onClose();
  }

  function onBackdropClick(event: MouseEvent<HTMLDialogElement>) {
    if (event.target === ref.current) requestClose();
  }

  function onDialogKeyDown(event: KeyboardEvent<HTMLDialogElement>) {
    if (event.key !== "Escape") return;
    if (event.target instanceof Element && event.target.closest("dialog") !== ref.current) return;
    event.preventDefault();
    requestClose();
  }

  function onDialogCancel(event: SyntheticEvent<HTMLDialogElement>) {
    if (event.target !== ref.current) return;
    event.preventDefault();
    requestClose();
  }

  const props = { form, edit, editable, errors, issues, context };
  const approvedLike = ["approved", "executed", "closed"].includes(project.lifecycle_status);
  return (
    <dialog ref={ref} className="cad-dialog drill-dialog mb-dialog" aria-labelledby="mb-dialog-title" onCancel={onDialogCancel}
      onKeyDown={onDialogKeyDown} onClick={onBackdropClick}>
      <header>
        <b id="mb-dialog-title">
          Проект массового взрыва{form.requisites.project_no ? ` № ${form.requisites.project_no}` : ""} · {project.name}
        </b>
        <span className="cad-files">
          {STATUS_LABELS[project.lifecycle_status]}
          {project.current_revision_id ? " · ревизия выпущена" : ""}
          {dirty ? " · есть несохранённые правки" : ""}
        </span>
        <span className="cad-header-actions">
          <MassBlastHelp />
        </span>
        <button type="button" className="cad-close" aria-label="Закрыть" onClick={requestClose}>×</button>
      </header>
      <div className="mb-dialog-body">
        <nav className="mb-tabs" aria-label="Разделы проекта">
          {TABS.map((item) => {
            const count = issues.filter((issue) => issue.level === "error" && tabForIssue(issue) === item.code).length;
            const hidden = item.code === "day" && !approvedLike;
            if (hidden) return null;
            return (
              <button key={item.code} type="button" className={tab === item.code ? "active" : ""} aria-current={tab === item.code ? "page" : undefined}
                onClick={() => setTab(item.code)}>
                {item.label}{count ? <span className="mb-tab-errors" aria-label={`ошибок: ${count}`}>{count}</span> : null}
              </button>
            );
          })}
        </nav>
        <div className="drill-form mb-content">
          {!editable && tab !== "day" && tab !== "documents" && (
            <small className="frag-warnings">Проект не в статусе черновика: поля только для чтения.</small>
          )}
          {tab === "requisites" && <RequisitesTab {...props} hints={hints} />}
          {tab === "blocks" && <BlocksTab {...props} />}
          {tab === "explosives" && <ExplosivesTab {...props} />}
          {tab === "safety" && <SafetyTab {...props} fields={fields} />}
          {tab === "objects" && <ObjectsTab {...props} />}
          {tab === "schedule" && <ScheduleTab {...props} />}
          {tab === "personnel" && <PersonnelTab {...props} hints={hints} accounts={accounts} />}
          {tab === "posts" && <PostsTab {...props} />}
          {tab === "documents" && (
            <ProjectDocuments project={project} issues={issues} checked={validation !== null} dirty={dirty} busy={busy}
              userEmail={userEmail} hasGraphics={hasGraphics} ensureSaved={save}
              onRelease={() => void onRelease()} onApprove={(role) => void onApprove(role)} onTransition={onTransition}
              onOpenIssue={(issue) => setTab(tabForIssue(issue))} />
          )}
          {tab === "day" && approvedLike && <DayTab project={project} />}
        </div>
      </div>
      <footer className="mb-footer">
        <button type="button" className="link-button" onClick={() => setTab("documents")}>
          {validation ? `Ошибок: ${errorCount} · предупреждений: ${warningCount}` : "Проверка не выполнялась"}
        </button>
        {message && <small className={message.error ? "form-error" : "drill-message"}>{message.text}</small>}
        <span className="mb-footer-actions">
          {project.lifecycle_status === "draft" && (
            <button type="button" className="secondary-button" disabled={busy || !dirty} onClick={() => void onSave()}>Сохранить</button>
          )}
          <button type="button" className="calculate-button" disabled={busy} onClick={() => void onCheck()}>Проверить</button>
        </span>
      </footer>
    </dialog>
  );
}
