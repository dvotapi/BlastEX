// «Съёмка старого блока» (TASK-014, PR 5а): исполнительная съёмка блока,
// которого нет в BlastEX, хранится на объекте работ — название блока, горизонт,
// дата и точки файла. Объект — запись справочника «Объекты» (Cost V2): окно
// показывает только её название, полей справочника не знает.
import { useEffect, useRef, useState, type MouseEvent, type SyntheticEvent } from "react";
import { api } from "../../api/endpoints";
import { ruDate, ruNumber } from "../../lib/format";
import type { EconomicsReferenceItem } from "../../types/economics";
import type { SiteSurvey } from "../../types/design";

const SURVEY_ACCEPT = ".csv,.txt,.xlsx,.xlsm,.dxf";

function message(reason: unknown, fallback: string): string {
  return reason instanceof Error && reason.message ? reason.message : fallback;
}

/** Подпись объекта — название; код — только у одинаковых названий. */
function siteLabels(items: EconomicsReferenceItem[]): Map<string, string> {
  const counts = new Map<string, number>();
  for (const item of items) counts.set(item.name, (counts.get(item.name) ?? 0) + 1);
  return new Map(items.map((item) => [item.code, (counts.get(item.name) ?? 0) > 1 ? `${item.name} (${item.code})` : item.name || item.code]));
}

function newestFirst(items: SiteSurvey[]): SiteSurvey[] {
  return [...items].sort((a, b) => b.survey_date.localeCompare(a.survey_date) || b.created_at.localeCompare(a.created_at));
}

