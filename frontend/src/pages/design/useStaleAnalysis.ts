// Устаревший результат «Рассчитать тайминг»: времена, изолинии и темп отбойки
// посчитаны по раскладке скважин, породе и сетке a × b на момент расчёта.
// После перестройки сетки, сдвига, включения/выключения или удаления скважин,
// смены породы (границы темпа) или a, b (предел ребра треугольника) их нужно
// сбросить, иначе слой темпа рисует треугольники старой сетки, а панель —
// старую медиану и доли.
import { useEffect, useMemo, useRef } from "react";
import type { Hole } from "../../types/design";

/** Входы расчёта помимо сети коммутации: скважины, порода и сетка a × b. */
export interface AnalysisInputs {
  holes: Hole[];
  rockName: string;
  spacingAM: number | null | undefined;
  burdenBM: number | null | undefined;
}

/** Ключ раскладки: набор скважин, устья в плане, вид и включённость. */
export function holesLayoutKey(holes: Hole[]): string {
  return holes.map((h) => `${h.id}:${h.collar.x}:${h.collar.y}:${h.kind}:${h.enabled ? 1 : 0}`).join("|");
}

/** Ключ входов расчёта: раскладка, порода, a и b. */
export function analysisInputsKey(inputs: AnalysisInputs): string {
  return `${holesLayoutKey(inputs.holes)}#${inputs.rockName ?? ""}#${inputs.spacingAM ?? ""}#${inputs.burdenBM ?? ""}`;
}

/**
 * Зовёт `reset`, когда меняются входы расчёта. Новый массив с той же
 * раскладкой (пересчёт глубин, запись времён срабатывания после расчёта) — не
 * сброс. Правки сети коммутации сбрасывают анализ на месте правки.
 */
export function useStaleAnalysisReset(inputs: AnalysisInputs, reset: () => void): void {
  const { holes, rockName, spacingAM, burdenBM } = inputs;
  const key = useMemo(
    () => analysisInputsKey({ holes, rockName, spacingAM, burdenBM }),
    [holes, rockName, spacingAM, burdenBM],
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
