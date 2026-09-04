import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/endpoints";
import type { User } from "../../types";
import type {
  EconomicsReferenceItem,
  EconomicsReferenceSnapshot,
  PublicDelta,
  PublicDeltaEntry,
  PublicSyncSettings,
  ReferenceRevision,
  ReferenceValidationIssue,
} from "../../types/economics";
import type { ReferenceSchemaCatalog } from "../../types/referenceSchema";
import { vatRate as vatRateOf, type DerivedContext } from "../../lib/referenceDerived";
import { plural } from "../../lib/plural";
import { countDraftChanges } from "./draftDiff";
import { DrillingConditionsMatrix, type MatrixMode } from "./DrillingConditionsMatrix";
import { mergeImportedSections, type DraftSections } from "./importDraft";
import {
  applyDeltaEntries,
  mergePendingLinks,
  resolvePendingLinks,
  type PendingLink,
} from "./publicDelta";
import { PublicDeltaBanner } from "./PublicDeltaBanner";
import { PublicSyncSettingsPanel } from "./PublicSyncSettings";
import { PublishBar } from "./PublishBar";
import { RecordForm, type DraftItem } from "./RecordForm";
import { SectionList } from "./SectionList";
import { SectionNav, type SectionStat } from "./SectionNav";
import { defaultPayload, numericPayloadKeys, sectionFields } from "./schemaFields";
import type { RefOption } from "./fields/RefSelect";

// Поля самой записи справочника (не payload): их подписи одинаковы во всех
// разделах, схема раздела о них ничего не знает.
const PAYLOAD_PREFIX = "payload.";
const TOP_LEVEL_FIELD_LABELS: Record<string, string> = {
  name: "Наименование",
  is_active: "Активна",
  comment: "Комментарий",
  valid_from: "Действует с",
  valid_to: "Действует по",
};

function rowId(): string {
  const token =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `reference-${token}`;
}

function toDraft(snapshot: EconomicsReferenceSnapshot): DraftSections {
  const draft: DraftSections = {};
  for (const [section, items] of Object.entries(snapshot.sections)) {
    draft[section] = items.map((item) => ({ ...item, row_id: rowId() }));
  }
  return draft;
}

function toSections(draft: DraftSections): Record<string, EconomicsReferenceItem[]> {
  const sections: Record<string, EconomicsReferenceItem[]> = {};
  for (const [section, rows] of Object.entries(draft)) {
    sections[section] = rows.map(({ row_id: _row, ...item }) => item);
  }
  return sections;
}

/**
 * Справочники экономики: разделы — список — форма записи.
 *
 * Страница не знает ни одного поля payload: и форма, и колонки списка строятся
 * по схеме с сервера. Разделоспецифично только одно представление — матрица
 * условий бурения.
 */
