import { useEffect, useMemo, useState } from "react";
import { api } from "../api/endpoints";
import type { User } from "../types";
import type {
  EconomicsReferenceItem,
  EconomicsReferenceSnapshot,
  ReferenceValidationIssue,
} from "../types/economics";

type DraftItem = Omit<EconomicsReferenceItem, "payload"> & { row_id: string; payload_text: string };
type DraftSections = Record<string, DraftItem[]>;

function draftRowId(): string {
  const token = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `economics-reference-${token}`;
}

function stable(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, stable(item)])
    );
  }
  return value;
}

function fingerprint(sections: Record<string, EconomicsReferenceItem[]>): string {
  const normalized = Object.fromEntries(
    Object.entries(sections)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([section, rows]) => [section, [...rows].sort((a, b) => a.code.localeCompare(b.code))])
  );
  return JSON.stringify(stable(normalized));
}

function toDraft(snapshot: EconomicsReferenceSnapshot): DraftSections {
  const result: DraftSections = {};
  for (const meta of snapshot.section_catalog) {
    result[meta.code] = (snapshot.sections[meta.code] ?? []).map((item) => ({
      ...item,
      row_id: draftRowId(),
      payload_text: JSON.stringify(item.payload, null, 2),
    }));
  }
  return result;
}

function parseDraft(draft: DraftSections): {
  sections: Record<string, EconomicsReferenceItem[]>;
  issues: ReferenceValidationIssue[];
} {
  const sections: Record<string, EconomicsReferenceItem[]> = {};
  const issues: ReferenceValidationIssue[] = [];
  for (const [section, rows] of Object.entries(draft)) {
    sections[section] = rows.map((row) => {
      let payload: Record<string, unknown> = {};
      try {
        const parsed = JSON.parse(row.payload_text || "{}");
        if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
          throw new Error("ожидается JSON-объект");
        }
        payload = parsed as Record<string, unknown>;
      } catch (reason) {
        issues.push({
          level: "error",
          section,
          code: row.code,
          message: `Некорректные параметры JSON: ${reason instanceof Error ? reason.message : String(reason)}`,
        });
      }
      const { payload_text: _, row_id: __, ...item } = row;
      return { ...item, payload };
    });
  }
  return { sections, issues };
}

function emptyItem(): DraftItem {
  return {
    row_id: draftRowId(),
    code: "",
    name: "",
    payload_text: "{}",
    is_active: true,
    valid_from: null,
    valid_to: null,
    source: "",
    comment: "",
    revision: 1,
  };
}

