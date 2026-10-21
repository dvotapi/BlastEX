// Устаревший результат «Рассчитать тайминг»: времена, изолинии и темп отбойки
// посчитаны по раскладке скважин на момент расчёта. После перестройки сетки,
// сдвига, включения/выключения или удаления скважин их нужно сбросить, иначе
// слой темпа рисует треугольники старой сетки, а панель — старую медиану.
import { useEffect, useMemo, useRef } from "react";
import type { Hole } from "../../types/design";

/** Ключ раскладки: набор скважин, устья в плане, вид и включённость. */
export function holesLayoutKey(holes: Hole[]): string {
  return holes.map((h) => `${h.id}:${h.collar.x}:${h.collar.y}:${h.kind}:${h.enabled ? 1 : 0}`).join("|");
}

/**
 * Зовёт `reset`, когда меняется раскладка скважин. Новый массив с той же
 * раскладкой (смена сети коммутации после расчёта, пересчёт глубин) — не сброс.
 */
export function useStaleAnalysisReset(holes: Hole[], reset: () => void): void {
  const key = useMemo(() => holesLayoutKey(holes), [holes]);
  const previous = useRef(key);
  const resetRef = useRef(reset);
  resetRef.current = reset;
  useEffect(() => {
    if (previous.current === key) return;
    previous.current = key;
    resetRef.current();
  }, [key]);
}
