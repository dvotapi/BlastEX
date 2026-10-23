// Подбор раскладки блока: клиентская сторона фоновой задачи (часть 4в).
//
// Сервер считает подбор в дочернем процессе и отдаёт статус по `design_id`.
// Хук при монтировании и смене паспорта один раз спрашивает статус, а пока
// подбор идёт, повторяет запрос раз в секунду (`setTimeout`, не `setInterval`:
// следующий запрос не начнётся, пока не вернулся предыдущий). Уйти со
// страницы и вернуться можно: идущий подбор подхватывается по `design_id`.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/endpoints";
import type { BlastDesign, LayoutSearchStatus } from "../../types/design";

/** Пауза между запросами статуса, пока подбор идёт. */
export const LAYOUT_SEARCH_POLL_MS = 1000;

/** Входы, от которых зависит результат подбора. */
export interface LayoutFingerprintInput {
  contour: unknown;
  surfaces: unknown;
  domains: unknown;
  pattern_params: unknown;
  rock_name: string;
}

/** JSON с ключами по алфавиту на любой глубине: порядок ключей не влияет на текст. */
function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map((item) => stableJson(item === undefined ? null : item)).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const record = value as Record<string, unknown>;
    const parts = Object.keys(record)
      .filter((key) => record[key] !== undefined)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableJson(record[key])}`);
    return `{${parts.join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}

/** Отпечаток входов подбора: SHA-256 от стабильного JSON, в шестнадцатеричном виде. */
export async function layoutFingerprint(input: LayoutFingerprintInput): Promise<string> {
  const bytes = new TextEncoder().encode(stableJson(input));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

export interface LayoutSearchHook {
  status: LayoutSearchStatus | null;
  start: (design: BlastDesign) => Promise<void>;
  stop: () => Promise<void>;
  error: string | null;
  /** Есть результат, посчитанный по другим входам, чем текущие. */
  stale: boolean;
}

function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : "Не удалось выполнить запрос.";
}

export function useLayoutSearch(designId: string | null, fingerprint: string | null): LayoutSearchHook {
  const [status, setStatus] = useState<LayoutSearchStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Поколение: растёт при смене паспорта и размонтировании; ответ прежнего
  // поколения (и его повторный опрос) отбрасывается.
  const generation = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fingerprintRef = useRef(fingerprint);
  fingerprintRef.current = fingerprint;

  const clearTimer = useCallback(() => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  // Принять статус; пока идёт подбор — запланировать следующий запрос.
  const accept = useCallback(
    (id: string, gen: number, next: LayoutSearchStatus) => {
      if (gen !== generation.current) return;
      setStatus(next);
      clearTimer();
      if (next.state === "running") {
        timer.current = setTimeout(() => {
          timer.current = null;
          void poll(id, gen);
        }, LAYOUT_SEARCH_POLL_MS);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [clearTimer],
  );

  const poll = useCallback(
    async (id: string, gen: number) => {
      try {
        const next = await api.design.layoutSearchStatus(id);
        accept(id, gen, next);
      } catch (e) {
        if (gen !== generation.current) return;
        setError(messageOf(e));
      }
    },
    [accept],
  );

  useEffect(() => {
    generation.current += 1;
    const gen = generation.current;
    clearTimer();
    setStatus(null);
    setError(null);
    if (designId) void poll(designId, gen);
    return () => {
      generation.current += 1;
      clearTimer();
    };
  }, [designId, poll, clearTimer]);

  const start = useCallback(
    async (design: BlastDesign) => {
      if (!designId) return;
      const gen = generation.current;
      setError(null);
      try {
        const next = await api.design.layoutSearchStart(designId, design, fingerprintRef.current ?? "");
        accept(designId, gen, next);
      } catch (e) {
        if (gen !== generation.current) return;
        setError(messageOf(e));
      }
    },
    [designId, accept],
  );

  const stop = useCallback(async () => {
    if (!designId) return;
    const gen = generation.current;
    setError(null);
    try {
      const next = await api.design.layoutSearchStop(designId);
      accept(designId, gen, next);
    } catch (e) {
      if (gen !== generation.current) return;
      setError(messageOf(e));
    }
  }, [designId, accept]);

  const stale = Boolean(status?.result) && fingerprint !== null && status?.fingerprint !== fingerprint;
  return { status, start, stop, error, stale };
}
