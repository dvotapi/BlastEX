// Устаревший результат «Рассчитать тайминг»: времена, изолинии и темп отбойки
// посчитаны по раскладке скважин, сети коммутации, породе и сетке a × b на
// момент расчёта. После перестройки сетки, сдвига, включения/выключения или
// удаления скважин, любой правки сети (в том числе отменой и повтором), смены
// породы (границы темпа) или a, b (предел ребра треугольника) их нужно
// сбросить, иначе слой темпа рисует треугольники старой сетки, а панель —
// старую медиану и доли.
import { useEffect, useMemo, useRef } from "react";
import { normalizeNetwork, type Hole, type InitiationNetwork } from "../../types/design";

/** Входы расчёта: скважины, сеть коммутации, порода и сетка a × b. */
export interface AnalysisInputs {
  holes: Hole[];
  network: InitiationNetwork;
  rockName: string;
  spacingAM: number | null | undefined;
  burdenBM: number | null | undefined;
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

/** Ключ входов расчёта: раскладка, сеть, порода, a и b. */
export function analysisInputsKey(inputs: AnalysisInputs): string {
  return `${holesLayoutKey(inputs.holes)}#${networkKey(inputs.network)}#${inputs.rockName ?? ""}#${inputs.spacingAM ?? ""}#${inputs.burdenBM ?? ""}`;
}

/**
 * Зовёт `reset`, когда меняются входы расчёта. Новый массив с той же
 * раскладкой (пересчёт глубин) и запись времён срабатывания после расчёта —
 * не сброс. Единственный механизм сброса при правках скважин и сети.
 */
export function useStaleAnalysisReset(inputs: AnalysisInputs, reset: () => void): void {
  const { holes, network, rockName, spacingAM, burdenBM } = inputs;
  const key = useMemo(
    () => analysisInputsKey({ holes, network, rockName, spacingAM, burdenBM }),
    [holes, network, rockName, spacingAM, burdenBM],
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
