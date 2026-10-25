// Подбор раскладки на странице «Проектирование» (часть 4в): отпечаток входов,
// опрос подбора, показ варианта на плане и «Применить».
//
// Форма «Сетка» живёт вне документа паспорта. Отмена «Применить» возвращает
// документ как был: его `pattern_params` — те, по которым построены
// скважины, а не несохранённые правки формы. Когда применение, отмена или
// повтор возвращают документ с параметрами до или после «Применить», форма
// «Сетка» берётся из документа. Вместе с ней — сетка для q в правилах
// зарядов (шаги a × b — от них масса заряда) и форма «Коммутация» (по
// `timing_params` сети документа; сеть, построенная не шаблоном, форму не
// меняет). Вариант с теми же параметрами, но другой сетью меняет одну форму
// «Коммутация». Параметры и сеть узнаются по значению, а не по объекту: после
// «Сохранить» документ приходит с сервера новыми объектами с теми же значениями.
import { useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { api } from "../../api/endpoints";
import {
  DEFAULT_PATTERN_PARAMS,
  DEFAULT_TIE_PARAMS,
  normalizeNetwork,
  type Hole,
  type InitiationNetwork,
  type LayoutSearchVariant,
  type PatternParams,
  type SchemeType,
  type TieParams,
} from "../../types/design";
import { chargeGridOf, type ChargeGrid } from "./designParams";
import type { DesignAction, DesignState } from "./designReducer";
import {
  fingerprintOfJson,
  layoutFingerprint,
  layoutSearchInputs,
  stableJson,
  useLayoutSearch,
  wiredContourHoles,
  type LayoutSearchHook,
} from "./useLayoutSearch";

/** Параметры без ключей со значением undefined — как они уходят на сервер. */
function definedParams(params: PatternParams): Record<string, unknown> {
  return Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined));
}

export type { ChargeGrid };

const SCHEMES: ReadonlySet<string> = new Set<SchemeType>(["row", "echelon", "diagonal_v", "trapezoid", "trunk_chains"]);

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/**
 * Форма «Коммутация» по сети документа: схема и её параметры — из
 * `timing_params` (их пишут построители сети); чего там нет — умолчание.
 * Без схемы в `timing_params` (сеть построена не шаблоном) — null: форма
 * остаётся как есть.
 */
export function tieFormFromNetwork(
  network: InitiationNetwork,
  prev: TieParams,
): { scheme: SchemeType; params: TieParams } | null {
  const timing = network.timing_params ?? {};
  if (typeof timing.scheme !== "string" || !SCHEMES.has(timing.scheme)) return null;
  const scheme = timing.scheme as SchemeType;
  const flank = timing.cut_flank === "left" || timing.cut_flank === "right" ? timing.cut_flank : DEFAULT_TIE_PARAMS.cut_flank;
  return {
    scheme,
    params: {
      ...prev,
      system: network.system ?? prev.system,
      timing_mode: network.timing_mode ?? "",
      cut_flank: flank,
      trunk_ms: finite(timing.trunk_ms) ?? DEFAULT_TIE_PARAMS.trunk_ms,
      chain_ms: finite(timing.chain_ms) ?? DEFAULT_TIE_PARAMS.chain_ms,
      interval_ms: finite(timing.interval_ms) ?? prev.interval_ms,
    },
  };
}

/** То, от чего зависят скважины варианта и их геология (и статус паспорта). */
function geologyInputs(design: DesignState["present"]): string {
  return stableJson({
    contour: design.contour,
    surfaces: design.surfaces,
    domains: design.domains,
    water_table_z_m: design.water_table_z_m,
    lifecycle_status: design.lifecycle_status,
  });
}

export const CHANGED_DURING_GEOLOGY = "Паспорт изменился, пока готовилась геология, — примените вариант ещё раз.";

export interface LayoutSearchApply {
  search: LayoutSearchHook;
  /** Отпечаток текущих входов (null — ещё считается). */
  inputsFingerprint: string | null;
  /** Результат посчитан по другим входам (с поправкой на применённый вариант). */
  stale: boolean;
  previewIndex: number | null;
  setPreviewIndex: (index: number | null) => void;
  /** Вариант на показ поверх плана. */
  preview: LayoutSearchVariant | null;
  /** Применить вариант; подтверждения — забота панели. */
  apply: (variant: LayoutSearchVariant) => Promise<void>;
}

