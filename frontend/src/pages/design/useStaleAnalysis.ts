// Устаревший результат «Рассчитать тайминг»: времена, изолинии и темп отбойки
// посчитаны по раскладке скважин, сети коммутации, породе, сетке a × b,
// контуру блока и виду основной сетки на момент расчёта. После перестройки
// сетки, сдвига, включения/выключения или удаления скважин, любой правки сети
// (в том числе отменой и повтором), смены породы (границы темпа), a, b
// (предел ребра треугольника), контура (отсечение треугольников вне блока)
// или вида основной сетки (какие скважины входят в темп) их нужно сбросить,
// иначе слой темпа рисует треугольники старой сетки, а панель — старую
// медиану и доли.
import { useCallback, useEffect, useMemo, useRef } from "react";
import { normalizeNetwork, type BlockContour, type Hole, type InitiationNetwork } from "../../types/design";

/** Входы расчёта: скважины, сеть, порода, сетка a × b, контур и вид основной сетки. */
export interface AnalysisInputs {
  holes: Hole[];
  network: InitiationNetwork;
  rockName: string;
  spacingAM: number | null | undefined;
  burdenBM: number | null | undefined;
  /** Контур блока: вершины в плане и пометки откосов. */
  contour: Pick<BlockContour, "vertices" | "free_faces">;
  /** Вид основной сетки (`pattern_params.default_kind`). */
  defaultKind: string | null | undefined;
}

/** Ключ раскладки: набор скважин, устья в плане, вид и включённость. */
export function holesLayoutKey(holes: Hole[]): string {
  return holes.map((h) => `${h.id}:${h.collar.x}:${h.collar.y}:${h.kind}:${h.enabled ? 1 : 0}`).join("|");
}

/**
 * Подпись сети: стартеры, связи, замедления — всё, кроме времён срабатывания
 * (`firing_events`), которые «Рассчитать тайминг» сам записывает в сеть.
 */
export function networkKey(network: InitiationNetwork): string {
  const { firing_events: _firingEvents, ...rest } = normalizeNetwork(network);
  return JSON.stringify(rest);
}

/**
 * Ключ контура: вершины в плане и пометки откосов. Отметки вершин не в счёт —
 * темп отбойки отсекает треугольники по контуру в плане.
 */
export function contourKey(contour: AnalysisInputs["contour"]): string {
  const vertices = contour.vertices.map((v) => `${v.x}:${v.y}`).join(",");
  const faces = contour.free_faces.map((edge) => edge.join("-")).join(",");
  return `${vertices}/${faces}`;
}

/** Ключ входов расчёта: раскладка, сеть, порода, a, b, контур и вид основной сетки. */
export function analysisInputsKey(inputs: AnalysisInputs): string {
  return [
    holesLayoutKey(inputs.holes),
    networkKey(inputs.network),
    inputs.rockName ?? "",
    inputs.spacingAM ?? "",
    inputs.burdenBM ?? "",
    contourKey(inputs.contour),
    inputs.defaultKind ?? "",
  ].join("#");
}

/**
 * Ответ запроса, начатого при ключе входов `startKey`, ещё относится к
 * документу: входы с тех пор не менялись. Иначе его выбрасывают — сброс уже
 * случился, и поздний ответ вернул бы старый результат (и старые времена
 * срабатывания в сеть).
 */
export function isResponseCurrent(startKey: string, currentKey: string): boolean {
  return startKey === currentKey;
}

/**
 * Зовёт `reset`, когда меняется `key`; первый рендер — не сброс. Возвращает
 * чтение текущего ключа: его берут при старте запроса и сверяют с ним ответ
 * (`isResponseCurrent`), чтобы ответ, пришедший после правки, не лёг поверх.
 */
export function useKeyChangeReset(key: string, reset: () => void): () => string {
  const current = useRef(key);
  current.current = key;
  const previous = useRef(key);
  const resetRef = useRef(reset);
  resetRef.current = reset;
  useEffect(() => {
    if (previous.current === key) return;
    previous.current = key;
    resetRef.current();
  }, [key]);
  return useCallback(() => current.current, []);
}

