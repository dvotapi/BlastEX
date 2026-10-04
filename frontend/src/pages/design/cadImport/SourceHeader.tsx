// Шапка источника окна «Импорт чертежа» (TASK-013, PR 4): название и дата
// съёмки файла, другие версии его серии ситуации и система координат
// объекта. Название и дата сохраняются сами после паузы в наборе; СК —
// настройка всего объекта, поэтому только по кнопке «Сохранить».
import { useEffect, useRef, useState } from "react";
import type {
  CadCrs,
  CadCrsResponse,
  CadSource,
  CadSourceMetaPayload,
  CadSourceMetaResponse,
} from "../../../types/cad";
import { versionLabels } from "../situationLayer";

/** Пауза в наборе, после которой название и дата уходят на сервер. */
const SAVE_DELAY_MS = 400;

export type SourceHeaderProps = {
  source: CadSource;
  /** Названия серий объекта — подсказка: совпавшее название делает файл новой версией серии. */
  knownTitles: string[];
  disabled: boolean;
  saveMeta: (id: string, payload: CadSourceMetaPayload) => Promise<CadSourceMetaResponse>;
  saveCrs: (id: string, crs: CadCrs) => Promise<CadCrsResponse>;
  onMetaSaved: (meta: CadSourceMetaResponse) => void;
  onCrsSaved: (sourceId: string, answer: CadCrsResponse) => void;
  /**
   * Чем занята шапка: набор ждёт паузы или сохраняется, сохраняется или
   * открыта правка СК; null — ничего. «Построить блок» ждёт, иначе паспорт
   * запомнил бы прежние серию и СК.
   */
  onBusyChange?: (reason: string | null) => void;
};

function crsText(source: CadSource): string {
  if (!source.site_code) return "объект работ не выбран — систему координат хранить негде";
  const crs = source.crs;
  if (!crs) return "не задана";
  const parts = [crs.name];
  if (crs.height_system) parts.push(`высоты ${crs.height_system}`);
  if (crs.epsg !== null) parts.push(`EPSG ${crs.epsg}`);
  return parts.join(" · ");
}

/** Сколько других версий серии называть в шапке: строка не должна съедать таблицу слоёв. */
const SERIES_SHOWN = 3;

function seriesText(source: CadSource): string {
  if (!source.series.length) return "";
  const labels = versionLabels(source.series);
  const rest = labels.length - SERIES_SHOWN;
  return `Другие версии серии: ${labels.slice(0, SERIES_SHOWN).join(", ")}${rest > 0 ? ` и ещё ${rest}` : ""}`;
}

