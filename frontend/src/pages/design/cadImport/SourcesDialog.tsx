// «Чертежи объекта» (TASK-013, PR 4): загруженные файлы активного объекта
// работ. Файл открывается в окне «Импорт чертежа» без повторной загрузки или
// удаляется насовсем (решение владельца 03.10.2026): паспорта, построенные по
// нему, сохраняют контур и кровлю, но теряют его ситуацию.
import { useEffect, useRef, useState, type MouseEvent, type SyntheticEvent } from "react";
import { api } from "../../../api/endpoints";
import { ruDate, ruDateTime } from "../../../lib/format";
import type { CadSiteSources, CadSource } from "../../../types/cad";

export type SourcesDialogProps = {
  onClose: () => void;
  onOpenSource: (source: CadSource) => void;
  /** Источник удалён — страница перечитывает ситуацию объекта. */
  onDeleted: (id: string) => void;
  list?: () => Promise<CadSiteSources>;
  load?: (id: string) => Promise<CadSource>;
  remove?: (id: string) => Promise<void>;
};

export function SourcesDialog({
  onClose,
  onOpenSource,
  onDeleted,
  list = api.cad.siteSources,
  load = api.cad.source,
  remove = api.cad.deleteSource,
}: SourcesDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const [data, setData] = useState<CadSiteSources | null>(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  useEffect(() => {
    let alive = true;
    list().then(
      (loaded) => alive && setData(loaded),
      (reason) => alive && setError(reason instanceof Error ? reason.message : "Не удалось загрузить чертежи объекта."),
    );
    return () => {
      alive = false;
    };
  }, [list]);

  function onDialogClose(event: SyntheticEvent<HTMLDialogElement>) {
    if (event.target === ref.current) onClose();
  }

  function onBackdropClick(event: MouseEvent<HTMLDialogElement>) {
    if (event.target === ref.current) onClose();
  }

  async function open(id: string) {
    setBusyId(id);
    setError("");
    try {
      onOpenSource(await load(id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось открыть чертёж.");
    } finally {
      setBusyId("");
    }
  }

  async function drop(id: string, title: string) {
    const question =
      `Удалить «${title}» насовсем? Паспорта, построенные по этому чертежу, сохранят контур и кровлю, ` +
      "но потеряют его ситуацию.";
    if (!window.confirm(question)) return;
    setBusyId(id);
    setError("");
    try {
      await remove(id);
      setData((current) => (current ? { ...current, sources: current.sources.filter((item) => item.id !== id) } : current));
      onDeleted(id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось удалить чертёж.");
    } finally {
      setBusyId("");
    }
  }

  return (
    <dialog
      ref={ref}
      className="cad-sources-dialog"
      aria-labelledby="cad-sources-title"
      onClose={onDialogClose}
      onClick={onBackdropClick}
    >
      <header>
        <b id="cad-sources-title">Чертежи объекта</b>
        <button type="button" className="cad-close" aria-label="Закрыть" onClick={onClose}>
          ×
        </button>
      </header>
      {error && (
        <p className="cad-request-error" role="alert">
          {error}
        </p>
      )}
      {data === null ? (
        !error && <p className="cad-loading">Загружаю…</p>
      ) : !data.site_code ? (
        <p className="cad-sources-note">
          Объект работ не выбран — чертежи без объекта в список не попадают. Выберите объект в шапке.
        </p>
      ) : !data.sources.length ? (
        <p className="cad-sources-note">Чертежей объекта ещё нет.</p>
      ) : (
        <table className="cad-sources">
          <thead>
            <tr>
              <th scope="col">Название</th>
              <th scope="col">Дата съёмки</th>
              <th scope="col">Файл</th>
              <th scope="col">Загружен</th>
              <th scope="col" title="Объектов ситуации">Ситуация</th>
              <th scope="col">
                <span className="sr-only">Действия</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {data.sources.map((item) => (
              <tr key={item.id}>
                <td>
                  <b>{item.title}</b>
                </td>
                <td>{item.survey_date ? ruDate(item.survey_date) : "—"}</td>
                <td className="cad-sources-file" title={item.file_name}>
                  {item.file_name}
                </td>
                <td>{`${ruDateTime(item.uploaded_at)} · ${item.uploaded_by}`}</td>
                <td className="cad-sources-count">{item.situation_count}</td>
                <td className="cad-sources-actions">
                  <button type="button" className="secondary-button" disabled={busyId !== ""} onClick={() => void open(item.id)}>
                    Открыть
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={busyId !== ""}
                    onClick={() => void drop(item.id, item.title)}
                  >
                    Удалить
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data?.truncated && <p className="cad-sources-note">Показаны последние 50 чертежей объекта.</p>}
    </dialog>
  );
}
