import type { AutosaveStatus } from "./useCalcInputsAutosave";

/** Значение плашки: без расчёта показываем «—», иначе — с заданным числом знаков. */
export function formatMetric(value: number | null, digits: number): string {
  return value === null ? "—" : value.toFixed(digits);
}

function autosaveStatusText(status: AutosaveStatus): string {
  switch (status) {
    case "saved":
      return "сохранено";
    case "saving":
      return "сохранение…";
    case "error":
      return "ошибка сохранения";
    default:
      return "";
  }
}

export type CalcTopStripMetrics = {
  q: number | null;
  w: number | null;
  x50: number | null;
  oversize: number | null;
};

/**
 * Компактная полоса листа «Расчёт»: команда и объект работ вместо шапки
 * рабочего пространства (её на этой странице не показываем), статус
 * автосохранения и плашки с результатом выбранного варианта.
 */
export function CalcTopStrip({
  teamName,
  objectName,
  objects,
  onObjectChange,
  autosaveStatus,
  metrics,
  warnings,
}: {
  teamName: string;
  objectName: string;
  objects: { id?: string; name: string }[];
  onObjectChange: (name: string) => void;
  autosaveStatus: AutosaveStatus;
  metrics: CalcTopStripMetrics;
  warnings: string[];
}) {
  const statusText = autosaveStatusText(autosaveStatus);

  return (
    <>
      <div className="calc-top-strip">
        <div className="wb-field"><label>Команда</label><b>{teamName}</b></div>
        <div className="wb-field calc-top-strip-object">
          <label>Объект работ</label>
          <select value={objectName} onChange={(e) => onObjectChange(e.target.value)}>
            {objects.map((o) => (
              <option key={o.id || o.name} value={o.name}>{o.name}</option>
            ))}
          </select>
        </div>
        {statusText && (
          <span className="calc-autosave-status" data-status={autosaveStatus}>{statusText}</span>
        )}
        <div className="metric-chips">
          <div className="metric-chip"><span>Удельный расход</span><strong>{formatMetric(metrics.q, 2)}</strong><small>кг/м³</small></div>
          <div className="metric-chip"><span>ЛНС W</span><strong>{formatMetric(metrics.w, 2)}</strong><small>м</small></div>
          <div className="metric-chip"><span>Средний кусок x50</span><strong>{formatMetric(metrics.x50, 1)}</strong><small>мм</small></div>
          <div className="metric-chip"><span>Негабарит</span><strong>{formatMetric(metrics.oversize, 1)}</strong><small>%</small></div>
        </div>
      </div>
      {warnings.length > 0 && (
        <div className="workspace-bar-caption">
          <details>
            <summary>Предупреждения справочников ({warnings.length})</summary>
            <ul>
              {warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </details>
        </div>
      )}
    </>
  );
}
