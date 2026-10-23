// Подбор раскладки на странице «Проектирование» (часть 4в): отпечаток входов,
// опрос подбора, показ варианта на плане и «Применить».
//
// Форма «Сетка» живёт вне документа паспорта, поэтому «Применить» пишет в
// шаг отмены и её значения на момент применения, а форма берётся из
// документа, когда отмена или повтор возвращают одни из этих параметров.
import { useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { api } from "../../api/endpoints";
import {
  DEFAULT_PATTERN_PARAMS,
  type Hole,
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

  // Параметры, записанные в документ «Применить» (и до него): когда отмена или
  // повтор возвращают документ с одним из них, форма «Сетка» берётся оттуда.
  const appliedParams = useRef(new WeakSet<object>());
  const syncedParams = useRef(document.pattern_params);
  useEffect(() => {
    if (syncedParams.current === document.pattern_params) return;
    syncedParams.current = document.pattern_params;
    if (!appliedParams.current.has(document.pattern_params)) return;
    setPatternParams({ ...DEFAULT_PATTERN_PARAMS, ...(document.pattern_params as Partial<PatternParams>) });
  }, [document.pattern_params, setPatternParams]);

  const applying = useRef(false);

  async function apply(variant: LayoutSearchVariant) {
    if (applying.current || rejectLocked()) return;
    applying.current = true;
    const wasStale = staleRef.current;
    const resultFingerprint = search.status?.fingerprint ?? null;
    const nextParams: PatternParams = { ...DEFAULT_PATTERN_PARAMS, ...(variant.params as Partial<PatternParams>) };
    const params = definedParams(nextParams);
    const previous = formParams;
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
      appliedParams.current.add(params);
      appliedParams.current.add(previous);
      dispatch({ type: "APPLY_LAYOUT", holes, network: variant.network, pattern_params: params, previous_pattern_params: previous });
      setPreviewIndex(null);
      // «Коммутация» — схема варианта: «Магистраль + цепочки» с его флангом.
      setTieScheme("trunk_chains");
      setTieParams((prev) => ({ ...prev, system: variant.network.system, cut_flank: variant.cut_flank, timing_mode: "" }));
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