export function SourceHeader({
  source,
  knownTitles,
  disabled,
  saveMeta,
  saveCrs,
  onMetaSaved,
  onCrsSaved,
  onBusyChange,
}: SourceHeaderProps) {
  const [title, setTitle] = useState(source.title);
  const [surveyDate, setSurveyDate] = useState(source.survey_date ?? "");
  const [metaError, setMetaError] = useState("");
  const [editingCrs, setEditingCrs] = useState(false);
  const [crsName, setCrsName] = useState("");
  const [crsHeights, setCrsHeights] = useState("");
  const [crsEpsg, setCrsEpsg] = useState("");
  const [crsError, setCrsError] = useState("");
  const [crsSaving, setCrsSaving] = useState(false);
  // Набор ждёт паузы; отправленные и ещё не отвеченные сохранения.
  const [waiting, setWaiting] = useState(false);
  const [inFlight, setInFlight] = useState(0);
  // Поля, изменённые после последней отправки, и таймер паузы.
  const pending = useRef<CadSourceMetaPayload>({});
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Номер отправки и последний номер по файлу: ответ на более раннюю отправку
  // того же файла не применяется, а ответ по файлу, с которого уже ушли, —
  // применяется (окно обновит название и серию того файла).
  const sent = useRef(0);
  const lastSent = useRef(new Map<string, number>());
  const sourceId = useRef(source.id);
  sourceId.current = source.id;
  const latest = useRef({ saveMeta, onMetaSaved });
  latest.current = { saveMeta, onMetaSaved };

  // Другой файл — свои поля. Набор прежнего файла, не дождавшийся паузы
  // (переключили файл, закрыли окно, нажали «Построить блок»), отправляется
  // сразу — правка названия или даты не теряется.
  useEffect(() => {
    setTitle(source.title);
    setSurveyDate(source.survey_date ?? "");
    setMetaError("");
    setEditingCrs(false);
    setCrsError("");
    const id = source.id;
    return () => {
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
      setWaiting(false);
      const payload = pending.current;
      pending.current = {};
      if (Object.keys(payload).length) deliver(id, payload);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source.id]);

  function schedule(patch: CadSourceMetaPayload) {
    pending.current = { ...pending.current, ...patch };
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(send, SAVE_DELAY_MS);
    setWaiting(true);
  }

  function send() {
    timer.current = null;
    setWaiting(false);
    const payload = pending.current;
    pending.current = {};
    if (Object.keys(payload).length) deliver(sourceId.current, payload);
  }

  function deliver(id: string, payload: CadSourceMetaPayload) {
    const number = ++sent.current;
    lastSent.current.set(id, number);
    const stale = () => lastSent.current.get(id) !== number;
    setInFlight((count) => count + 1);
    const settled = () => setInFlight((count) => count - 1);
    latest.current.saveMeta(id, payload).then(
      (answer) => {
        settled();
        if (stale()) return;
        if (id === sourceId.current) setMetaError("");
        latest.current.onMetaSaved(answer);
      },
      (reason) => {
        settled();
        // Ошибку видно только у открытого файла.
        if (stale() || id !== sourceId.current) return;
        setMetaError(reason instanceof Error ? reason.message : "Не удалось сохранить название и дату.");
      },
    );
  }

  function changeTitle(value: string) {
    setTitle(value);
    if (!value.trim()) {
      // Пустое название не отправляется: по нему файл попадает в серию.
      const { title: _dropped, ...rest } = pending.current;
      pending.current = rest;
      if (!Object.keys(rest).length && timer.current) {
        clearTimeout(timer.current);
        timer.current = null;
        setWaiting(false);
      }
      setMetaError("Название не может быть пустым: по нему файл попадает в серию ситуации.");
      return;
    }
    setMetaError("");
    schedule({ title: value.trim() });
  }

  function changeDate(value: string) {
    setSurveyDate(value);
    schedule({ survey_date: value || null });
  }

  function startCrs() {
    setCrsName(source.crs?.name ?? "");
    setCrsHeights(source.crs?.height_system ?? "");
    setCrsEpsg(source.crs?.epsg != null ? String(source.crs.epsg) : "");
    setCrsError("");
    setEditingCrs(true);
  }

  async function submitCrs() {
    const name = crsName.trim();
    if (!name) {
      setCrsError("Укажите систему координат, например «МСК-66 зона 1».");
      return;
    }
    const epsgText = crsEpsg.trim();
    const epsg = epsgText === "" ? null : Number(epsgText);
    if (epsg !== null && (!Number.isInteger(epsg) || epsg <= 0)) {
      setCrsError("EPSG — целое положительное число; у местной системы его нет — оставьте пустым.");
      return;
    }
    const id = source.id;
    setCrsSaving(true);
    try {
      const answer = await saveCrs(id, { name, height_system: crsHeights.trim(), epsg });
      onCrsSaved(id, answer);
      setEditingCrs(false);
      setCrsError("");
    } catch (reason) {
      setCrsError(reason instanceof Error ? reason.message : "Не удалось сохранить систему координат.");
    } finally {
      setCrsSaving(false);
    }
  }

  const busy = crsSaving
    ? "Сохраняю систему координат…"
    : editingCrs
      ? "Сохраните или отмените правку СК объекта."
      : waiting || inFlight > 0
        ? "Сохраняю название и дату…"
        : null;
  const reportBusy = useRef(onBusyChange);
  reportBusy.current = onBusyChange;
  useEffect(() => {
    reportBusy.current?.(busy);
  }, [busy]);

  const series = seriesText(source);
  const listId = `cad-known-titles-${source.id}`;
  return (
    <section className="cad-source-header" aria-label="Файл чертежа и СК объекта">
      <div className="cad-source-fields">
        <label>
          <span>Название</span>
          <input
            value={title}
            list={listId}
            maxLength={300}
            disabled={disabled}
            onChange={(event) => changeTitle(event.target.value)}
          />
          <datalist id={listId}>
            {knownTitles.map((item) => (
              <option key={item} value={item} />
            ))}
          </datalist>
        </label>
        <label>
          <span>Дата съёмки</span>
          <input type="date" value={surveyDate} disabled={disabled} onChange={(event) => changeDate(event.target.value)} />
        </label>
      </div>
      {series && <p className="cad-series">{series}</p>}
      {metaError && (
        <p className="cad-field-error" role="alert">
          {metaError}
        </p>
      )}
      <div className="cad-crs">
        <span className="cad-crs-text">{`СК объекта: ${crsText(source)}`}</span>
        {source.site_code && !editingCrs && (
          <button type="button" className="secondary-button" disabled={disabled} onClick={startCrs}>
            Изменить
          </button>
        )}
      </div>
      {editingCrs && (
        <div className="cad-crs-form">
          <label>
            <span>Система координат</span>
            <input value={crsName} maxLength={120} placeholder="МСК-66 зона 1" onChange={(event) => setCrsName(event.target.value)} />
          </label>
          <label>
            <span>Система высот</span>
            <input
              value={crsHeights}
              maxLength={120}
              placeholder="Балтийская 1977"
              onChange={(event) => setCrsHeights(event.target.value)}
            />
          </label>
          <label>
            <span>EPSG</span>
            <input value={crsEpsg} inputMode="numeric" placeholder="нет" onChange={(event) => setCrsEpsg(event.target.value)} />
          </label>
          <div className="cad-crs-actions">
            <button type="button" className="primary-button" disabled={crsSaving} onClick={() => void submitCrs()}>
              Сохранить
            </button>
            <button type="button" className="secondary-button" disabled={crsSaving} onClick={() => setEditingCrs(false)}>
              Отмена
            </button>
          </div>
          {crsError && (
            <p className="cad-field-error" role="alert">
              {crsError}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