export function ReferencesPage({ user }: { user: User }) {
  const [catalog, setCatalog] = useState<ReferenceSchemaCatalog | null>(null);
  const [snapshot, setSnapshot] = useState<EconomicsReferenceSnapshot | null>(null);
  const [draft, setDraft] = useState<DraftSections>({});
  const [activeSection, setActiveSection] = useState("");
  const [selectedRow, setSelectedRow] = useState("");
  const [newRows, setNewRows] = useState<Set<string>>(new Set());
  const [issues, setIssues] = useState<ReferenceValidationIssue[]>([]);
  const [matrixMode, setMatrixMode] = useState<MatrixMode>("rocks");
  const [comment, setComment] = useState("");
  const [revisions, setRevisions] = useState<ReferenceRevision[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [publicDelta, setPublicDelta] = useState<PublicDelta | null>(null);
  // Связи со строками журнала копятся в черновике и записываются при
  // публикации, одной транзакцией с ревизией. Ключ связи — `row_id` записи, а
  // не код: код правится в форме, и связь должна идти за записью.
  const [pendingLinks, setPendingLinks] = useState<PendingLink[]>([]);
  // Настройки обмена меняет только администратор — остальным они и не грузятся.
  const [publicSettings, setPublicSettings] = useState<PublicSyncSettings | null>(null);
  const canEdit = user.role === "admin" || user.role === "reference_editor";
  const isAdmin = user.role === "admin";

  // Номер последнего запроса разницы: ответы более ранних запросов
  // игнорируются, иначе медленный первый ответ затёр бы свежий второй.
  const deltaRequest = useRef(0);

  /**
   * Разница черновика с журналом project1. Ошибка запроса не ломает страницу:
   * плашка показывает причину и кнопку «Повторить», справочники остаются
   * рабочими и без журнала.
   *
   * Возвращает полученную разницу или `null`, если ответ устарел — пока он
   * шёл, начался следующий запрос, и показывать нужно уже его результат.
   */
  const refreshPublicDelta = useCallback(
    async (currentDraft: DraftSections, links: PendingLink[]): Promise<PublicDelta | null> => {
      const request = (deltaRequest.current += 1);
      let result: PublicDelta;
      try {
        // Ожидающие связи уходят вместе с черновиком: без них применённая, но
        // ещё не опубликованная запись каждый раз возвращалась бы «новой».
        result = await api.economics.publicDelta(
          toSections(currentDraft),
          resolvePendingLinks(currentDraft, links),
        );
      } catch (reason) {
        result = {
          available: false,
          error: reason instanceof Error ? reason.message : "неизвестная ошибка",
          counts: { new: 0, changed: 0, deactivated: 0 },
          entries: [],
        };
      }
      if (request !== deltaRequest.current) return null;
      setPublicDelta(result);
      return result;
    },
    [],
  );

  const load = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      // Схема и снимок независимы — грузим параллельно, страница открывается
      // за один круг вместо двух.
      const [schema, loaded] = await Promise.all([
        api.economics.referenceSchema(),
        api.economics.referenceSnapshot(),
      ]);
      const loadedDraft = toDraft(loaded);
      setCatalog(schema);
      setSnapshot(loaded);
      setDraft(loadedDraft);
      setNewRows(new Set());
      setPendingLinks([]);
      setIssues([]);
      setSelectedRow("");
      setActiveSection((current) => (current && schema.sections[current] ? current : Object.keys(schema.sections)[0] ?? ""));
      try {
        // Номер ревизии живёт в истории публикаций: в снимке лежит только его
        // идентификатор, а «Опубликовать ревизию 15» читается понятнее UUID.
        setRevisions(await api.economics.revisions());
      } catch {
        setRevisions([]);
      }
      if (isAdmin) {
        try {
          setPublicSettings(await api.economics.publicSettings());
        } catch {
          // Настройки обмена — не условие работы со справочниками: без них
          // просто нет панели.
          setPublicSettings(null);
        }
      }
      await refreshPublicDelta(loadedDraft, []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить справочники.");
    } finally {
      setBusy(false);
    }
  }, [isAdmin, refreshPublicDelta]);

  useEffect(() => {
    void load();
  }, [load]);

  const publishedByCode = useMemo(() => {
    const map = new Map<string, EconomicsReferenceItem>();
    for (const [section, items] of Object.entries(snapshot?.sections ?? {})) {
      for (const item of items) map.set(`${section}::${item.code}`, item);
    }
    return map;
  }, [snapshot]);

  // Что считать числом, знает только схема раздела: без неё текстовые коды
  // из цифр («0021») сравнивались бы как числа и правка терялась.
  const numericKeys = useMemo(() => {
    const bySection = new Map<string, ReadonlySet<string>>();
    for (const [code, section] of Object.entries(catalog?.sections ?? {})) {
      bySection.set(code, numericPayloadKeys(section.json_schema));
    }
    return (section: string): ReadonlySet<string> => bySection.get(section) ?? new Set<string>();
  }, [catalog]);

  const diff = useMemo(
    () => countDraftChanges(draft, publishedByCode, numericKeys),
    [draft, publishedByCode, numericKeys],
  );

  const changedRows = diff.changed;
  const changeCount = changedRows.size;
  const removedCount = diff.removed.length;
  // Удаление записи видно только по опубликованной ревизии: без него кнопка
  // публикации оставалась выключенной, а шапка говорила «Опубликовано».
  // Связь, выбранная в черновике, — тоже неопубликованное изменение: без неё
  // кнопка публикации осталась бы выключенной и связь некуда было бы записать.
  const dirty = changeCount > 0 || removedCount > 0 || pendingLinks.length > 0;

  const stats = useMemo(() => {
    const result: Record<string, SectionStat> = {};
    for (const section of Object.keys(catalog?.sections ?? {})) {
      const rows = draft[section] ?? [];
      const sectionIssues = issues.filter((issue) => issue.section === section);
      result[section] = {
        count: rows.length,
        errors: sectionIssues.filter((issue) => issue.level === "error").length,
        warnings: sectionIssues.filter((issue) => issue.level === "warning").length,
        changed: rows.filter((row) => changedRows.has(row.row_id)).length,
      };
    }
    return result;
  }, [catalog, draft, issues, changedRows]);

  const derivedContext: DerivedContext = useMemo(
    () => ({
      sections: Object.fromEntries(
        Object.entries(draft).map(([section, rows]) => [
          section,
          rows.map((row) => ({ code: row.code, name: row.name, payload: row.payload, is_active: row.is_active })),
        ]),
      ),
    }),
    [draft],
  );

  const sectionLabels = useMemo(
    () =>
      Object.fromEntries(Object.values(catalog?.sections ?? {}).map((section) => [section.code, section.label])),
    [catalog],
  );

  /**
   * Подпись поля в тексте изменения. Страница не знает полей payload: имя
   * берётся из схемы раздела (`title`, затем `description`), а у полей самой
   * записи справочника подписи одинаковы во всех разделах.
   */
  const fieldLabel = useCallback(
    (section: string, key: string) => {
      if (!key.startsWith(PAYLOAD_PREFIX)) return TOP_LEVEL_FIELD_LABELS[key] ?? key;
      const name = key.slice(PAYLOAD_PREFIX.length);
      const property = catalog?.sections[section]?.json_schema.properties?.[name];
      return property?.title ?? property?.description ?? name;
    },
    [catalog],
  );

  const refOptions = useCallback(
    (section: string): RefOption[] =>
      (draft[section] ?? []).map((row) => ({ code: row.code, name: row.name, is_active: row.is_active })),
    [draft],
  );

  const refName = useCallback(
    (section: string, code: string) => (draft[section] ?? []).find((row) => row.code === code)?.name || code,
    [draft],
  );

  const findRecord = useCallback(
    (query: string) => {
      const matches: Array<{ section: string; code: string; name: string }> = [];
      for (const [section, rows] of Object.entries(draft)) {
        for (const row of rows) {
          if (`${row.name} ${row.code}`.toLowerCase().includes(query)) {
            matches.push({ section, code: row.code, name: row.name });
          }
        }
      }
      return matches;
    },
    [draft],
  );

  function selectSection(section: string, code?: string) {
    setActiveSection(section);
    setSelectedRow(code ? (draft[section] ?? []).find((row) => row.code === code)?.row_id ?? "" : "");
  }

  function updateRows(section: string, update: (rows: DraftItem[]) => DraftItem[]) {
    setDraft((current) => ({ ...current, [section]: update(current[section] ?? []) }));
  }

  function addRecord(prefill: Record<string, unknown> = {}) {
    const schema = catalog?.sections[activeSection];
    if (!schema) return;
    const created: DraftItem = {
      row_id: rowId(),
      code: "",
      name: "",
      payload: { ...defaultPayload(sectionFields(schema.json_schema)), ...prefill },
      is_active: true,
      valid_from: null,
      valid_to: null,
      source: "",
      comment: "",
      revision: 1,
    };
    updateRows(activeSection, (rows) => [...rows, created]);
    setNewRows((current) => new Set(current).add(created.row_id));
    setSelectedRow(created.row_id);
  }

  function applyRecord(next: DraftItem) {
    updateRows(activeSection, (rows) => rows.map((row) => (row.row_id === next.row_id ? next : row)));
    setNewRows((current) => {
      if (!current.has(next.row_id)) return current;
      const rest = new Set(current);
      rest.delete(next.row_id);
      return rest;
    });
  }

  function resetRecord(row: DraftItem) {
    const published = publishedByCode.get(`${activeSection}::${row.code}`);
    if (!published) {
      updateRows(activeSection, (rows) => rows.filter((item) => item.row_id !== row.row_id));
      setSelectedRow("");
      return;
    }
    updateRows(activeSection, (rows) =>
      rows.map((item) => (item.row_id === row.row_id ? { ...published, row_id: row.row_id } : item)),
    );
  }

  /** Код копии: свободный `_COPY`, `_COPY2`… — иначе публикация падает на повторе кода. */
  function copyCode(row: DraftItem): string {
    const taken = new Set((draft[activeSection] ?? []).map((item) => item.code));
    const base = row.code ? `${row.code}_COPY` : "COPY";
    if (!taken.has(base)) return base;
    for (let suffix = 2; suffix < 100; suffix += 1) {
      const candidate = `${base}${suffix}`;
      if (!taken.has(candidate)) return candidate;
    }
    return `${base}_${Date.now()}`;
  }

  function duplicateRecord(row: DraftItem) {
    const copy: DraftItem = { ...row, row_id: rowId(), code: copyCode(row), name: `${row.name} (копия)` };
    updateRows(activeSection, (rows) => [...rows, copy]);
    setNewRows((current) => new Set(current).add(copy.row_id));
    setSelectedRow(copy.row_id);
  }

  function toggleActive(row: DraftItem) {
    updateRows(activeSection, (rows) =>
      rows.map((item) => (item.row_id === row.row_id ? { ...item, is_active: !item.is_active } : item)),
    );
  }

  async function validate(): Promise<boolean> {
    setBusy(true);
    setError("");
    try {
      // Ожидающие связи уходят вместе с черновиком: без них связанная запись
      // проверяется как новая и получает ошибку «уже есть в журнале», хотя
      // публикация с теми же связями прошла бы успешно.
      const result = await api.economics.validateReferences(
        toSections(draft),
        resolvePendingLinks(draft, pendingLinks),
      );
      setIssues(result.issues);
      return result.valid;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось проверить справочники.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  function discard() {
    if (!snapshot) return;
    setDraft(toDraft(snapshot));
    setNewRows(new Set());
    setPendingLinks([]);
    setIssues([]);
    setSelectedRow("");
  }

  async function exportReferences(format: "xlsx" | "json") {
    // Выгружается ревизия с сервера, а не то, что на экране: без предупреждения
    // файл молча расходился бы с черновиком.
    if (dirty && !window.confirm("Черновик не опубликован: будет выгружена опубликованная ревизия. Продолжить?")) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.economics.exportReferences(format, snapshot?.revision_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось экспортировать справочники.");
    } finally {
      setBusy(false);
    }
  }

  async function importReferences(file: File) {
    if (!canEdit) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.economics.importReferences(file);
      const merged = mergeImportedSections(draft, result.sections, rowId);
      setDraft(merged.draft);
      // Новые для опубликованной ревизии записи помечаем как новые: список и
      // форма показывают их так же, как добавленные вручную.
      setNewRows((current) => {
        // Разделы из файла заменены целиком: их прежние `row_id` исчезли.
        const alive = new Set(Object.values(merged.draft).flatMap((rows) => rows.map((row) => row.row_id)));
        const next = new Set([...current].filter((id) => alive.has(id)));
        for (const section of merged.replaced) {
          for (const row of merged.draft[section] ?? []) {
            if (!publishedByCode.has(`${section}::${row.code}`)) next.add(row.row_id);
          }
        }
        return next;
      });
      setSelectedRow("");
      setIssues([]);
      if (merged.replaced.length && !merged.replaced.includes(activeSection)) setActiveSection(merged.replaced[0]);
      const validation = await api.economics.validateReferences(
        toSections(merged.draft),
        resolvePendingLinks(merged.draft, pendingLinks),
      );
      setIssues(validation.issues);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить файл.");
    } finally {
      setBusy(false);
    }
  }

  /**
   * Применить всю разницу с журналом в черновик и пересчитать её заново.
   *
   * Показанная разница считалась по черновику на момент последней проверки:
   * с тех пор пользователь мог править записи, и применение старых `entries`
   * затёрло бы эти правки. Поэтому разница сначала перечитывается по текущему
   * черновику, и применяется уже свежий ответ.
   */
  async function applyPublicDelta() {
    if (!publicDelta || !publicDelta.available || !canEdit) return;
    setBusy(true);
    setError("");
    try {
      const fresh = await refreshPublicDelta(draft, pendingLinks);
      // Ответ устарел — идёт более свежая проверка, она и обновит плашку.
      if (!fresh) return;
      if (!fresh.available) {
        setError(`project1 недоступен: ${fresh.error}`);
        return;
      }
      const merged = applyDeltaEntries(draft, fresh.entries, rowId);
      if (!merged.applied) return;
      setDraft(merged.draft);
      // Применённая запись — это связь со строкой журнала: без неё та же
      // строка вернулась бы как «новая» и завела бы дубль под кодом `PUB_*`.
      // Связь ждёт публикации и записывается вместе с ревизией.
      const applied: PendingLink[] = [];
      for (const entry of fresh.entries) {
        const row = (merged.draft[entry.section] ?? []).find((item) => item.code === entry.code);
        if (!row) continue;
        applied.push({
          row_id: row.row_id,
          section: entry.section,
          public_table: entry.public_table,
          public_id: entry.public_id,
        });
      }
      const links = mergePendingLinks(pendingLinks, applied);
      setPendingLinks(links);
      // Записи, которых нет в опубликованной ревизии, помечаем как новые — так
      // же, как добавленные вручную или пришедшие файлом.
      setNewRows((current) => {
        const next = new Set(current);
        for (const entry of fresh.entries) {
          if (publishedByCode.has(`${entry.section}::${entry.code}`)) continue;
          const row = (merged.draft[entry.section] ?? []).find((item) => item.code === entry.code);
          if (row) next.add(row.row_id);
        }
        return next;
      });
      setSelectedRow("");
      const validation = await api.economics.validateReferences(
        toSections(merged.draft),
        resolvePendingLinks(merged.draft, links),
      );
      setIssues(validation.issues);
      await refreshPublicDelta(merged.draft, links);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось проверить справочники.");
    } finally {
      setBusy(false);
    }
  }

  /**
   * Связать строку журнала с уже существующей записью: она перестанет быть
   * «новой». Связь только выбирается — в базу она уходит при публикации
   * ревизии, в которую вошла запись, поэтому отменённый черновик не оставляет
   * связей на исчезнувшие коды.
   */
  async function linkPublicEntry(entry: PublicDeltaEntry, code: string) {
    if (!canEdit || !code) return;
    const row = (draft[entry.section] ?? []).find((item) => item.code === code);
    if (!row) return;
    const links = mergePendingLinks(pendingLinks, [
      {
        row_id: row.row_id,
        section: entry.section,
        public_table: entry.public_table,
        public_id: entry.public_id,
      },
    ]);
    setPendingLinks(links);
    setBusy(true);
    try {
      await refreshPublicDelta(draft, links);
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    if (!snapshot || !canEdit) return;
    if (!(await validate())) return;
    setBusy(true);
    setError("");
    try {
      const published = await api.economics.publishReferences({
        base_revision: snapshot.revision_id,
        sections: toSections(draft),
        comment,
        public_links: resolvePendingLinks(draft, pendingLinks),
      });
      const publishedDraft = toDraft(published);
      setSnapshot(published);
      setDraft(publishedDraft);
      setNewRows(new Set());
      setPendingLinks([]);
      setSelectedRow("");
      setComment("");
      setIssues([]);
      setRevisions(await api.economics.revisions().catch(() => revisions));
      // Черновик после публикации — это уже новая ревизия: плашка должна
      // считать разницу от неё, а не показывать расхождения, которых нет.
      await refreshPublicDelta(publishedDraft, []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось опубликовать справочники.");
    } finally {
      setBusy(false);
    }
  }

  if (!catalog || !snapshot) {
    return (
      <div className="page-content">
        <h2>Справочники</h2>
        {error ? <div className="page-error">{error}</div> : <p className="page-caption">Загрузка…</p>}
        <button className="ref-ghost-button" onClick={() => void load()} disabled={busy}>
          Повторить
        </button>
      </div>
    );
  }

  const section = catalog.sections[activeSection];
  const rows = draft[activeSection] ?? [];
  const selected = rows.find((row) => row.row_id === selectedRow);
  const sectionIssues = issues.filter((issue) => issue.section === activeSection);
  const errorCodes = new Set(sectionIssues.filter((issue) => issue.level === "error").map((issue) => issue.code));
  const totalErrors = issues.filter((issue) => issue.level === "error").length;
  const lastRevisionNo = revisions.reduce((max, item) => Math.max(max, item.sequence_no), 0);
  const currentRevisionNo = revisions.find((item) => item.id === snapshot.revision_id)?.sequence_no;
  const revisionLabel = currentRevisionNo ? String(currentRevisionNo) : snapshot.revision_id;

  const draftSummary = [
    removedCount
      ? `изменено: ${changeCount}, удалено: ${removedCount}`
      : `${changeCount} ${plural(changeCount, ["изменение", "изменения", "изменений"])}`,
    // Связи записываются публикацией, поэтому их число видно там же, где
    // остальное неопубликованное.
    pendingLinks.length ? `связей к публикации: ${pendingLinks.length}` : "",
  ]
    .filter(Boolean)
    .join(", ");

  const list = section && (
    <SectionList
      section={section}
      rows={rows}
      selected={selectedRow}
      changed={changedRows}
      errorCodes={errorCodes}
      canEdit={canEdit}
      refName={refName}
      onSelect={setSelectedRow}
      onAdd={() => addRecord()}
    />
  );

  return (
    <div className="ref-workbench">
      <header className="ref-workbench-head">
        <div>
          <h2>Справочники</h2>
          <p>
            {user.organization_name} · опубликована ревизия {revisionLabel}
            {snapshot.published_at ? ` от ${new Date(snapshot.published_at).toLocaleDateString("ru-RU")}` : ""}
          </p>
        </div>
        <span className={`ref-draft-status${dirty ? " dirty" : ""}`}>
          {dirty ? `Черновик · ${draftSummary}` : "Опубликовано"}
        </span>
      </header>

      <PublicDeltaBanner
        delta={publicDelta}
        busy={busy}
        canEdit={canEdit}
        sectionLabel={(code) => sectionLabels[code] ?? code}
        fieldLabel={fieldLabel}
        // Связывать можно только с записью опубликованной ревизии: код записи,
        // заведённой в этом черновике, ещё может исчезнуть или измениться, и
        // связь осталась бы указывать в пустоту.
        recordsOf={(code) =>
          (draft[code] ?? [])
            .filter((row) => row.is_active && row.code && publishedByCode.has(`${code}::${row.code}`))
            .map((row) => ({ code: row.code, name: row.name }))
        }
        onRefresh={() => void refreshPublicDelta(draft, pendingLinks)}
        onApplyAll={() => void applyPublicDelta()}
        onLink={(entry, code) => void linkPublicEntry(entry, code)}
      />

      {isAdmin && (
        <PublicSyncSettingsPanel
          settings={publicSettings}
          sectionLabel={(code) => sectionLabels[code] ?? code}
          onChange={setPublicSettings}
          // Включённый обмен и новые зеркала меняют состав разницы с журналом:
          // после сохранения плашку нужно пересчитать.
          onSaved={() => void refreshPublicDelta(draft, pendingLinks)}
        />
      )}

      {error && <div className="page-error">{error}</div>}

      <div className={`ref-grid${selected ? " with-form" : ""}`}>
        <SectionNav
          catalog={catalog}
          stats={stats}
          active={activeSection}
          onSelect={selectSection}
          findRecord={findRecord}
        />

        <div className="ref-main">
          {section?.view === "matrix" ? (
            <DrillingConditionsMatrix
              section={section}
              rows={rows}
              rigs={(draft.equipment_types ?? []).filter((row) => row.is_active && row.payload.kind === "DRILL_RIG")}
              rocks={(draft.rocks ?? []).filter((row) => row.is_active)}
              sites={(draft.sites ?? []).filter((row) => row.is_active)}
              mode={matrixMode}
              onMode={setMatrixMode}
              selected={selectedRow}
              changed={changedRows}
              canEdit={canEdit}
              onSelect={setSelectedRow}
              onCreate={(prefill) => addRecord(prefill)}
              listView={list}
            />
          ) : (
            list
          )}

          <PublishBar
            comment={comment}
            onComment={setComment}
            onValidate={() => void validate()}
            onDiscard={discard}
            onPublish={() => void publish()}
            onExportXlsx={() => void exportReferences("xlsx")}
            onExportJson={() => void exportReferences("json")}
            onImport={(file) => void importReferences(file)}
            canEdit={canEdit}
            busy={busy}
            dirty={dirty}
            errors={totalErrors}
            nextRevision={lastRevisionNo ? String(lastRevisionNo + 1) : ""}
          />
        </div>

        {section && selected && (
          <RecordForm
            section={section}
            record={selected}
            published={publishedByCode.get(`${activeSection}::${selected.code}`)}
            issues={sectionIssues.filter((issue) => issue.code === selected.code)}
            canEdit={canEdit}
            isNew={newRows.has(selected.row_id)}
            changed={changedRows.has(selected.row_id)}
            refOptions={refOptions}
            sectionLabels={sectionLabels}
            siblings={rows.filter((row) => row.row_id !== selected.row_id).map((row) => row.payload)}
            context={derivedContext}
            vatRate={vatRateOf(derivedContext)}
            onApply={applyRecord}
            onReset={() => resetRecord(selected)}
            onDeactivate={() => toggleActive(selected)}
            onDuplicate={() => duplicateRecord(selected)}
            onClose={() => setSelectedRow("")}
          />
        )}
      </div>
    </div>
  );
}