/**
 * Зовёт `reset`, когда меняются входы расчёта. Новый массив с той же
 * раскладкой (пересчёт глубин) и запись времён срабатывания после расчёта —
 * не сброс. Единственный механизм сброса при правках скважин и сети.
 * Возвращает чтение текущего ключа входов — для отбраковки позднего ответа.
 */
export function useStaleAnalysisReset(inputs: AnalysisInputs, reset: () => void): () => string {
  const { holes, network, rockName, spacingAM, burdenBM, contour, defaultKind } = inputs;
  const key = useMemo(
    () => analysisInputsKey({ holes, network, rockName, spacingAM, burdenBM, contour, defaultKind }),
    [holes, network, rockName, spacingAM, burdenBM, contour, defaultKind],
  );
  return useKeyChangeReset(key, reset);
}

/**
 * Ключ геометрии подошвы для инженерных карт: подошва по углу (пунктир
 * «подошва по углу») строится от бровки контура по углу откоса и высоте
 * уступа у каждой скважины, а показатели карт — по устьям и глубинам скважин.
 * Поэтому в ключ входят вершины контура в плане, откосы, отметки и угол
 * уступа, замена или правка контура с чертежа, устья (с отметкой) и забои
 * скважин, их вид и включённость.
 */
export function mapsInputsKey(holes: Hole[], contour: BlockContour): string {
  const bench = contour.bench;
  const cad = contour.cad ? `${contour.cad.source_id}:${contour.cad.built_at}:${contour.cad.edited ? 1 : 0}` : "";
  const holesKey = holes
    .map((h) => `${h.id}:${h.collar.x}:${h.collar.y}:${h.collar.z}:${h.toe.x}:${h.toe.y}:${h.toe.z}:${h.kind}:${h.enabled ? 1 : 0}`)
    .join("|");
  return [
    contourKey(contour),
    `${bench.crest_z_m}:${bench.toe_z_m}:${bench.face_angle_deg}`,
    cad,
    holesKey,
  ].join("#");
}

/** Пауза перед повторным запросом карт: серия правок — один запрос. */
export const MAPS_REFRESH_DELAY_MS = 300;

/**
 * Перезапросить карты после смены их входов, если пользователь их смотрел:
 * карты были загружены (или запрошены — ответ в полёте) или выбрана метрика
 * инженерных карт. Иначе карты
 * запрашиваются по требованию — только убираем.
 */
export function shouldRefetchMaps(mapsLoaded: boolean, mapMetricSelected: boolean): boolean {
  return mapsLoaded || mapMetricSelected;
}

/**
 * Инженерные карты при смене `key`: сразу `clear` (старый пунктир «подошва
 * по углу» не висит), а если `active()` на момент смены — `refetch` через
 * `delayMs` после последней смены. Так обычный путь «Построить сетку →
 * карты → автопересчёт глубин» оставляет карту на экране. Поздние ответы
 * отбрасывает сам `refetch` по ключу (`isResponseCurrent`). Возвращает
 * чтение текущего ключа.
 */
export function useStaleMapsRefresh(
  key: string,
  options: { active: () => boolean; clear: () => void; refetch: () => void; delayMs?: number },
): () => string {
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (timer.current !== null) clearTimeout(timer.current);
  }, []);
  return useKeyChangeReset(key, () => {
    const { active, clear, delayMs = MAPS_REFRESH_DELAY_MS } = optionsRef.current;
    // Решение — до очистки: после `clear` карт уже нет.
    const refetchWanted = active();
    clear();
    if (timer.current !== null) {
      // Запрос уже запланирован серией правок — переносим его.
      clearTimeout(timer.current);
    } else if (!refetchWanted) {
      return;
    }
    timer.current = setTimeout(() => {
      timer.current = null;
      optionsRef.current.refetch();
    }, delayMs);
  });
}
