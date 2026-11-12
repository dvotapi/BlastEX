// Вкладка «Проверка и документы» окна проекта МВ (TASK-018, PR 6, §5):
// замечания проверки со ссылкой на вкладку, предпросмотр каждого документа
// черновика, ревизия, согласование ролями, статусы и скачивание документов
// утверждённой ревизии и «Весь комплект».
import { useState } from "react";
import { api } from "../../../api/endpoints";
import type { MassBlastIssue, MassBlastProjectV2, ProjectDocument } from "../../../types/massBlast";
import { APPROVAL_ROLES } from "./form";
import { download, errorText, openPdf } from "./ui";

export const DOCUMENTS: Array<{ code: ProjectDocument; label: string }> = [
  { code: "title", label: "Титул" },
  { code: "technical-calculation", label: "Технический расчёт" },
  { code: "parameter-table", label: "Таблица параметров" },
  { code: "schedule", label: "Распорядок" },
  { code: "graphics", label: "Графика Г.1–Г.5" },
  { code: "project", label: "Проект целиком" },
];

export const STATUS_LABELS: Record<MassBlastProjectV2["lifecycle_status"], string> = {
  draft: "черновик",
  in_review: "на согласовании",
  approved: "утверждён",
  executed: "взрыв произведён",
  closed: "закрыт",
};

const AFTER_APPROVAL = new Set(["approved", "executed", "closed"]);

export function IssueList({ issues, onOpen }: { issues: MassBlastIssue[]; onOpen: (issue: MassBlastIssue) => void }) {
  if (!issues.length) return <small className="drill-hint">Замечаний нет.</small>;
  const ordered = [...issues.filter((issue) => issue.level === "error"), ...issues.filter((issue) => issue.level === "warning")];
  return (
    <ul className="drill-issues">
      {ordered.map((issue, index) => (
        <li key={`${issue.code}:${index}`} className={issue.level === "error" ? "form-error" : "frag-warnings"}>
          <span>{issue.level === "error" ? "Ошибка: " : "Предупреждение: "}{issue.message}</span>
          <button type="button" className="link-button" onClick={() => onOpen(issue)}>К полю</button>
        </li>
      ))}
    </ul>
  );
}

