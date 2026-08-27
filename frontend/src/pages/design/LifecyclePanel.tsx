import {
  allowedTransitions,
  canEditDesigned,
  formatRoleChip,
  isRecordFrozen,
  statusLabel,
  transitionLabel,
} from "../../lib/lifecycle";
import type { DesignLifecycleStatus, LifecycleEvent } from "../../types/design";
import { RoleLegend } from "./RoleBadge";

const KIND_LABELS: Record<string, string> = {
  created: "создан",
  transition: "смена статуса",
  fork: "ревизия",
  revise: "правка проекта",
  record_execution: "запись исполнения",
  record_measured: "запись замера",
  rename: "переименование",
};

export function LifecyclePanel({
  designId,
  status,
  revision,
  parentDesignId,
  designedSha256,
  events,
  busy,
  confirm,
  note,
  onConfirmChange,
  onNoteChange,
  onTransition,
  onFork,
}: {
  designId: string;
  status: string;
  revision: number;
  parentDesignId: string;
  designedSha256: string;
  events: LifecycleEvent[];
  busy: boolean;
  confirm: boolean;
  note: string;
  onConfirmChange: (value: boolean) => void;
  onNoteChange: (value: string) => void;
  onTransition: (toStatus: DesignLifecycleStatus) => void;
  onFork: () => void;
}) {
  const transitions = allowedTransitions(status);
  const frozen = !canEditDesigned(status);
  const closed = isRecordFrozen(status);

  return (
    <section className="panel lifecycle-panel">
      <header>
        <b>Жизненный цикл</b>
        <span className={`lifecycle-pill status-${status}`}>{statusLabel(status)}</span>
      </header>
      <div className="panel-body">
        <RoleLegend />
        <small>
          Статусы Draft…Closed не смешиваются со слоями {formatRoleChip("designed")}, {formatRoleChip("executed")},
          {" "}{formatRoleChip("predicted")} и {formatRoleChip("measured")}. Автоперехода нет.
        </small>
        <div className="lifecycle-meta">
          <span>ревизия {revision || "—"}</span>
          {parentDesignId && <span>родитель {parentDesignId.slice(0, 8)}</span>}
          {designedSha256 && <span>SHA {designedSha256.slice(0, 8)}</span>}
        </div>
        {!designId && <small>Сохраните паспорт, чтобы менять статус.</small>}
        {frozen && !closed && (
          <small className="lifecycle-freeze">
            Слой DESIGNED заморожен. Исполнение и замер можно дополнять. Сценарии остаются оверлеями.
          </small>
        )}
        {closed && (
          <small className="lifecycle-freeze">
            Закрытый паспорт нельзя править. Создайте ревизию — она откроется как черновик.
          </small>
        )}
        <label className="check-row">
          <input type="checkbox" checked={confirm} onChange={(e) => onConfirmChange(e.target.checked)} />
          Подтверждаю смену статуса вручную
        </label>
        <label>
          Комментарий
          <input value={note} onChange={(e) => onNoteChange(e.target.value)} placeholder="необязательно" />
        </label>
        <div className="plans-actions">
          {transitions.map((target) => (
            <button
              key={target}
              type="button"
              className={target === "approved" || target === "closed" ? "calculate-button" : "secondary-button"}
              onClick={() => onTransition(target)}
              disabled={busy || !designId || !confirm}
            >
              {transitionLabel(status, target)}
            </button>
          ))}
          <button type="button" className="secondary-button" onClick={onFork} disabled={busy || !designId}>
            Создать ревизию
          </button>
        </div>
        {events.length > 0 && (
          <ol className="lifecycle-log">
            {events.slice().reverse().slice(0, 6).map((event, index) => (
              <li key={`${event.at}-${event.kind}-${index}`}>
                <b>{KIND_LABELS[event.kind] || event.kind}</b>
                <span>
                  {event.from_status && event.to_status
                    ? `${statusLabel(event.from_status)} → ${statusLabel(event.to_status)}`
                    : event.actor || "система"}
                </span>
                {event.note && <small>{event.note}</small>}
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
