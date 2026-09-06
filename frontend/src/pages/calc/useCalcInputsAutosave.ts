import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/endpoints";
import { AUTOSAVE_DELAY_MS, nextAutosaveAction, type CalcInputs } from "./calcInputs";

export type AutosaveStatus = "idle" | "saving" | "saved" | "error";

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
  const pendingRef = useRef<{ objectName: string; inputs: CalcInputs } | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const save = useCallback(async (name: string, value: CalcInputs) => {
    setStatus("saving");
    try {
      await api.saveCalcInputs(name, value);
      if (savedRef.current?.objectName === name) savedRef.current = { objectName: name, inputs: value };
      setStatus("saved");
    } catch {
      setStatus("error");
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

  return { status, flush };
}