export function useLayoutSearchApply({
  state,
  dispatch,
  patternParams,
  setPatternParams,
  setTieScheme,
  setTieParams,
  setChargeGrid,
  rejectLocked,
  setError,
  onApplied,
}: {
  state: DesignState;
  dispatch: Dispatch<DesignAction>;
  patternParams: PatternParams;
  setPatternParams: Dispatch<SetStateAction<PatternParams>>;
  setTieScheme: (scheme: SchemeType) => void;
  setTieParams: Dispatch<SetStateAction<TieParams>>;
  /** Сетка для q в правилах зарядов: ставится вместе с формой «Сетка». */
  setChargeGrid: (grid: ChargeGrid) => void;
  /** true — проектную часть править нельзя (сообщение ставит страница). */
  rejectLocked: () => boolean;
  setError: (message: string) => void;
  /**
   * Остальное, что страница сбрасывает после новой раскладки. Скважины (после
   * геологии), параметры и сетка для q — варианта: страница ещё не
   * перерисовалась, и её формы — прежние.
   */
  onApplied?: (variant: LayoutSearchVariant, holes: Hole[], params: PatternParams, grid: ChargeGrid) => void;
}): LayoutSearchApply {
  const document = state.present;

  // Отпечаток — по тому, что ушло бы на сервер: контур, съёмка, домены,
  // параметры формы «Сетка», порода, система инициирования и контурные
  // скважины, связанные базовой сетью. Пока он пересчитывается, прежний не
  // действует (null): запуск в это время просит подождать.
  const formParams = useMemo(() => definedParams(patternParams), [patternParams]);
  // Связанные контурные скважины — отдельно: правка скважин (перетаскивание)
  // не пересобирает JSON съёмки, пока список не изменился.
  const wiredKey = useMemo(
    () => wiredContourHoles(document.holes, document.network).join("\n"),
    [document.holes, document.network],
  );
  const networkSystem = document.network?.system ?? null;
  const inputsJson = useMemo(
    () => stableJson(layoutSearchInputs(document, formParams, wiredKey ? wiredKey.split("\n") : [])),
    // Сеть и скважины входят только системой и списком связанных контурных.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [document.contour, document.surfaces, document.domains, formParams, document.rock_name, networkSystem, wiredKey],
  );
  const [inputsFingerprint, setInputsFingerprint] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    setInputsFingerprint(null);
    void fingerprintOfJson(inputsJson).then((value) => {
      if (alive) setInputsFingerprint(value);
    });
    return () => {
      alive = false;
    };
  }, [inputsJson]);

  const search = useLayoutSearch(document.design_id || null, inputsFingerprint);
  const result = search.status?.state === "running" ? null : search.status?.result ?? null;

  const [previewIndex, setPreviewIndex] = useState<number | null>(null);
  // Новый результат (запуск, другой паспорт) — прежний показ снимается.
  useEffect(() => setPreviewIndex(null), [result]);
  const preview = previewIndex === null ? null : result?.best[previewIndex] ?? null;

  // Применённый вариант меняет параметры сетки, и отпечаток входов расходится
  // с подбором, хотя результат свежий: входы после применения помним отдельно.
  // Только для свежего результата — устаревший так и остаётся устаревшим.
  const [applied, setApplied] = useState<{ result: string | null; inputs: string } | null>(null);
  // Сменившиеся границы темпа породы применённый вариант не исправляет.
  const stale =
    search.boundsChanged ||
    (search.stale &&
      !(applied && applied.result === search.status?.fingerprint && applied.inputs === inputsFingerprint));
  const staleRef = useRef(stale);
  staleRef.current = stale;

  // Параметры и сеть документа до и после «Применить» (по значению): когда
  // применение, отмена или повтор возвращают документ с одними из них, формы
  // берутся из документа. Сменились параметры — форма «Сетка», сетка для q в
  // правилах зарядов и форма «Коммутация»; только сеть (вариант с теми же
  // параметрами) — одна форма «Коммутация». Другие отмены и «Сохранить»
  // (значения те же) правок форм не затирают.
  const appliedParams = useRef(new Set<string>());
  const appliedNetworks = useRef(new Set<string>());
  const syncedParams = useRef(stableJson(document.pattern_params));
  const syncedNetwork = useRef(stableJson(document.network));
  useEffect(() => {
    const paramsKey = stableJson(document.pattern_params);
    const networkKey = stableJson(document.network);
    const paramsChanged = syncedParams.current !== paramsKey;
    const networkChanged = syncedNetwork.current !== networkKey;
    if (!paramsChanged && !networkChanged) return;
    syncedParams.current = paramsKey;
    syncedNetwork.current = networkKey;
    const paramsApplied = paramsChanged && appliedParams.current.has(paramsKey);
    const networkApplied = networkChanged && appliedNetworks.current.has(networkKey);
    if (paramsApplied) {
      const params: PatternParams = { ...DEFAULT_PATTERN_PARAMS, ...(document.pattern_params as Partial<PatternParams>) };
      setPatternParams(params);
      setChargeGrid(chargeGridOf(params));
    }
    if (!paramsApplied && !networkApplied) return;
    const tie = tieFormFromNetwork(document.network, DEFAULT_TIE_PARAMS);
    if (!tie) return;
    setTieScheme(tie.scheme);
    const network = document.network;
    setTieParams((prev) => tieFormFromNetwork(network, prev)?.params ?? prev);
  }, [document.pattern_params, document.network, setPatternParams, setChargeGrid, setTieScheme, setTieParams]);

  const applying = useRef(false);
  // Последний документ: «Применить» сверяется с ним после ожидания геологии.
  const latest = useRef(document);
  latest.current = document;
  const rejectLockedRef = useRef(rejectLocked);
  rejectLockedRef.current = rejectLocked;

  async function apply(variant: LayoutSearchVariant) {
    if (applying.current || rejectLocked()) return;
    applying.current = true;
    const wasStale = staleRef.current;
    const resultFingerprint = search.status?.fingerprint ?? null;
    const nextParams: PatternParams = { ...DEFAULT_PATTERN_PARAMS, ...(variant.params as Partial<PatternParams>) };
    const params = definedParams(nextParams);
    const before = document;
    const { domains, water_table_z_m: waterTable } = document;
    try {
      // Геология — до применения, чтобы скважины и их интервалы были одним
      // шагом отмены: без интервалов шаблоны зарядов считают скважины сухими.
      // Уровень воды без доменов тоже даёт интервалы — обводнённые скважины.
      let holes = variant.holes;
      let geologyError = "";
      if ((domains.length || (waterTable !== null && waterTable !== undefined)) && holes.length) {
        try {
          holes = (await api.design.interceptGeology(holes, domains, waterTable)).holes;
        } catch (reason) {
          geologyError = reason instanceof Error ? reason.message : "Не удалось пересечь скважины с доменами.";
        }
      }
      // Пока ждали геологию, паспорт могли сменить, поправить или заблокировать:
      // вариант лёг бы поверх другого документа. Сверка — по значениям:
      // «Сохранить», завершившееся во время ожидания, даёт новые объекты с
      // теми же значениями и применение не отменяет.
      const now = latest.current;
      if (now.design_id !== before.design_id || geologyInputs(now) !== geologyInputs(before) || rejectLockedRef.current()) {
        setError(CHANGED_DURING_GEOLOGY);
        return;
      }
      appliedParams.current.add(stableJson(params));
      // Параметры документа, на который ложится шаг отмены.
      appliedParams.current.add(stableJson(now.pattern_params));
      // Сеть — так же: варианта (как её запишет редьюсер) и прежняя.
      appliedNetworks.current.add(stableJson(normalizeNetwork(variant.network)));
      appliedNetworks.current.add(stableJson(now.network));
      dispatch({ type: "APPLY_LAYOUT", holes, network: variant.network, pattern_params: params });
      setPreviewIndex(null);
      // Формы «Сетка», «Коммутация» и сетка для q — из документа (эффект выше):
      // «Магистраль + цепочки» с флангом варианта.
      setError(geologyError);
      onApplied?.(variant, holes, nextParams, chargeGridOf(nextParams));
      if (!wasStale) {
        // Входы документа после применения: скважины и сеть — варианта.
        const inputs = await layoutFingerprint(layoutSearchInputs({ ...now, holes, network: variant.network }, params));
        setApplied({ result: resultFingerprint, inputs });
      }
    } finally {
      applying.current = false;
    }
  }

  return { search, inputsFingerprint, stale, previewIndex, setPreviewIndex, preview, apply };
}
