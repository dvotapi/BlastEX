// Плашка над картой у паспорта, который нельзя править (на проверке, утверждён,
// выполнен, закрыт). Панели «Жизненный цикл» нет (решение владельца 12.11.2026):
// статус старых паспортов не меняется, править их можно только копией-ревизией.
import { isRecordFrozen, statusLabel } from "../../lib/lifecycle";

export function FrozenBanner({ status, saved, unsaved, busy, onFork }: {
  status: string;
  /** Паспорт сохранён: ревизия делается из сохранённой версии. */
  saved: boolean;
  /** Несохранённые правки исполнения или замера: сначала их надо сохранить. */
  unsaved: boolean;
  busy: boolean;
  onFork: () => void;
}) {
  return (
    <div className="lifecycle-banner compact" role="status">
      {isRecordFrozen(status)
        ? "Паспорт закрыт. Создайте ревизию, чтобы править дальше."
        : `Паспорт ${statusLabel(status)}: проект не правится. Чтобы править, создайте ревизию — она откроется черновиком.`}{" "}
      {saved && (
        <button type="button" className="secondary-button" onClick={onFork} disabled={busy || unsaved}
          title={unsaved ? "Сначала сохраните правки: ревизия создаётся из сохранённой версии." : undefined}>
          Создать ревизию
        </button>
      )}
      {saved && unsaved && <small> Сначала сохраните правки.</small>}
    </div>
  );
}
