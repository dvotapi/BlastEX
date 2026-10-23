// Подбор раскладки блока: клиентская сторона фоновой задачи (часть 4в).
//
// Сервер считает подбор в дочернем процессе и отдаёт статус по `design_id`.
// Хук при монтировании и смене паспорта один раз спрашивает статус, а пока
// подбор идёт, повторяет запрос раз в секунду (`setTimeout`, не `setInterval`:
// следующий запрос не начнётся, пока не вернулся предыдущий). Уйти со
// страницы и вернуться можно: идущий подбор подхватывается по `design_id`.
import { useCallback, useEffect, useRef, useState } from "react";
import { HttpError } from "../../api/client";
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
export function stableJson(value: unknown): string {
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

/** Запасной несекретный хеш cyrb53 (53 бита) — для страниц без `crypto.subtle`. */
function cyrb53(text: string): string {
  let h1 = 0xdeadbeef;
  let h2 = 0x41c6ce57;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(16).padStart(14, "0");
}

/**
 * Отпечаток входов подбора: SHA-256 от стабильного JSON в шестнадцатеричном
 * виде. `crypto.subtle` есть только в безопасном контексте (https/localhost);
 * иначе — запасной хеш: отпечаток нужен лишь для пометки «устарел».
 */
export async function layoutFingerprint(input: LayoutFingerprintInput): Promise<string> {
  const json = stableJson(input);
  const subtle = typeof crypto !== "undefined" ? crypto.subtle : undefined;
  if (!subtle) return cyrb53(json);
  const digest = await subtle.digest("SHA-256", new TextEncoder().encode(json));
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

/** Ошибки, которые повтор не исправит: нет входа, нет прав, нет такого блока. */
const PERMANENT_STATUSES = new Set([401, 403, 404]);

/** Повторять опрос после сбоя: сеть и 5xx — да, 401/403/404 — нет. */
function retryable(e: unknown): boolean {
  return !(e instanceof HttpError && PERMANENT_STATUSES.has(e.status));
}

function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : "Не удалось выполнить запрос.";
}

export function useLayoutSearch(designId: string | null, fingerprint: string | null): LayoutSearchHook {
  const [status, setStatus] = useState<LayoutSearchStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Поколение: растёт при смене паспорта, размонтировании, старте и остановке;
  // ответ прежнего поколения (и его повторный опрос) отбрасывается.
  const generation = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fingerprintRef = useRef(fingerprint);
  fingerprintRef.current = fingerprint;
  // Последнее известное состояние: после сбоя запроса (сеть, 5xx) опрос
  // продолжается, пока оно running; на 401/403/404 опрос прекращается.
  const lastState = useRef<LayoutSearchStatus["state"] | null>(null);
  const pollRef = useRef<(id: string, gen: number) => void>(() => {});

  const clearTimer = useCallback(() => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  const schedule = useCallback(
    (id: string, gen: number) => {
      clearTimer();
      timer.current = setTimeout(() => {
        timer.current = null;
        pollRef.current(id, gen);
      }, LAYOUT_SEARCH_POLL_MS);
    },
    [clearTimer],
  );

  // Принять статус; пока идёт подбор — запланировать следующий запрос.
  const accept = useCallback(
    (id: string, gen: number, next: LayoutSearchStatus) => {
      if (gen !== generation.current) return;
      lastState.current = next.state;
      setStatus(next);
      setError(null);
      clearTimer();
      if (next.state === "running") schedule(id, gen);
    },
    [clearTimer, schedule],
  );

  pollRef.current = (id, gen) => {
    void (async () => {
      try {
        accept(id, gen, await api.design.layoutSearchStatus(id));
      } catch (e) {
        if (gen !== generation.current) return;
        setError(messageOf(e));
        if (lastState.current === "running" && retryable(e)) schedule(id, gen);
      }
    })();
  };

  useEffect(() => {
    generation.current += 1;
    const gen = generation.current;
    clearTimer();
    lastState.current = null;
    setStatus(null);
    setError(null);
    if (designId) pollRef.current(designId, gen);
    return () => {
      generation.current += 1;
      clearTimer();
    };
  }, [designId, clearTimer]);

  const start = useCallback(
    async (design: BlastDesign) => {
      if (!designId) return;
      if (fingerprintRef.current === null) {
        setError("Подождите, данные блока ещё готовятся.");
        return;
      }
      // Новое поколение: запоздалый ответ опроса, начатого до старта, не перетрёт статус.
      generation.current += 1;
      const gen = generation.current;
      clearTimer();
      setError(null);
      try {
        accept(designId, gen, await api.design.layoutSearchStart(designId, design, fingerprintRef.current));
      } catch (e) {
        if (gen !== generation.current) return;
        setError(messageOf(e));
        // 409: чужой подбор идёт — опрос, прерванный стартом, возобновляем.
        if (lastState.current === "running") schedule(designId, gen);
      }
    },
    [designId, accept, clearTimer, schedule],
  );

  const stop = useCallback(async () => {
    if (!designId) return;
    generation.current += 1;
    const gen = generation.current;
    clearTimer();
    setError(null);
    try {
      accept(designId, gen, await api.design.layoutSearchStop(designId));
    } catch (e) {
      if (gen !== generation.current) return;
      setError(messageOf(e));
      // Остановка не удалась — подбор мог остаться запущенным: опрос продолжаем.
      if (lastState.current === "running") schedule(designId, gen);
    }
  }, [designId, accept, clearTimer, schedule]);

  const stale = Boolean(status?.result) && fingerprint !== null && status?.fingerprint !== fingerprint;
  return { status, start, stop, error, stale };
}
