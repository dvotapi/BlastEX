import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/endpoints";
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

  const save = useCallback(async (name: string, value: CalcInputs) => {
    /** Статус — про лист, который открыт сейчас: см. `shouldReportSaveStatus`. */
    const report = (next: AutosaveStatus) => {
      if (shouldReportSaveStatus(name, currentObjectRef.current)) setStatus(next);
    };
    report("saving");
    try {
      await api.saveCalcInputs(name, value);
      if (savedRef.current?.objectName === name) savedRef.current = { objectName: name, inputs: value };
      report("saved");
    } catch {
      report("error");
      // Запись не удалась — правка не должна пропасть: её допишет flush()
      // (например, при смене объекта) или следующая правка через автосейв.
      pendingRef.current = pendingAfterSaveError(pendingRef.current, { objectName: name, inputs: value });
    }
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

  /** Немедленная запись отложенного изменения — перед сменой объекта. */
  const flush = useCallback(async () => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const pending = pendingRef.current;
    pendingRef.current = null;
    if (!pending) return;
    await save(pending.objectName, pending.inputs);
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
