// Наряд-путёвка ↔ MagEX (TASK-018, PR 7, §7, §9): состояние выписки, нехватка,
// исполнение, «Обновить», «Повторить сейчас», «Отменить в MagEX». Всё, что
// показывается, собирает сервер (`view.magex`, ответы маршрутов `…/magex`):
// окно не знает ни полей справочников, ни контракта MagEX.
import { useEffect, useState } from "react";
import { api } from "../../../../api/endpoints";
import type {
  MagexApproveResult,
  MagexBlasterStatus,
  MagexState,
  MagexVersion,
  MassBlastLayer,
} from "../../../../types/massBlast";
import { errorText } from "../ui";

export function magexState(layer: MassBlastLayer): MagexState | null {
  const state = (layer.view ?? {}).magex as MagexState | undefined;
  return state && state.mode ? state : null;
}

/** Онлайн-наряд: выпуск — «Разрешить», печать — только принятой MagEX ревизии. */
export function isOnline(layer: MassBlastLayer): boolean {
  return magexState(layer)?.mode === "ONLINE";
}

/** Можно ли скачать текущую ревизию: у онлайн-наряда — только принятую MagEX. */
export function canDownload(layer: MassBlastLayer): boolean {
  if (!layer.current_revision_id) return false;
  const state = magexState(layer);
  if (state?.mode !== "ONLINE") return true;
  const version = (state.versions ?? []).find((item) => item.layer_revision_id === layer.current_revision_id);
  // Ревизия без версии MagEX выпущена до включения интеграции — печатается как раньше.
  return !version || version.status === "ACCEPTED";
}

function moment(text: string | null | undefined): string {
  if (!text) return "";
  const date = new Date(text);
  return Number.isNaN(date.getTime()) ? text : date.toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" });
}

function number(text: string | null | undefined): string {
  if (text === null || text === undefined || text === "") return "—";
  const value = Number(text);
  return Number.isFinite(value) ? value.toLocaleString("ru-RU", { maximumFractionDigits: 3 }) : text;
}

function statusText(version: MagexVersion | null | undefined): string {
  if (!version) return "В MagEX не отправлена — печать после «Разрешить».";
  switch (version.status) {
    case "ACCEPTED":
      return `Разрешена: MagEX принял версию ${version.ver}${version.accepted_at ? ` (${moment(version.accepted_at)})` : ""}.`;
    case "PENDING":
      return `Ожидает MagEX: версия ${version.ver} в очереди повтора${version.next_attempt_at ? `, следующая попытка ${moment(version.next_attempt_at)}` : ""}. Печать — после приёма.`;
    case "SENDING":
      return `Версия ${version.ver} отправляется в MagEX…`;
    case "REJECTED":
      return `MagEX не принял версию ${version.ver}: ${version.response?.message || version.response?.code || "отказ"}.`;
    default:
      return `Версия ${version.ver} заменена новой.`;
  }
}

