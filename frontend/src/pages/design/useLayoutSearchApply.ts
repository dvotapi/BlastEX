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
// меняет).
import { useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { api } from "../../api/endpoints";
import {
  DEFAULT_PATTERN_PARAMS,
  DEFAULT_TIE_PARAMS,
  type Hole,
  type InitiationNetwork,
  type LayoutSearchVariant,
  type PatternParams,
  type SchemeType,
  type TieParams,
} from "../../types/design";
import type { DesignAction, DesignState } from "./designReducer";
import { layoutFingerprint, useLayoutSearch, type LayoutSearchHook } from "./useLayoutSearch";

/** Параметры без ключей со значением undefined — как они уходят на сервер. */
function definedParams(params: PatternParams): Record<string, unknown> {
  return Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined));
}

/** Сетка для q в правилах зарядов: шаги a × b раскладки. */
export interface ChargeGrid {
  grid_a_m: number;
  grid_b_m: number;
}

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
  /** Остальное, что страница сбрасывает после новой раскладки. */
  onApplied?: (variant: LayoutSearchVariant, holes: Hole[], params: PatternParams) => void;
}): LayoutSearchApply {
  const document = state.present;

  // Отпечаток — по тому, что ушло бы на сервер: контур, съёмка, домены,
  // параметры формы «Сетка» и порода.
  const formParams = useMemo(() => definedParams(patternParams), [patternParams]);
  const [inputsFingerprint, setInputsFingerprint] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    void layoutFingerprint({
      contour: document.contour,
      surfaces: document.surfaces,
      domains: document.domains,
      pattern_params: formParams,
      rock_name: document.rock_name,
    }).then((value) => {
      if (alive) setInputsFingerprint(value);
    });
    return () => {
      alive = false;
    };
  }, [document.contour, document.surfaces, document.domains, formParams, document.rock_name]);

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
  const stale =
    search.stale &&
    !(applied && applied.result === search.status?.fingerprint && applied.inputs === inputsFingerprint);
  const staleRef = useRef(stale);
  staleRef.current = stale;

  // Параметры документа до и после «Применить»: когда применение, отмена или
  // повтор возвращают документ с одним из них, форма «Сетка», сетка для q в
  // правилах зарядов и форма «Коммутация» берутся из документа. Другие отмены
  // (параметры — тот же объект) правок форм не затирают.
  const appliedParams = useRef(new WeakSet<object>());
  const syncedParams = useRef(document.pattern_params);
  useEffect(() => {
    if (syncedParams.current === document.pattern_params) return;
    syncedParams.current = document.pattern_params;
    if (!appliedParams.current.has(document.pattern_params)) return;
    const params: PatternParams = { ...DEFAULT_PATTERN_PARAMS, ...(document.pattern_params as Partial<PatternParams>) };
    setPatternParams(params);
    setChargeGrid({ grid_a_m: params.spacing_a_m, grid_b_m: params.burden_b_m });
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
      let holes = variant.holes;
      let geologyError = "";
      if (domains.length && holes.length) {
        try {
          holes = (await api.design.interceptGeology(holes, domains, waterTable)).holes;
        } catch (reason) {
          geologyError = reason instanceof Error ? reason.message : "Не удалось пересечь скважины с доменами.";
        }
      }
      // Пока ждали геологию, паспорт могли сменить, поправить или заблокировать:
      // вариант лёг бы поверх другого документа.
      const now = latest.current;
      if (
        now.design_id !== before.design_id ||
        now.contour !== before.contour ||
        now.domains !== before.domains ||
        now.lifecycle_status !== before.lifecycle_status ||
        rejectLockedRef.current()
      ) {
        setError(CHANGED_DURING_GEOLOGY);
        return;
      }
      appliedParams.current.add(params);
      appliedParams.current.add(before.pattern_params);
      dispatch({ type: "APPLY_LAYOUT", holes, network: variant.network, pattern_params: params });
      setPreviewIndex(null);
      // Формы «Сетка», «Коммутация» и сетка для q — из документа (эффект выше):
      // «Магистраль + цепочки» с флангом варианта.
      setError(geologyError);
      onApplied?.(variant, holes, nextParams);
      if (!wasStale) {
        const inputs = await layoutFingerprint({
          contour: document.contour,
          surfaces: document.surfaces,
          domains,
          pattern_params: params,
          rock_name: document.rock_name,
        });
        setApplied({ result: resultFingerprint, inputs });
      }
    } finally {
      applying.current = false;
    }
  }

  return { search, inputsFingerprint, stale, previewIndex, setPreviewIndex, preview, apply };
}
