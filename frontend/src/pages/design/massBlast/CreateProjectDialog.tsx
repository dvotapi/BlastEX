// Окно «Создать проект МВ» (TASK-018, PR 6, В2): дата и время взрыва и
// блоки проекта. Остальное сервер заполняет сам — из справочника объекта и
// прошлого проекта того же объекта. Дату взрыва не подставляем.
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "../../../api/endpoints";
import type { DesignSummary } from "../../../types/design";
import type { MassBlastProjectV2 } from "../../../types/massBlast";
import { errorText } from "./ui";

export function CreateProjectDialog({
  designId,
  designName,
  onClose,
  onCreated,
}: {
  designId: string;
  designName: string;
  onClose: () => void;
  onCreated: (project: MassBlastProjectV2) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [blastDate, setBlastDate] = useState("");
  const [blastTime, setBlastTime] = useState("");
  const [designs, setDesigns] = useState<DesignSummary[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set([designId]));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal?.();
    let alive = true;
    api.design
      .listPlans()
      .then((result) => alive && setDesigns(result.items.filter((item) => item.design_id !== designId)))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [designId]);

  function toggle(id: string, checked: boolean) {
    setSelected((current) => {
      const next = new Set(current);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!blastDate) {
      setError("Укажите дату взрыва.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const ids = [designId, ...designs.map((item) => item.design_id).filter((id) => selected.has(id))];
      onCreated(await api.massBlast.newProject({ design_ids: ids, blast_date: blastDate, blast_time: blastTime }));
    } catch (reason) {
      setError(errorText(reason, "Не удалось создать проект."));
    } finally {
      setBusy(false);
    }
  }

  function close() {
    ref.current?.close?.();
    onClose();
  }

  return (
    <dialog ref={ref} className="cad-help mb-create" aria-labelledby="mb-create-title" onCancel={(event) => { event.preventDefault(); close(); }}>
      <header>
        <b id="mb-create-title">Новый проект массового взрыва</b>
        <button type="button" aria-label="Закрыть" onClick={close}>×</button>
      </header>
      <form className="cad-help-body drill-form" onSubmit={(event) => void submit(event)}>
        <div className="drill-grid">
          <div className="drill-field">
            <label htmlFor="mb-create-date">Дата взрыва</label>
            <input id="mb-create-date" type="date" value={blastDate} required onChange={(event) => setBlastDate(event.target.value)} disabled={busy} />
          </div>
          <div className="drill-field">
            <label htmlFor="mb-create-time">Время взрыва</label>
            <input id="mb-create-time" type="time" value={blastTime} onChange={(event) => setBlastTime(event.target.value)} disabled={busy} />
            <small className="drill-hint">без времени распорядок не выпускается</small>
          </div>
        </div>
        <fieldset>
          <legend>Блоки проекта</legend>
          <label className="drill-ack">
            <input type="checkbox" checked disabled /> {designName || "этот блок"}
          </label>
          {designs.map((item) => (
            <label key={item.design_id} className="drill-ack">
              <input type="checkbox" checked={selected.has(item.design_id)} disabled={busy} onChange={(event) => toggle(item.design_id, event.target.checked)} />
              {item.name}
            </label>
          ))}
          <small className="drill-hint">В одном массовом взрыве — до 5 блоков. Блок берётся из сохранённого проекта блока.</small>
        </fieldset>
        <small className="drill-hint">
          Объект, заказчик, люди и постоянные тексты распорядка заполнятся сами — из справочника объекта и прошлого
          проекта того же объекта. Всё можно поправить в окне проекта.
        </small>
        {error && <small className="form-error">{error}</small>}
        <div className="plans-actions">
          <button type="submit" className="calculate-button" disabled={busy}>Создать проект</button>
          <button type="button" className="secondary-button" onClick={close} disabled={busy}>Отмена</button>
        </div>
      </form>
    </dialog>
  );
}