export function EconomicsReferencesPage({ user }: { user: User }) {
  const [snapshot, setSnapshot] = useState<EconomicsReferenceSnapshot | null>(null);
  const [draft, setDraft] = useState<DraftSections>({});
  const [activeGroup, setActiveGroup] = useState("");
  const [activeSection, setActiveSection] = useState("");
  const [issues, setIssues] = useState<ReferenceValidationIssue[]>([]);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const canEdit = user.role === "admin" || user.role === "reference_editor";

  async function load() {
    setBusy(true);
    setError("");
    try {
      const loaded = await api.economics.referenceSnapshot();
      setSnapshot(loaded);
      setDraft(toDraft(loaded));
      setIssues([]);
      const group = loaded.group_catalog[0]?.code ?? "";
      setActiveGroup(group);
      setActiveSection(
        loaded.section_catalog.find((item) => item.group === group)?.code ??
          loaded.section_catalog[0]?.code ??
          ""
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить project1.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const groupSections = useMemo(
    () => snapshot?.section_catalog.filter((item) => item.group === activeGroup) ?? [],
    [snapshot, activeGroup]
  );
  const rows = draft[activeSection] ?? [];
  const original = snapshot ? fingerprint(snapshot.sections) : "";
  const parsed = useMemo(() => parseDraft(draft), [draft]);
  const dirty = snapshot ? fingerprint(parsed.sections) !== original : false;

  function chooseGroup(group: string) {
    setActiveGroup(group);
    const first = snapshot?.section_catalog.find((item) => item.group === group)?.code;
    if (first) setActiveSection(first);
  }

  function updateRow(index: number, patch: Partial<DraftItem>) {
    setDraft((current) => ({
      ...current,
      [activeSection]: (current[activeSection] ?? []).map((row, i) =>
        i === index ? { ...row, ...patch } : row
      ),
    }));
  }

  function addRow() {
    setDraft((current) => ({
      ...current,
      [activeSection]: [...(current[activeSection] ?? []), emptyItem()],
    }));
  }

  async function validate() {
    const local = parseDraft(draft);
    if (local.issues.length) {
      setIssues(local.issues);
      return false;
    }
    setBusy(true);
    setError("");
    try {
      const result = await api.economics.validateReferences(local.sections);
      setIssues(result.issues);
      return result.valid;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось проверить справочники.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    if (!snapshot || !canEdit) return;
    const local = parseDraft(draft);
    if (local.issues.length) {
      setIssues(local.issues);
      return;
    }
    if (!(await validate())) return;
    setBusy(true);
    setError("");
    try {
      const published = await api.economics.publishReferences({
        base_revision: snapshot.revision_id,
        sections: local.sections,
        comment,
      });
      setSnapshot(published);
      setDraft(toDraft(published));
      setComment("");
      setIssues([]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось опубликовать справочники.");
    } finally {
      setBusy(false);
    }
  }

  if (!snapshot) {
    return (
      <div className="page-content">
        <h2>Справочники project1</h2>
        {error ? <div className="page-error">{error}</div> : <p className="page-caption">Загрузка…</p>}
        <button className="secondary-button" onClick={() => void load()} disabled={busy}>Повторить</button>
      </div>
    );
  }

  const sectionLabel = snapshot.section_catalog.find((item) => item.code === activeSection)?.label ?? activeSection;

  return (
    <div className="page-content economics-references">
      <div className="page-heading">
        <div>
          <h2>Справочники project1</h2>
          <p>Опубликованная ревизия {snapshot.revision_id} · {snapshot.published_by}</p>
        </div>
        <span className={`save-status ${dirty ? "dirty" : ""}`}>{dirty ? "Есть черновик" : "Опубликовано"}</span>
      </div>
      <p className="page-caption">
        Изменения остаются локальным черновиком до атомарной публикации. Использованные записи деактивируйте вместо удаления.
      </p>
      {error && <div className="page-error">{error}</div>}

      <nav className="reference-group-tabs">
        {snapshot.group_catalog.map((group) => (
          <button key={group.code} className={group.code === activeGroup ? "active" : ""} onClick={() => chooseGroup(group.code)}>
            {group.label}
          </button>
        ))}
      </nav>
      <nav className="sub-tabs">
        {groupSections.map((section) => (
          <button key={section.code} className={section.code === activeSection ? "active" : ""} onClick={() => setActiveSection(section.code)}>
            {section.label} ({draft[section.code]?.length ?? 0})
          </button>
        ))}
      </nav>

      <section className="panel reference-editor-panel">
        <header><b>{sectionLabel}</b><span>{rows.length} записей</span></header>
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>Активна</th><th>Код</th><th>Наименование</th><th>Параметры JSON</th><th>Действует с</th><th>Действует до</th><th>Источник / комментарий</th></tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={row.row_id} className={row.is_active ? "" : "inactive-row"}>
                  <td><input type="checkbox" checked={row.is_active} disabled={!canEdit} onChange={(e) => updateRow(index, { is_active: e.target.checked })} /></td>
                  <td><input value={row.code} disabled={!canEdit} onChange={(e) => updateRow(index, { code: e.target.value.toUpperCase() })} /></td>
                  <td><input value={row.name} disabled={!canEdit} onChange={(e) => updateRow(index, { name: e.target.value })} /></td>
                  <td><textarea rows={4} value={row.payload_text} disabled={!canEdit} onChange={(e) => updateRow(index, { payload_text: e.target.value })} /></td>
                  <td><input type="date" value={row.valid_from ?? ""} disabled={!canEdit} onChange={(e) => updateRow(index, { valid_from: e.target.value || null })} /></td>
                  <td><input type="date" value={row.valid_to ?? ""} disabled={!canEdit} onChange={(e) => updateRow(index, { valid_to: e.target.value || null })} /></td>
                  <td>
                    <input placeholder="Источник" value={row.source} disabled={!canEdit} onChange={(e) => updateRow(index, { source: e.target.value })} />
                    <textarea rows={2} placeholder="Комментарий" value={row.comment} disabled={!canEdit} onChange={(e) => updateRow(index, { comment: e.target.value })} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {canEdit && <button className="row-add" onClick={addRow}>+ Добавить запись</button>}
      </section>

      {issues.length > 0 && (
        <section className="validation-list">
          <b>Результат проверки</b>
          {issues.map((issue, index) => (
            <div key={`${issue.section}-${issue.code}-${index}`} className={issue.level}>
              <span>{issue.level === "error" ? "Ошибка" : "Предупреждение"}</span>
              <p>{issue.section}{issue.code ? ` / ${issue.code}` : ""}: {issue.message}</p>
            </div>
          ))}
        </section>
      )}

      <div className="reference-publish-bar">
        <input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Комментарий к публикации" disabled={!canEdit || busy} />
        <button className="secondary-button" onClick={() => void load()} disabled={busy || (dirty && canEdit)}>Загрузить из project1</button>
        <button className="secondary-button" onClick={() => void validate()} disabled={busy}>Проверить</button>
        <button className="primary-button" onClick={() => void publish()} disabled={!canEdit || busy || !dirty}>Опубликовать в project1</button>
      </div>
    </div>
  );
}
