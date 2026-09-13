import { useEffect, useState } from "react";
import { api, type GeometryRequest } from "../../api/endpoints";
import type { BlastGeometryResponse } from "../../types";

/** Пауза перед запросом: протяжка ползунка или набор числа уходят одним запросом. */
export const GEOMETRY_DELAY_MS = 250;

/**
 * Схема заряда одного варианта: `POST /blast/geometry` после паузы в правках.
 * Прошлый ответ остаётся на экране, пока идёт новый, — таблицы сравнения не
 * мигают пустотой, — но `loading` поднимается сразу при изменении запроса:
 * по нему лист помечает сравнение как пересчитываемое и не даёт сохранить в
 * паспорт прошлый блок. Ответ на устаревший запрос отбрасывается.
 * `payload === null` — варианта нет (сетка ещё не рассчитана или объект
 * сменился), схема сбрасывается.
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
    const timer = setTimeout(() => {
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
    }, GEOMETRY_DELAY_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return { geometry, error, loading };
}
