// Ситуация объекта на странице «Проектирование» (TASK-013, PR 4).
//
// Каталог серий запрашивается по ссылке паспорта (`contour.cad.situation`,
// иначе источник контура) через 300 мс после её смены; объект сервер находит
// сам — по источникам ссылки, иначе активный. Показывается версия, выбранная
// в «Виде» (только просмотр), иначе версия по умолчанию: из ссылки паспорта
// или самая свежая. Геометрия кэшируется по источнику и номеру его правки;
// удалённая версия отмечается и не запрашивается снова.
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/endpoints";
import type { CadSituationCatalogue, CadSituationGeometry } from "../../types/cad";
import type { BlastDesign } from "../../types/design";
import type { SituationShown } from "./situationLayer";

export const SITUATION_DELAY_MS = 300;

export type SituationFetchers = {
  catalogue: (sourceIds: string[]) => Promise<CadSituationCatalogue>;
  geometry: (sourceId: string) => Promise<CadSituationGeometry>;
};

const DEFAULT_FETCHERS: SituationFetchers = {
  catalogue: (ids) => api.cad.situation(ids),
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

/** Ссылка паспорта на ситуацию: запомненные версии, иначе источник контура. */
export function situationReferenceIds(design: BlastDesign): string[] {
  const cad = design.contour.cad;
  if (cad?.situation?.length) return cad.situation.map((item) => item.source_id);
  return cad?.source_id ? [cad.source_id] : [];
}

export function useSituation(
  referenceIds: string[],
  choice: Record<string, string>,
  reloadKey: number,
  fetchers: SituationFetchers = DEFAULT_FETCHERS,
): SituationState {
  const [catalogue, setCatalogue] = useState<CadSituationCatalogue | null>(null);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);
  const sequence = useRef(0);
  // Геометрия по «источник:правка»; упавшие запросы — там же, чтобы не повторять.
  const cache = useRef(new Map<string, CadSituationGeometry>());
  const failed = useRef(new Set<string>());
  const inflight = useRef(new Set<string>());
  const idsKey = referenceIds.join(",");

  useEffect(() => {
    const number = ++sequence.current;
    const timer = setTimeout(() => {
      fetchers.catalogue(idsKey ? idsKey.split(",") : []).then(
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
  }, [idsKey, reloadKey]);

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
      if (cache.current.has(cacheKey) || failed.current.has(cacheKey) || inflight.current.has(cacheKey)) continue;
      inflight.current.add(cacheKey);
      fetchers.geometry(sourceId).then(
        (loaded) => {
          inflight.current.delete(cacheKey);
          cache.current.set(cacheKey, loaded);
          setTick((current) => current + 1);
        },
        () => {
          inflight.current.delete(cacheKey);
          failed.current.add(cacheKey);
          setTick((current) => current + 1);
        },
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wantedKey]);

  return useMemo(() => {
    const shown: SituationShown[] = [];
    const missing = [...(catalogue?.missing ?? [])];
    for (const { seriesKey, sourceId, cacheKey } of wanted) {
      const loaded = cache.current.get(cacheKey);
      if (loaded) shown.push({ seriesKey, geometry: loaded });
      else if (failed.current.has(cacheKey) && !missing.includes(sourceId)) missing.push(sourceId);
    }
    const references = new Set(referenceIds);
    const passport: Record<string, string> = {};
    for (const series of catalogue?.series ?? []) {
      const pinned = series.versions.find((item) => references.has(item.source_id));
      if (pinned) passport[series.key] = pinned.source_id;
    }
    return { catalogue, shown, displayed, passport, missing, error };
    // `tick` — ответ геометрии пришёл в кэш.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalogue, wanted, displayed, error, idsKey, tick]);
}
