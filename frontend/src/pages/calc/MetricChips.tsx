/** Показатели выбранного варианта сетки. */
export type Metrics = {
  q: number | null;
  w: number | null;
  x50: number | null;
  oversize: number | null;
};

/** Значение плашки: без расчёта показываем «—», иначе — с заданным числом знаков. */
export function formatMetric(value: number | null, digits: number): string {
  return value === null ? "—" : value.toFixed(digits);
}

/**
 * Плашки выбранного варианта над таблицей «Варианты сетки». Раньше они жили в
 * шапке приложения и переносили её на вторую строку; рядом с таблицей им и по
 * смыслу место — это показатели выделенной строки.
 */
export function MetricChips({ metrics }: { metrics: Metrics }) {
  return (
    <div className="chips" aria-label="Показатели выбранного варианта">
      <div className="chip"><span>Удельный q</span><b>{formatMetric(metrics.q, 2)}<small>кг/м³</small></b></div>
      <div className="chip"><span>ЛНС W</span><b>{formatMetric(metrics.w, 2)}<small>м</small></b></div>
      <div className="chip"><span>x50</span><b>{formatMetric(metrics.x50, 1)}<small>мм</small></b></div>
      <div className="chip"><span>Негабарит</span><b>{formatMetric(metrics.oversize, 1)}<small>%</small></b></div>
    </div>
  );
}
