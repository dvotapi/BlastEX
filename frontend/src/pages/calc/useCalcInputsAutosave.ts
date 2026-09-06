import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/endpoints";
import { isLatestObjectRequest } from "../../app/workspaceObjectSwitch";
import { AUTOSAVE_DELAY_MS, nextAutosaveAction, type CalcInputs } from "./calcInputs";

export type AutosaveStatus = "idle" | "saving" | "saved" | "error";

type PendingSave = { objectName: string; inputs: CalcInputs };

/**
 * Что остаётся в очереди записи после неудачной попытки сохранить `failed`.
 * Пока запрос летел, форма могла успеть измениться ещё раз — тогда `current`
 * уже содержит более новую очередь (полный снимок листа, а не дельту), и она
 * сама покрывает то, что не сохранилось; трогать её нельзя, иначе новая правка
 * потеряется. Если очереди нет — возвращаем упавшую запись, чтобы её дописал
 * `flush()` при смене объекта или следующая правка через тот же автосейв.
 */
export function pendingAfterSaveError(current: PendingSave | null, failed: PendingSave): PendingSave | null {
  return current ?? failed;
}

/**
 * Относится ли результат записи к объекту, который сейчас открыт на листе.
 *
 * `flush()` при смене объекта дописывает настройки прошлого объекта уже после
 * того, как полоса показывает новый: статус «сохранение…»/«сохранено» от той
 * записи относился бы к чужому листу, поэтому его не показываем.
 */
export function shouldReportSaveStatus(savedObjectName: string, currentObjectName: string): boolean {
  return savedObjectName === currentObjectName;
}

type SavedValue = { objectName: string; inputs: CalcInputs | null } | null;
type WrittenValue = { objectName: string; inputs: CalcInputs; seq: number };

/**
 * Что оставить в `savedRef` после того, как запись с номером `written.seq`
 * завершилась (успешно долетела до сервера).
 *
 * PUT-запросы теперь идут по очереди (см. docstring хука ниже), поэтому на
 * сервер они приходят в порядке отправки — но завершиться дольше может и та
 * запись, что была отправлена раньше (например, если очередь успела принять
 * ещё одну правку, пока предыдущий PUT ещё не ответил). Применяем результат,
 * только если `written.seq` — самый свежий из выданных (`isLatestObjectRequest`
 * из `workspaceObjectSwitch.ts`, переиспользуем ту же проверку гонки, что и
 * для смены объекта): иначе более старый ответ откатил бы `savedRef` назад,
 * и следующая правка не понадобилась бы для его исправления.
 *
 * Также не трогаем `savedRef`, если он уже относится к другому объекту —
 * лист успел переключиться, и текущая запись хвостом дописывает прошлый.
 */
export function nextSavedAfterWrite(current: SavedValue, written: WrittenValue, latestSeq: number): SavedValue {
  if (!isLatestObjectRequest(written.seq, latestSeq)) return current;
  if (current?.objectName !== written.objectName) return current;
  return { objectName: written.objectName, inputs: written.inputs };
}

/**
 * Автосохранение настроек листа за объектом работ.
 *
 * Пишем через `AUTOSAVE_DELAY_MS` после последнего изменения и только если
 * настройки отличаются от последних сохранённых. До того как настройки текущего
 * объекта загружены (`ready`), не пишем вовсе — иначе умолчания формы затрут
 * сохранённое. Момент, когда `ready` стал `true`, и есть отсечка «уже
 * сохранено»: лист в этот миг равен тому, что лежит на сервере.
 *
 * Ошибка не блокирует лист: статус становится `error`, а следующая правка
 * пользователя снова поставит запись в очередь.
 *
 * Записи идут по очереди: каждый `save()` кладёт свой PUT в промис-цепочку
 * `queueRef` (`queueRef.current = queueRef.current.then(run, run)`), поэтому
 * на сервер они уходят строго в порядке вызова, а не параллельно — раньше
 * два PUT могли лететь одновременно, и более старый, ответивший последним,
 * откатывал `savedRef` к устаревшему значению. У каждой записи есть
 * монотонный номер `writeSeqRef`; какой из завершившихся ответов применять к
 * `savedRef`/статусу, решает чистая `nextSavedAfterWrite` (статус — `shouldReportSaveStatus`
 * вместе с той же проверкой номера). `flush()` ждёт очередь целиком, а не
 * только свою дозапись, — если к моменту вызова в очереди уже есть
 * незавершённый PUT, уйти со страницы/сменить объект можно только после него.
 */
