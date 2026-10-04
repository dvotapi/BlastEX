// Ситуация объекта на странице «Проектирование» (TASK-013, PR 4).
//
// Каталог серий запрашивается по ссылке паспорта (`contour.cad.situation`)
// через 300 мс после её смены; без запомненных версий источник контура только
// находит объект (`site_source_id`), версия не закрепляется. Объект сервер
// находит сам — по источникам ссылки, активный — только без ссылки. Показывается версия, выбранная
// в «Виде» (только просмотр), иначе версия по умолчанию: из ссылки паспорта
// или самая свежая. Геометрия кэшируется по источнику и номеру его правки;
// удалённая версия отмечается и не запрашивается снова.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/endpoints";
import type { CadSituationCatalogue, CadSituationGeometry } from "../../types/cad";
import type { BlastDesign } from "../../types/design";
import type { SituationShown } from "./situationLayer";

export const SITUATION_DELAY_MS = 300;
// Общий пустой выбор: новый `{}` на каждый рендер пересчитывал бы модель «Вида».
const NO_CHOICE: Record<string, string> = {};

export type SituationFetchers = {
  catalogue: (sourceIds: string[], siteSourceId?: string) => Promise<CadSituationCatalogue>;
  geometry: (sourceId: string) => Promise<CadSituationGeometry>;
};

const DEFAULT_FETCHERS: SituationFetchers = {
  catalogue: (ids, siteSourceId) => api.cad.situation(ids, siteSourceId),
  geometry: (id) => api.cad.sourceSituation(id),
};

export type SituationState = {
  catalogue: CadSituationCatalogue | null;
  /** Загруженная геометрия показанных версий, в порядке серий каталога. */
  shown: SituationShown[];
  /** Серия → показанная версия (источник). */
  displayed: Record<string, string>;
  /** Серия → версия из ссылки паспорта — «паспорт спроектирован по…». */
  passport: Record<string, string>;
  /** Ссылки паспорта и показанные версии, которых больше нет. */
  missing: string[];
  error: string;
};

/**
 * Дата версии, выбранная в «Виде», — только у своего паспорта: другой паспорт
 * открывается со своей ситуацией (из ссылки или самой свежей).
 */
export function useSituationChoice(
  passportKey: string,
): [Record<string, string>, (seriesKey: string, sourceId: string) => void] {
  const [state, setState] = useState<{ key: string; choice: Record<string, string> }>({ key: passportKey, choice: {} });
  const choice = state.key === passportKey ? state.choice : NO_CHOICE;
  const choose = useCallback(
    (seriesKey: string, sourceId: string) =>
      setState((current) => ({
        key: passportKey,
        choice: { ...(current.key === passportKey ? current.choice : {}), [seriesKey]: sourceId },
      })),
    [passportKey],
  );
  return [choice, choose];
}

/**
 * Ссылка паспорта на ситуацию. `pinned` — версии запомнены «Построить блок»;
 * иначе источник контура нужен только чтобы найти объект, и его удаление —
 * не «удалённая версия ситуации».
 */
export type SituationReference = { ids: string[]; pinned: boolean };

export function situationReference(design: BlastDesign): SituationReference {
  const cad = design.contour.cad;
  if (cad?.situation?.length) return { ids: cad.situation.map((item) => item.source_id), pinned: true };
  return { ids: cad?.source_id ? [cad.source_id] : [], pinned: false };
}

function notFound(reason: unknown): boolean {
  return typeof reason === "object" && reason !== null && (reason as { status?: unknown }).status === 404;
}