export function SiteSurveyDialog({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  // null — справочник читается, false — не прочитан (код объекта вводится текстом).
  const [sites, setSites] = useState<EconomicsReferenceItem[] | null | false>(null);
  const [siteCode, setSiteCode] = useState("");
  const [surveys, setSurveys] = useState<SiteSurvey[] | null>(null);
  const [blockLabel, setBlockLabel] = useState("");
  const [horizon, setHorizon] = useState("");
  const [surveyDate, setSurveyDate] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  useEffect(() => {
    let alive = true;
    api.economics
      .referenceSnapshot()
      .then((snapshot) => {
        if (!alive) return;
        const active = (snapshot.sections.sites ?? []).filter((item) => item.is_active);
        setSites(active);
        if (active.length === 1) setSiteCode(active[0].code);
      })
      .catch(() => alive && setSites(false));
    return () => {
      alive = false;
    };
  }, []);

  // Список съёмок выбранного объекта.
  useEffect(() => {
    setSurveys(null);
    const code = siteCode.trim();
    if (!code) return;
    let alive = true;
    api.survey.sites
      .list(code)
      .then((items) => alive && setSurveys(newestFirst(items)))
      .catch((reason) => alive && setError(message(reason, "Не удалось прочитать съёмки объекта.")));
    return () => {
      alive = false;
    };
  }, [siteCode]);

  const horizonValue = horizon.trim() ? Number(horizon.trim().replace(",", ".")) : null;
  const horizonBad = horizonValue !== null && !Number.isFinite(horizonValue);
  const canUpload = Boolean(siteCode.trim() && blockLabel.trim() && surveyDate && file && !horizonBad && !busy);

  async function upload() {
    if (!file || !canUpload) return;
    setBusy(true);
    setError("");
    try {
      const created = await api.survey.sites.create(siteCode.trim(), file, {
        blockLabel: blockLabel.trim(),
        surveyDate,
        ...(horizonValue !== null ? { horizonM: horizonValue } : {}),
      });
      const { points: _points, ...summary } = created;
      setSurveys((current) => newestFirst([summary, ...(current ?? [])]));
      setBlockLabel("");
      setHorizon("");
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
    } catch (reason) {
      setError(message(reason, "Не удалось загрузить съёмку."));
    } finally {
      setBusy(false);
    }
  }

  async function remove(item: SiteSurvey) {
    if (!window.confirm(`Удалить съёмку блока ${item.block_label} от ${ruDate(item.survey_date)}? Отменить удаление нельзя.`)) return;
    setBusy(true);
    setError("");
    try {
      await api.survey.sites.remove(item.site_code, item.id);
      setSurveys((current) => (current ?? []).filter((other) => other.id !== item.id));
    } catch (reason) {
      setError(message(reason, "Не удалось удалить съёмку."));
    } finally {
      setBusy(false);
    }
  }

  function onDialogClose(event: SyntheticEvent<HTMLDialogElement>) {
    if (event.target === ref.current) onClose();
  }

  function onBackdropClick(event: MouseEvent<HTMLDialogElement>) {
    if (event.target === ref.current) onClose();
  }

  const labels = sites ? siteLabels(sites) : new Map<string, string>();

  return (
    <dialog
      ref={ref}
      className="cad-sources-dialog survey-site-dialog"
      aria-labelledby="survey-site-title"
      onClose={onDialogClose}
      onClick={onBackdropClick}
    >
      <header>
        <b id="survey-site-title">Съёмка старого блока</b>
        <button type="button" className="cad-close" aria-label="Закрыть" onClick={onClose}>
          ×
        </button>
      </header>
      <p className="cad-sources-note">
        Блок, которого нет в BlastEX: файл исполнительной съёмки хранится на объекте работ — по нему соседние блоки
        увидят пробуренные скважины.
      </p>
      {error && (
        <p className="cad-request-error" role="alert">
          {error}
        </p>
      )}
      <div className="survey-site-form">
        <label>
          Объект
          {sites === false ? (
            <input value={siteCode} onChange={(event) => setSiteCode(event.target.value)} placeholder="код объекта" />
          ) : (
            <select value={siteCode} disabled={sites === null || busy} onChange={(event) => setSiteCode(event.target.value)}>
              <option value="">{sites === null ? "читаю справочник…" : "— не выбран —"}</option>
              {(sites || []).map((item) => (
                <option key={item.code} value={item.code}>{labels.get(item.code)}</option>
              ))}
            </select>
          )}
        </label>
        <label>
          Блок
          <input value={blockLabel} maxLength={80} disabled={busy} onChange={(event) => setBlockLabel(event.target.value)} />
        </label>
        <label>
          Горизонт, м
          <input
            inputMode="decimal"
            value={horizon}
            disabled={busy}
            placeholder="отметка подошвы"
            onChange={(event) => setHorizon(event.target.value)}
          />
        </label>
        <label>
          Дата съёмки
          <input type="date" value={surveyDate} disabled={busy} onChange={(event) => setSurveyDate(event.target.value)} />
        </label>
        <label>
          Файл
          <input
            ref={fileRef}
            type="file"
            accept={SURVEY_ACCEPT}
            disabled={busy}
            aria-label="Файл съёмки старого блока"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <button type="button" className="primary-button" disabled={!canUpload} onClick={() => void upload()}>
          {busy ? "Загружаю…" : "Загрузить"}
        </button>
        {horizonBad && <small className="frag-warnings">Горизонт — число, метры.</small>}
      </div>
      {siteCode.trim() && (
        <div className="survey-site-list">
          {surveys === null ? (
            <small className="cad-sources-note">Читаю съёмки объекта…</small>
          ) : surveys.length === 0 ? (
            <small className="cad-sources-note">Съёмок старых блоков на объекте нет.</small>
          ) : (
            <ul>
              {surveys.map((item) => (
                <li key={item.id}>
                  <span>
                    <b>Блок {item.block_label}</b>
                    <small>
                      {item.horizon_m !== null && item.horizon_m !== undefined ? `горизонт ${ruNumber(item.horizon_m, 1)} м · ` : ""}
                      съёмка {ruDate(item.survey_date)} · точек {item.points_count}
                      {item.file_name ? ` · ${item.file_name}` : ""}
                    </small>
                  </span>
                  <button
                    type="button"
                    className="secondary-button survey-site-delete"
                    disabled={busy}
                    aria-label={`Удалить съёмку блока ${item.block_label}`}
                    onClick={() => void remove(item)}
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </dialog>
  );
}
