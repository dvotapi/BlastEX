// Устаревший результат «Рассчитать тайминг»: времена, изолинии и темп отбойки
// посчитаны по раскладке скважин, сети коммутации, породе, сетке a × b,
// контуру блока и виду основной сетки на момент расчёта. После перестройки
// сетки, сдвига, включения/выключения или удаления скважин, любой правки сети
// (в том числе отменой и повтором), смены породы (границы темпа), a, b
// (предел ребра треугольника), контура (отсечение треугольников вне блока)
// или вида основной сетки (какие скважины входят в темп) их нужно сбросить,
// иначе слой темпа рисует треугольники старой сетки, а панель — старую
// медиану и доли.
import { useEffect, useMemo, useRef } from "react";
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
 * Зовёт `reset`, когда меняются входы расчёта. Новый массив с той же
 * раскладкой (пересчёт глубин) и запись времён срабатывания после расчёта —
 * не сброс. Единственный механизм сброса при правках скважин и сети.
 */
export function useStaleAnalysisReset(inputs: AnalysisInputs, reset: () => void): void {
  const { holes, network, rockName, spacingAM, burdenBM, contour, defaultKind } = inputs;
  const key = useMemo(
    () => analysisInputsKey({ holes, network, rockName, spacingAM, burdenBM, contour, defaultKind }),
    [holes, network, rockName, spacingAM, burdenBM, contour, defaultKind],
  );
  const previous = useRef(key);
  const resetRef = useRef(reset);
  resetRef.current = reset;
  useEffect(() => {
    if (previous.current === key) return;
    previous.current = key;
    resetRef.current();
  }, [key]);
}
