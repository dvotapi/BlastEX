import { useEffect, useState } from "react";
import { api, type GeometryRequest } from "../../api/endpoints";
import type { BlastGeometryResponse } from "../../types";

/**
 * Схема заряда одного варианта: `POST /blast/geometry` при каждом изменении
 * запроса. Прошлый ответ остаётся на экране, пока идёт новый: таблицы
 * сравнения не мигают пустотой на каждое движение ползунка. Ответ на
 * устаревший запрос отбрасывается. `payload === null` — варианта нет
 * (сетка ещё не рассчитана или объект сменился), схема сбрасывается.
 */
export function useHoleGeometry(payload: GeometryRequest | null): {
  geometry: BlastGeometryResponse | null;
  error: string;
  loading: boolean;
} {
  const [geometry, setGeometry] = useState<BlastGeometryResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  // Сравнение по содержимому: объект запроса пересобирается на каждом рендере листа.
  const key = payload ? JSON.stringify(payload) : "";

  useEffect(() => {
    if (!payload) {
      setGeometry(null);
      setError("");
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    api
      .geometry(payload)
      .then((response) => {
        if (cancelled) return;
        setGeometry(response);
        setError("");
      })
      .catch((reason) => {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : "Ошибка расчёта схемы заряда.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return { geometry, error, loading };
}