export function useSituation(
  reference: SituationReference,
  choice: Record<string, string>,
  reloadKey: number,
  fetchers: SituationFetchers = DEFAULT_FETCHERS,
): SituationState {
  const [catalogue, setCatalogue] = useState<CadSituationCatalogue | null>(null);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);
  const sequence = useRef(0);
  // Геометрия по «источник:правка». Удалённые (404) не запрашиваются снова;
  // сбои (сеть, 5xx) повторяются при следующей перезагрузке каталога.
  const cache = useRef(new Map<string, CadSituationGeometry>());
  const gone = useRef(new Set<string>());
  const broken = useRef(new Set<string>());
  const inflight = useRef(new Set<string>());
  const referenceIds = reference.ids;
  const idsKey = referenceIds.join(",");
  const requestKey = `${reference.pinned ? "pinned" : "site"}:${idsKey}`;

  useEffect(() => {
    const number = ++sequence.current;
    broken.current.clear();
    const timer = setTimeout(() => {
      const ids = idsKey ? idsKey.split(",") : [];
      const request = reference.pinned || !ids.length ? fetchers.catalogue(ids) : fetchers.catalogue([], ids[0]);
      request.then(
        (loaded) => {
          if (number !== sequence.current) return;
          setCatalogue(loaded);
          setError("");
        },
        () => {
          if (number !== sequence.current) return;
          setCatalogue(null);
          setError("Не удалось загрузить ситуацию объекта.");
        },
      );
    }, SITUATION_DELAY_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey, reloadKey]);

  const displayed = useMemo(() => {
    const result: Record<string, string> = {};
    for (const series of catalogue?.series ?? []) {
      const chosen = choice[series.key];
      result[series.key] = series.versions.some((item) => item.source_id === chosen) ? chosen : series.default_source_id;
    }
    return result;
  }, [catalogue, choice]);

  // Ключи кэша показанных версий: источник и номер его правки.
  const wanted = useMemo(() => {
    const keys: Array<{ seriesKey: string; sourceId: string; cacheKey: string }> = [];
    for (const series of catalogue?.series ?? []) {
      const sourceId = displayed[series.key];
      const version = series.versions.find((item) => item.source_id === sourceId);
      if (version) keys.push({ seriesKey: series.key, sourceId, cacheKey: `${sourceId}:${version.revision}` });
    }
    return keys;
  }, [catalogue, displayed]);
  const wantedKey = wanted.map((item) => item.cacheKey).join(",");

  useEffect(() => {
    for (const { sourceId, cacheKey } of wanted) {
      if (
        cache.current.has(cacheKey) ||
        gone.current.has(cacheKey) ||
        broken.current.has(cacheKey) ||
        inflight.current.has(cacheKey)
      ) {
        continue;
      }
      inflight.current.add(cacheKey);
      fetchers.geometry(sourceId).then(
        (loaded) => {
          inflight.current.delete(cacheKey);
          cache.current.set(cacheKey, loaded);
          setTick((current) => current + 1);
        },
        (reason) => {
          inflight.current.delete(cacheKey);
          (notFound(reason) ? gone : broken).current.add(cacheKey);
          setTick((current) => current + 1);
        },
      );
    }
    // Перезагрузка каталога (`reloadKey`) повторяет запросы, упавшие сбоем.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wantedKey, reloadKey, catalogue]);

  return useMemo(() => {
    const shown: SituationShown[] = [];
    // Источник контура без запомненных версий нужен только для поиска объекта.
    const missing = reference.pinned ? [...(catalogue?.missing ?? [])] : [];
    let failures = 0;
    for (const { seriesKey, sourceId, cacheKey } of wanted) {
      const loaded = cache.current.get(cacheKey);
      if (loaded) shown.push({ seriesKey, geometry: loaded });
      else if (gone.current.has(cacheKey) && !missing.includes(sourceId)) missing.push(sourceId);
      else if (broken.current.has(cacheKey)) failures += 1;
    }
    // «Паспорт спроектирован по…» — только запомненные версии, не источник контура.
    const references = new Set(reference.pinned ? referenceIds : []);
    const passport: Record<string, string> = {};
    for (const series of catalogue?.series ?? []) {
      const pinned = series.versions.find((item) => references.has(item.source_id));
      if (pinned) passport[series.key] = pinned.source_id;
    }
    const geometryError = failures ? `Не удалось загрузить ситуацию: версий — ${failures}. Повторю при обновлении.` : "";
    return { catalogue, shown, displayed, passport, missing, error: error || geometryError };
    // `tick` — ответ геометрии пришёл в кэш.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalogue, wanted, displayed, error, idsKey, reference.pinned, tick]);
}
