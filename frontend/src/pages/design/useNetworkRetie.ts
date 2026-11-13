// Пересчёт коммутации после сдвига скважин (TASK-017, PR 3).
//
// Сеть шаблона, не правленая руками, перестраивается сама: после отпускания
// мыши — сразу, после серии стрелок — через `MOVE_SERIES_GAP_MS` после
// последнего нажатия (`DesignState.autoRetie`). Правленая сеть только
// помечается «устаревшей по геометрии» — пересчёт кнопкой (подтверждение —
// забота страницы). Запрос — `POST /design/tie/generate` с параметрами из
// сети; ответ применяется к тому документу, по которому спрошен
// (`RETIE_NETWORK.base`), автопересчёт — в запись отмены сдвига. Любая смена
// документа отменяет незавершённый запрос (`AbortController`).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/endpoints";
import { normalizeNetwork, type BlastDesign, type InitiationNetwork, type TieGenerateResponse } from "../../types/design";
import { MOVE_SERIES_GAP_MS, type DesignAction, type DesignState } from "./designReducer";
import {
  GEOMETRY_STALE_TEXT,
  isGeometryStale,
  isNetworkEmpty,
  networkChangeSummary,
  networkOrigin,
  retieRequest,
  retieSummaryText,
  RETIE_INCOMPLETE_HINT,
  type NetworkOrigin,
} from "./retie";
import { networkKey } from "./useStaleAnalysis";

export type RetieFetcher = (
  ...args: Parameters<typeof api.design.tie>
) => Promise<TieGenerateResponse>;

export interface NetworkRetieView {
  /** Скважины сдвинуты после построения сети. */
  stale: boolean;
  staleText: string;
  origin: NetworkOrigin;
  /** Кнопку «Пересчитать коммутацию» можно нажать. */
  canRecompute: boolean;
  /** Почему нельзя (параметров не хватает); иначе пусто. */
  hint: string;
  pending: boolean;
  error: string;
  /** Сводка последнего пересчёта, пока в документе та же сеть. */
  summary: string;
  /** Пересчитать сейчас (своя запись отмены). */
  recompute: () => void;
}

export function useNetworkRetie({
  state,
  dispatch,
  editable,
  fetcher = api.design.tie,
  onApplied,
}: {
  state: DesignState;
  dispatch: (action: DesignAction) => void;
  /** Проектную часть можно править (статус паспорта). */
  editable: boolean;
  fetcher?: RetieFetcher;
  /** Пересчитанная сеть принята документом: предупреждения построителя — странице. */
  onApplied?: (network: InitiationNetwork, warnings: string[]) => void;
}): NetworkRetieView {
  const present = state.present;
  const network = useMemo(() => normalizeNetwork(present.network), [present.network]);
  const latest = useRef(present);
  latest.current = present;
  const onAppliedRef = useRef(onApplied);
  onAppliedRef.current = onApplied;
  const controller = useRef<AbortController | null>(null);
  // Запрос и ошибка — со своим документом: после смены документа не видны.
  const [pendingFor, setPendingFor] = useState<BlastDesign | null>(null);
  const [failure, setFailure] = useState<{ base: BlastDesign; text: string } | null>(null);
  const [summary, setSummary] = useState<{ key: string; text: string } | null>(null);

  const run = useCallback(
    (base: BlastDesign, merge: boolean) => {
      const request = retieRequest(normalizeNetwork(base.network));
      if (!request || !base.holes.length) return;
      controller.current?.abort();
      const own = new AbortController();
      controller.current = own;
      setPendingFor(base);
      setFailure(null);
      fetcher(base.holes, request.scheme, request.params as Parameters<RetieFetcher>[2], base.contour, { signal: own.signal })
        .then((response) => {
          if (own.signal.aborted || latest.current !== base) return;
          const next = normalizeNetwork(response.network);
          setSummary({ key: networkKey(next), text: retieSummaryText(networkChangeSummary(normalizeNetwork(base.network), next)) });
          dispatch({ type: "RETIE_NETWORK", network: next, base, merge });
          onAppliedRef.current?.(next, response.warnings ?? []);
        })
        .catch((reason) => {
          if (own.signal.aborted || latest.current !== base) return;
          setFailure({ base, text: reason instanceof Error ? reason.message : "Не удалось пересчитать коммутацию." });
        })
        .finally(() => {
          if (controller.current === own) controller.current = null;
          setPendingFor((current) => (current === base ? null : current));
        });
    },
    [dispatch, fetcher],
  );

  // Смена документа отменяет незавершённый запрос; сдвиг сети шаблона —
  // пересчёт сам (после серии стрелок — когда серия кончилась).
  const auto = state.autoRetie;
  useEffect(() => {
    let timer: number | undefined;
    if (editable && auto && auto.present === present && isGeometryStale(normalizeNetwork(present.network))) {
      timer = window.setTimeout(() => run(present, true), auto.series ? MOVE_SERIES_GAP_MS : 0);
    }
    return () => {
      if (timer !== undefined) window.clearTimeout(timer);
      controller.current?.abort();
      controller.current = null;
    };
  }, [present, auto, editable, run]);

  const stale = !isNetworkEmpty(network) && isGeometryStale(network);
  const complete = retieRequest(network) !== null;
  const currentKey = useMemo(() => networkKey(network), [network]);
  return {
    stale,
    staleText: GEOMETRY_STALE_TEXT,
    origin: networkOrigin(network),
    canRecompute: editable && complete && present.holes.length > 0 && pendingFor !== present,
    hint: complete ? "" : RETIE_INCOMPLETE_HINT,
    pending: pendingFor === present,
    error: failure?.base === present ? failure.text : "",
    summary: summary?.key === currentKey ? summary.text : "",
    recompute: () => run(latest.current, false),
  };
}
