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
 *
 * Шапки на этой странице нет, поэтому ошибки и загрузку рабочего пространства
 * показывает полоса — иначе упавшая смена объекта молча откатывала бы список,
 * а упавшая загрузка оставляла бы его пустым без объяснения.
 */
export function CalcTopStrip({
  teamName,
  objectName,
  objects,
  onObjectChange,
  autosaveStatus,
  metrics,
  warnings,
  workspaceError,
  workspaceLoading,
}: {
  teamName: string;
  objectName: string;
  objects: { id?: string; name: string }[];
  onObjectChange: (name: string) => void;
  autosaveStatus: AutosaveStatus;
  metrics: CalcTopStripMetrics;
  warnings: string[];
  /** Ошибка рабочего пространства: неудачная загрузка или смена объекта. */
  workspaceError: string;
  /** Рабочее пространство ещё загружается — список объектов неполон. */
  workspaceLoading: boolean;
}) {
  const statusText = autosaveStatusText(autosaveStatus);

  return (
    <>
      {workspaceError && <div className="page-error" role="alert">{workspaceError}</div>}
      <div className="calc-top-strip">
        <div className="wb-field"><label>Команда</label><b>{teamName}</b></div>
        <div className="wb-field calc-top-strip-object">
          <label>Объект работ</label>
          <select
            value={objectName}
            onChange={(e) => onObjectChange(e.target.value)}
            disabled={workspaceLoading || !objects.length}
          >
            {objects.map((o) => (
              <option key={o.id || o.name} value={o.name}>{o.name}</option>
            ))}
          </select>
        </div>
        {workspaceLoading && <span className="calc-autosave-status">рабочее пространство загружается…</span>}
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
        // Собственный класс, а не `workspace-bar-caption`: тот рисует
        // разделительную черту внутри шапки, а здесь блок стоит отдельно.
        <div className="calc-warnings">
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