export function useCalcInputsAutosave({
  objectName,
  inputs,
  ready,
}: {
  objectName: string;
  inputs: CalcInputs | null;
  ready: boolean;
}): { status: AutosaveStatus; flush: () => Promise<void> } {
  const [status, setStatus] = useState<AutosaveStatus>("idle");
  /** Последнее сохранённое значение вместе с объектом, к которому оно относится. */
  const savedRef = useRef<{ objectName: string; inputs: CalcInputs | null } | null>(null);
  /** Изменение, ожидающее записи: его дописывает `flush()` перед сменой объекта. */
  const pendingRef = useRef<PendingSave | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** Объект, открытый на листе сейчас: с ним сверяется статус записи. */
  const currentObjectRef = useRef(objectName);
  currentObjectRef.current = objectName;
  /** Хвост очереди записи: следующий `save()` встаёт после уже идущих. */
  const queueRef = useRef<Promise<void>>(Promise.resolve());
  /** Монотонный номер записи — какая из них последняя, см. `nextSavedAfterWrite`. */
  const writeSeqRef = useRef(0);

  const save = useCallback((name: string, value: CalcInputs) => {
    const seq = ++writeSeqRef.current;
    /** Статус — про лист, который открыт сейчас, и только если это ещё
     * последняя выданная запись: см. `shouldReportSaveStatus`. */
    const report = (next: AutosaveStatus) => {
      if (shouldReportSaveStatus(name, currentObjectRef.current) && isLatestObjectRequest(seq, writeSeqRef.current)) {
        setStatus(next);
      }
    };
    report("saving");
    const run = async () => {
      try {
        await api.saveCalcInputs(name, value);
        savedRef.current = nextSavedAfterWrite(savedRef.current, { objectName: name, inputs: value, seq }, writeSeqRef.current);
        report("saved");
      } catch {
        report("error");
        // Запись не удалась — правка не должна пропасть: её допишет flush()
        // (например, при смене объекта) или следующая правка через автосейв.
        pendingRef.current = pendingAfterSaveError(pendingRef.current, { objectName: name, inputs: value });
      }
    };
    const task = queueRef.current.then(run, run);
    queueRef.current = task;
    return task;
  }, []);

  // Отсечка «уже сохранено» для объекта, настройки которого только что загружены.
  useEffect(() => {
    if (!ready) return;
    if (savedRef.current?.objectName === objectName) return;
    savedRef.current = { objectName, inputs };
    setStatus("idle");
  }, [ready, objectName, inputs]);

  useEffect(() => {
    if (!ready || !inputs) return;
    const saved = savedRef.current;
    // Отсечка ещё не выставлена (или относится к прошлому объекту) — ждём её,
    // не трогая отложенное изменение: его допишет `flush()`.
    if (!saved || saved.objectName !== objectName) return;
    if (nextAutosaveAction(saved.inputs, inputs, 0) !== "wait") {
      pendingRef.current = null;
      return;
    }
    pendingRef.current = { objectName, inputs };
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      pendingRef.current = null;
      void save(objectName, inputs);
    }, AUTOSAVE_DELAY_MS);
    return () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [ready, objectName, inputs, save]);

  /** Немедленная запись отложенного изменения — перед сменой объекта.
   * Ждёт очередь целиком, а не только свою дозапись: если в ней уже есть
   * незавершённый PUT (например, только что запущенный отложенным таймером),
   * дальше (смена объекта, уход со страницы) можно идти лишь после него. */
  const flush = useCallback(async () => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const pending = pendingRef.current;
    pendingRef.current = null;
    if (pending) save(pending.objectName, pending.inputs);
    await queueRef.current;
  }, [save]);

  // Уход со страницы (размонтирование) не должен терять до 800 мс
  // несохранённых правок — дописываем отложенное сразу же.
  useEffect(() => {
    return () => {
      void flush();
    };
  }, [flush]);

  return { status, flush };
}
