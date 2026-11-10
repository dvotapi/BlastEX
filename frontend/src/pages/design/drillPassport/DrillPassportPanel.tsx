// Панель «Паспорт на бурение» в этапе «Отчёт» «Проектирования» рядом с
// «Проект МВ» (TASK-015, PR 6): паспорт проекта блока (последний изменённый),
// его ревизия и документы; форма, проверка и выпуск — в окне
// `DrillPassportDialog`.
import { useEffect, useRef, useState } from "react";
import { api } from "../../../api/endpoints";
import { ruDate } from "../../../lib/format";
import type { DrillPassport, DrillPassportRevision } from "../../../types/drillPassport";
import { DownloadBar } from "./DownloadBar";
import { DrillPassportDialog } from "./DrillPassportDialog";

export function DrillPassportPanel({ designId, designSaved }: { designId: string; designSaved: boolean }) {
  const [passport, setPassport] = useState<DrillPassport | null>(null);
  const [revision, setRevision] = useState<DrillPassportRevision | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // Закрытие окна перечитывает паспорт: выпуск меняет его версию, а окно
  // могло не успеть её получить (иначе следующее сохранение — 409).
  const [reload, setReload] = useState(0);

  // Другой блок — паспорт прежнего сразу убирается: иначе, пока читается (или
  // не прочитался) список нового, кнопки открыли бы и скачали чужой паспорт.
  // Перечитывание того же блока (после окна) прежний паспорт оставляет на месте.
  const shownFor = useRef(designId);
  useEffect(() => {
    setError("");
    if (shownFor.current !== designId) {
      shownFor.current = designId;
      setPassport(null);
    }
    if (!designId) {
      setPassport(null);
      return;
    }
    let alive = true;
    setLoading(true);
    api.drillPassport
      .list(designId)
      .then((items) => alive && setPassport(items[0] ?? null))
      .catch((reason) => alive && setError(reason instanceof Error ? reason.message : "Не удалось прочитать паспорт на бурение."))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [designId, reload]);

  const revisionId = passport?.current_revision_id ?? null;
  useEffect(() => {
    setRevision(null);
    if (!revisionId) return;
    let alive = true;
    api.drillPassport
      .revision(revisionId)
      .then((loaded) => alive && setRevision(loaded))
      .catch((reason) => alive && setError(reason instanceof Error ? reason.message : "Не удалось прочитать ревизию паспорта."));
    return () => {
      alive = false;
    };
  }, [revisionId]);

  async function create() {
    setBusy(true);
    setError("");
    try {
      setPassport(await api.drillPassport.create({ design_id: designId }));
      setOpen(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось создать паспорт на бурение.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <header><b>Паспорт на бурение</b><span>ГР.05.01</span></header>
      <div className="panel-body">
        {!designId && <small>Сначала сохраните проект блока: паспорт строится по сохранённому проекту.</small>}
        {designId && !designSaved && (
          <small className="frag-warnings">Паспорт строится по сохранённому проекту блока — сохраните правки.</small>
        )}
        {designId && loading && <small>Ищем паспорт блока…</small>}
        {designId && !loading && !passport && !error && (
          <div className="plans-actions">
            <button type="button" className="calculate-button" onClick={() => void create()} disabled={busy}>
              Создать паспорт
            </button>
          </div>
        )}
        {passport && (
          <>
            <small>
              № {passport.passport_no} от {ruDate(passport.passport_date)} ·{" "}
              {revision ? `Ревизия № ${revision.revision_no}` : passport.current_revision_id ? "Ревизия выпущена" : "Ревизия не выпущена"}
            </small>
            <div className="plans-actions">
              <button type="button" className="secondary-button" onClick={() => setOpen(true)}>
                Открыть паспорт
              </button>
            </div>
            {revision && <DownloadBar key={revision.id} revision={revision} />}
          </>
        )}
        {error && <small className="form-error">{error}</small>}
      </div>
      {open && passport && (
        <DrillPassportDialog
          passport={passport}
          designSaved={designSaved}
          onClose={() => {
            setOpen(false);
            setReload((value) => value + 1);
          }}
          onChange={setPassport}
        />
      )}
    </section>
  );
}