/** Отказ MagEX: нехватка — таблица «позиция / нужно / доступно», остальное — списком полей. */
export function Rejection({ rejection, names }: { rejection: MagexApproveResult["rejection"] | null; names: Record<string, string> }) {
  if (!rejection) return null;
  const details = (rejection.details ?? {}) as Record<string, unknown>;
  const lines = (details.lines ?? []) as Array<{ material_id: string; material: string; required: string; available: string }>;
  const problems = (details.problems ?? []) as Array<{ field: string; code: string; message: string }>;
  const errors = (details.errors ?? []) as Array<{ field: string; message: string }>;
  return (
    <div className="mb-diff" role="alert">
      <b>{rejection.code === "INSUFFICIENT_AVAILABLE" ? "Не хватает ВМ на складе — версия не принята целиком" : rejection.message}</b>
      {lines.length > 0 && (
        <table className="drill-check" aria-label="Нехватка ВМ">
          <thead><tr><th>Позиция</th><th>Нужно</th><th>Доступно</th></tr></thead>
          <tbody>
            {lines.map((line) => (
              <tr key={line.material_id}>
                <th scope="row">{line.material || names[line.material_id] || "позиция MagEX"}</th>
                <td>{number(line.required)}</td>
                <td>{number(line.available)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {rejection.code === "BLASTER_INDEX_CONFLICT" && (
        <small className="form-error">
          В справочнике взрывников MagEX этот индекс принадлежит другому сотруднику: укажите у взрывника в справочнике
          «Взрывники» того же «Сотрудника SafetyMAIN», что и в MagEX.
        </small>
      )}
      {rejection.code === "NARYAD_NUMBER_TAKEN" && (
        <small className="form-error">Номер наряда-путёвки уже занят на этом складе в эту дату: укажите другой №.</small>
      )}
      {problems.map((problem, index) => <small key={index} className="form-error">{problem.message || problem.code}</small>)}
      {errors.map((error, index) => <small key={index} className="form-error">{error.message}</small>)}
    </div>
  );
}

function Execution({ state }: { state: MagexState }) {
  const execution = state.execution;
  if (!execution) return null;
  const names = state.material_names ?? {};
  return (
    <>
      <small className="drill-hint">
        Исполнение в MagEX: <b>{execution.status_label}</b>, версия {execution.version}; прочитано {moment(execution.fetched_at)}.
        {execution.cancellation ? ` Отменена: ${execution.cancellation.reason}.` : ""}
      </small>
      <table className="drill-check" aria-label="Исполнение наряда в MagEX">
        <thead>
          <tr><th>ВМ</th><th>Выписано</th><th>Выдано</th><th>Возвращено</th><th>Израсходовано</th><th>Утрачено</th><th>На руках</th></tr>
        </thead>
        <tbody>
          {execution.lines.map((line) => (
            <tr key={line.material_id}>
              <th scope="row">{names[line.material_id] || "позиция MagEX"}</th>
              {(["ordered", "issued", "returned", "consumed", "lost", "on_hand"] as const).map((key) => (
                <td key={key}>{number(line[key])}{line[`${key}_kg`] !== null && line[`${key}_kg`] !== undefined && line[`${key}_kg`] !== line[key] ? ` (${number(line[`${key}_kg`])} кг)` : ""}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {execution.issued_batches.length > 0 && (
        <small className="drill-hint">
          Выданные партии: {execution.issued_batches.map((batch) => `${names[batch.material_id] || "позиция"} — партия ${batch.batch_no}${batch.manufacturer ? ` (${batch.manufacturer})` : ""}, ${number(batch.issued)}`).join("; ")}.
        </small>
      )}
    </>
  );
}

export function MagexPanel({
  layer,
  rejection,
  busy,
  onState,
  setBusy,
}: {
  layer: MassBlastLayer;
  rejection: MagexApproveResult["rejection"] | null;
  busy: boolean;
  /** Новое состояние MagEX (после «Обновить», «Повторить», «Отменить»): карточка перечитывает слой. */
  onState: () => Promise<void>;
  setBusy: (busy: boolean) => void;
}) {
  const state = magexState(layer);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const [reason, setReason] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const [report, setReport] = useState<MagexBlasterStatus | null>(null);
  const blasterCode = state?.blaster?.code ?? "";
  const online = state?.mode === "ONLINE";

  // Отчитался ли взрывник (предупреждение, не запрет): при открытии и при смене взрывника.
  useEffect(() => {
    if (!online || !blasterCode) {
      setReport(null);
      return;
    }
    let alive = true;
    api.massBlast.magexBlasterStatus(layer.id).then((value) => alive && setReport(value)).catch(() => alive && setReport(null));
    return () => {
      alive = false;
    };
  }, [online, blasterCode, layer.id]);

  if (!state) return null;
  if (state.mode === "OFFLINE") {
    return <small className="frag-warnings">Вне учёта MagEX: {state.reason} Наряд печатается с пометкой «вне учёта MagEX».</small>;
  }

  async function act(action: () => Promise<string>, fallback: string) {
    setBusy(true);
    setMessage(null);
    try {
      const text = await action();
      await onState();
      if (text) setMessage({ text, error: false });
    } catch (error) {
      setMessage({ text: errorText(error, fallback), error: true });
    } finally {
      setBusy(false);
    }
  }

  const latest = state.latest ?? null;
  const accepted = state.accepted_ver !== null && state.accepted_ver !== undefined;
  const cancelled = state.execution?.status === "cancelled";
  const shownRejection = rejection ?? (latest?.status === "REJECTED" ? {
    code: latest.response?.code ?? "", message: latest.response?.message ?? "", details: (latest.response?.details ?? {}) as Record<string, unknown>,
  } : null);
  return (
    <div className="mb-magex" aria-label="MagEX">
      <small className={latest?.status === "REJECTED" ? "form-error" : "drill-hint"}>{statusText(latest)}</small>
      {state.blaster ? (
        <small className="drill-hint">
          Взрывник для MagEX: {state.blaster.name}, индекс {state.blaster.index}
          {state.blaster.source === "PROJECT" ? " (по персоналу проекта)" : ""}.
        </small>
      ) : (
        <small className="frag-warnings">Взрывник не выбран из справочника «Взрывники».</small>
      )}
      {report && report.reported === false && (
        <small className="frag-warnings">
          У взрывника есть неотчитанные наряд-путёвки: {(report.pending ?? []).map((item) => `№ ${item.number} от ${item.issued_on} (${item.site_name})`).join("; ")}.
          Выдачу по новой наряд-путёвке MagEX заблокирует сам, пока ВМ на руках.
        </small>
      )}
      <Rejection rejection={shownRejection} names={state.material_names ?? {}} />
      {state.issued && (
        <small className="drill-hint">
          ВМ выданы: склад, взрывник, дата выписки, № и количества не меняются. Нужно больше ВМ — «Ещё наряд-путёвка».
        </small>
      )}
      <Execution state={state} />
      {state.refresh_error && <small className="frag-warnings">MagEX не ответил: {state.refresh_error}. Показано последнее известное.</small>}
      <div className="plans-actions">
        {accepted && (
          <button type="button" className="secondary-button" disabled={busy}
            onClick={() => void act(async () => {
              const fresh = await api.massBlast.magexState(layer.id, true);
              return fresh.refresh_error ? "" : "Исполнение обновлено.";
            }, "MagEX не ответил.")}>Обновить</button>
        )}
        {latest?.status === "PENDING" && (
          <button type="button" className="secondary-button" disabled={busy}
            onClick={() => void act(async () => {
              const result = await api.massBlast.magexRetry(layer.id);
              return result.outcome === "ACCEPTED" ? "MagEX принял наряд-путёвку." : "MagEX пока недоступен — версия осталась в очереди.";
            }, "Не удалось повторить отправку.")}>Повторить сейчас</button>
        )}
        {accepted && !state.issued && !cancelled && !cancelling && (
          <button type="button" className="secondary-button" disabled={busy} onClick={() => setCancelling(true)}>Отменить в MagEX</button>
        )}
      </div>
      {cancelling && (
        <div className="mb-diff">
          <label className="drill-field wide">
            Причина отмены
            <input value={reason} maxLength={500} disabled={busy} onChange={(event) => setReason(event.target.value)} />
          </label>
          <div className="plans-actions">
            <button type="button" className="calculate-button" disabled={busy || !reason.trim()}
              onClick={() => void act(async () => {
                await api.massBlast.magexCancel(layer.id, { reason: reason.trim() });
                setCancelling(false);
                setReason("");
                return "Наряд-путёвка отменена в MagEX, резерв освобождён.";
              }, "MagEX не отменил наряд-путёвку.")}>Отменить наряд-путёвку</button>
            <button type="button" className="secondary-button" disabled={busy} onClick={() => setCancelling(false)}>Не отменять</button>
          </div>
        </div>
      )}
      {message && <small className={message.error ? "form-error" : "drill-message"}>{message.text}</small>}
    </div>
  );
}
