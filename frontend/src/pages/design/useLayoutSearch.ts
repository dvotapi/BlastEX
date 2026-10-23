// Подбор раскладки блока: клиентская сторона фоновой задачи (часть 4в).
//
// Сервер считает подбор в дочернем процессе и отдаёт статус по `design_id`.
// Хук при монтировании и смене паспорта один раз спрашивает статус, а пока
// подбор идёт, повторяет запрос раз в секунду (`setTimeout`, не `setInterval`:
// следующий запрос не начнётся, пока не вернулся предыдущий). Уйти со
// страницы и вернуться можно: идущий подбор подхватывается по `design_id`.
// Старт не удался (409 — подбор уже идёт, сеть) — хук один раз спрашивает
// статус и дальше опрашивает по нему: идущий подбор так подхватывается и
// тогда, когда первый ответ статуса ещё не пришёл. Сбой запроса статуса при
// неизвестном состоянии (сеть, 5xx) — повтор через секунду.
import { useCallback, useEffect, useRef, useState } from "react";
import { HttpError } from "../../api/client";
import { api } from "../../api/endpoints";
import type { BlastDesign, Hole, InitiationNetwork, LayoutSearchStatus } from "../../types/design";

/** Пауза между запросами статуса, пока подбор идёт. */
export const LAYOUT_SEARCH_POLL_MS = 1000;

/** Входы, от которых зависит результат подбора. */
export interface LayoutFingerprintInput {
  contour: unknown;
  surfaces: unknown;
  domains: unknown;
  pattern_params: unknown;
  rock_name: string;
  /** Система инициирования базовой сети: от неё — замедление и реле варианта. */
  network_system: string | null;
  /** Контурные скважины, которые монтирует базовая сеть (по номерам, по порядку). */
  wired_contour_holes: string[];
}

/**
 * Контурные скважины, связанные базовой сетью (связи или стартовые), — то же
 * правило, что `wired_wall_holes` на сервере: по ним перебор решает,
 * монтировать ли контурный ряд варианта.
 */
export function wiredContourHoles(holes: Hole[], network: InitiationNetwork | null | undefined): string[] {
  if (!network) return [];
  const wired = new Set<string>(network.starters ?? []);
  for (const link of [...(network.connectors ?? []), ...(network.surface_connectors ?? [])]) {
    wired.add(link.from_hole);
    wired.add(link.to_hole);
  }
  return holes
    .filter((h) => h.kind === "contour" && wired.has(h.id))
    .map((h) => h.id)
    .sort();
}

/**
 * Входы подбора по паспорту и параметрам формы «Сетка» (как они уйдут на
 * сервер). `wired` — уже посчитанный `wiredContourHoles` (страница держит его
 * отдельно, чтобы правка скважин не пересобирала JSON съёмки).
 */
export function layoutSearchInputs(
  design: Pick<BlastDesign, "contour" | "surfaces" | "domains" | "rock_name" | "network" | "holes">,
  patternParams: Record<string, unknown>,
  wired: string[] = wiredContourHoles(design.holes, design.network),
): LayoutFingerprintInput {
  return {
    contour: design.contour,
    surfaces: design.surfaces,
    domains: design.domains,
    pattern_params: patternParams,
    rock_name: design.rock_name,
    network_system: design.network?.system ?? null,
    wired_contour_holes: wired,
  };
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
  return fingerprintOfJson(stableJson(input));
}

/** Отпечаток уже собранного стабильного JSON (`stableJson`). */
export async function fingerprintOfJson(json: string): Promise<string> {
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
  /** Есть результат, посчитанный по другим входам, чем текущие (или по другим границам темпа). */
  stale: boolean;
  /** Границы темпа породы итога в справочнике уже другие. */
  boundsChanged: boolean;
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
  // повторяется, пока оно running или ещё неизвестно (null — первый запрос
  // или восстановительный после старта не дошёл); на 401/403/404 — стоп.
  const lastState = useRef<LayoutSearchStatus["state"] | null>(null);
  const pollRef = useRef<(id: string, gen: number, keepError?: boolean) => Promise<void>>(async () => {});

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
        void pollRef.current(id, gen);
      }, LAYOUT_SEARCH_POLL_MS);
    },
    [clearTimer],
  );

  // Принять статус; пока идёт подбор — запланировать следующий запрос.
  // `keepError` — ответ после неудачного старта: его ошибка остаётся видна.
  const accept = useCallback(
    (id: string, gen: number, next: LayoutSearchStatus, keepError = false) => {
      if (gen !== generation.current) return;
      lastState.current = next.state;
      setStatus(next);
      if (!keepError) setError(null);
      clearTimer();
      if (next.state === "running") schedule(id, gen);
    },
    [clearTimer, schedule],
  );

  pollRef.current = async (id, gen, keepError = false) => {
    try {
      accept(id, gen, await api.design.layoutSearchStatus(id), keepError);
    } catch (e) {
      if (gen !== generation.current) return;
      // После неудачного старта видна его ошибка, а не сбой запроса статуса.
      if (!keepError) setError(messageOf(e));
      const unknownOrRunning = lastState.current === null || lastState.current === "running";
      if (unknownOrRunning && retryable(e)) schedule(id, gen);
    }
  };

  useEffect(() => {
    generation.current += 1;
    const gen = generation.current;
    clearTimer();
    lastState.current = null;
    setStatus(null);
    setError(null);
    if (designId) void pollRef.current(designId, gen);
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
        // 409 (подбор уже идёт) или сбой: старт прервал опрос, а первый ответ
        // статуса мог ещё не прийти — один раз спрашиваем статус, дальше опрос
        // по нему (идёт — раз в секунду).
        await pollRef.current(designId, gen, true);
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

  const boundsChanged = Boolean(status?.result && status.bounds_changed);
  const stale = boundsChanged || (Boolean(status?.result) && fingerprint !== null && status?.fingerprint !== fingerprint);
  return { status, start, stop, error, stale, boundsChanged };
}
