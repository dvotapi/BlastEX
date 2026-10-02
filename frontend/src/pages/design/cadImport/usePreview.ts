// Предпросмотр шага окна «Импорт чертежа» (TASK-013): сервер пересчитывает
// контур или кровлю на каждое изменение. Запрос уходит через 250 мс после
// последней правки, а ответ устаревшего запроса не затирает свежий.
import { useEffect, useRef, useState } from "react";

export const PREVIEW_DELAY_MS = 250;

export type Preview<R> = { result: R | null; pending: boolean; error: string };

export function usePreview<Q, R>(
  sourceId: string,
  request: Q | null,
  fetcher: (sourceId: string, request: Q) => Promise<R>,
  /** Меняется, когда сервер пересчитал роли: тот же запрос даёт новый ответ. */
  version: number,
  failure: string,
): Preview<R> {
  const [result, setResult] = useState<R | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const sequence = useRef(0);
  const key = request ? JSON.stringify(request) : "";

  useEffect(() => {
    const number = ++sequence.current;
    if (!request) {
      setResult(null);
      setPending(false);
      setError("");
      return;
    }
    setPending(true);
    const timer = window.setTimeout(() => {
      fetcher(sourceId, request)
        .then((loaded) => {
          if (number !== sequence.current) return;
          setResult(loaded);
          setError("");
        })
        .catch((reason) => {
          if (number !== sequence.current) return;
          setError(reason instanceof Error ? reason.message : failure);
        })
        .finally(() => {
          if (number === sequence.current) setPending(false);
        });
    }, PREVIEW_DELAY_MS);
    return () => window.clearTimeout(timer);
    // Запрос сравнивается по содержимому: объект пересоздаётся на каждой отрисовке.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceId, key, version]);

  return { result, pending, error };
}
