// Предпросмотр контура блока (TASK-013, PR 2): сервер пересчитывает контур
// на каждое изменение способа или участков. Запрос уходит через 250 мс после
// последней правки, а ответ устаревшего запроса не затирает свежий.
import { useEffect, useRef, useState } from "react";
import { api } from "../../../api/endpoints";
import type { CadContourRequest, CadContourResult } from "../../../types/cad";

export const PREVIEW_DELAY_MS = 250;

type Fetcher = (sourceId: string, request: CadContourRequest) => Promise<CadContourResult>;

export function useContourPreview(
  sourceId: string,
  request: CadContourRequest | null,
  fetcher: Fetcher = api.cad.contour,
  /** Меняется, когда сервер пересчитал роли: тот же запрос даёт новый ответ. */
  version = 0,
): { result: CadContourResult | null; pending: boolean; error: string } {
  const [result, setResult] = useState<CadContourResult | null>(null);
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
          setError(reason instanceof Error ? reason.message : "Не удалось построить контур.");
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