export function ProjectDocuments({
  project,
  issues,
  checked,
  dirty,
  busy,
  userEmail,
  hasGraphics,
  ensureSaved,
  onRelease,
  onApprove,
  onTransition,
  onOpenIssue,
}: {
  project: MassBlastProjectV2;
  issues: MassBlastIssue[];
  checked: boolean;
  dirty: boolean;
  busy: boolean;
  userEmail: string;
  hasGraphics: boolean;
  ensureSaved: () => Promise<MassBlastProjectV2 | null>;
  onRelease: () => void;
  onApprove: (role: string) => void;
  onTransition: (to: "draft" | "approved" | "executed" | "closed") => void;
  onOpenIssue: (issue: MassBlastIssue) => void;
}) {
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);
  const [working, setWorking] = useState(false);
  const status = project.lifecycle_status;
  const errors = issues.filter((issue) => issue.level === "error");
  const revisionId = project.current_revision_id;
  const approved = AFTER_APPROVAL.has(status);

  async function preview(document: ProjectDocument) {
    setWorking(true);
    setNote(null);
    try {
      const saved = await ensureSaved();
      if (!saved) return;
      await openPdf(api.massBlast.previewUrl(saved.id, document));
    } catch (reason) {
      setNote({ text: errorText(reason, "Предпросмотр недоступен."), error: true });
    } finally {
      setWorking(false);
    }
  }

  async function fetchFile(url: string, fallback: string) {
    setWorking(true);
    setNote(null);
    try {
      const warning = await download(url, fallback);
      if (warning) setNote({ text: warning, error: false });
    } catch (reason) {
      setNote({ text: errorText(reason, "Не удалось скачать файл."), error: true });
    } finally {
      setWorking(false);
    }
  }

  const locked = busy || working;
  return (
    <>
      <fieldset>
        <legend>Проверка</legend>
        {!checked && <small className="drill-hint">Нажмите «Проверить» — сервер посчитает проект и покажет замечания.</small>}
        {checked && <IssueList issues={issues} onOpen={onOpenIssue} />}
      </fieldset>

      {!approved && (
        <fieldset>
          <legend>Предпросмотр документов (с пометкой «ЧЕРНОВИК»)</legend>
          <div className="drill-downloads">
            {DOCUMENTS.map((item) => (
              <button key={item.code} type="button" className="secondary-button" disabled={locked || (checked && !dirty && errors.length > 0)}
                onClick={() => void preview(item.code)}>
                {item.label}
              </button>
            ))}
          </div>
          {checked && !dirty && errors.length > 0 && <small className="form-error">Сначала исправьте ошибки проверки.</small>}
          <small className="drill-hint">PDF открывается в новой вкладке. Несохранённые правки сначала сохраняются.</small>
        </fieldset>
      )}

      <fieldset>
        <legend>Ревизия и согласование · {STATUS_LABELS[status]}</legend>
        {status === "draft" && (
          <>
            <div className="plans-actions">
              <button type="button" className="calculate-button" disabled={locked || (checked && !dirty && errors.length > 0)} onClick={onRelease}>
                Выпустить ревизию на согласование
              </button>
            </div>
            <small className="drill-hint">Ревизия фиксирует проект и контрольную сумму; согласуют её назначенные учётки ролей.</small>
          </>
        )}
        {status === "in_review" && (
          <>
            <div className="plans-actions">
              {APPROVAL_ROLES.map((role) => {
                const account = project.responsibilities.find((item) => item.role_code === role.code)?.account_email ?? "";
                const mine = !account || !userEmail || account.toLowerCase() === userEmail.toLowerCase();
                return (
                  <button key={role.code} type="button" className="secondary-button" disabled={locked || !mine}
                    title={mine ? undefined : `Согласует учётка ${account}`} onClick={() => onApprove(role.code)}>
                    Согласовать: {role.label.toLowerCase()}
                  </button>
                );
              })}
            </div>
            <div className="plans-actions">
              <button type="button" className="calculate-button" disabled={locked} onClick={() => onTransition("approved")}>Утвердить проект</button>
              <button type="button" className="secondary-button" disabled={locked} onClick={() => onTransition("draft")}>Вернуть в черновик</button>
            </div>
          </>
        )}
        {status === "approved" && (
          <div className="plans-actions">
            <button type="button" className="calculate-button" disabled={locked} onClick={() => onTransition("executed")}>Взрыв произведён</button>
          </div>
        )}
        {status === "executed" && (
          <div className="plans-actions">
            <button type="button" className="secondary-button" disabled={locked} onClick={() => onTransition("closed")}>Закрыть проект</button>
          </div>
        )}
      </fieldset>

      {approved && revisionId && (
        <fieldset>
          <legend>Документы утверждённой ревизии</legend>
          <div className="drill-downloads">
            {DOCUMENTS.filter((item) => item.code !== "graphics" || hasGraphics).map((item) => (
              <button key={item.code} type="button" className="secondary-button" disabled={locked}
                onClick={() => void fetchFile(api.massBlast.revisionDocumentUrl(revisionId, item.code), `${item.code}.pdf`)}>
                {item.label}
              </button>
            ))}
            <button type="button" className="calculate-button" disabled={locked}
              onClick={() => void fetchFile(api.massBlast.packageUrl(revisionId), "package.zip")}>
              Весь комплект
            </button>
          </div>
          <small className="drill-hint">
            «Весь комплект» — архив: проект, выпущенные слои дня взрыва и общий PDF для двусторонней печати. Графику
            печатать в масштабе 100 %, без «вписать в страницу».
          </small>
        </fieldset>
      )}
      {note && <small className={note.error ? "form-error" : "frag-warnings"}>{note.text}</small>}
    </>
  );
}
