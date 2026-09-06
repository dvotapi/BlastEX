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
 * `variant="topbar"` — полоса встроена в верхнюю панель приложения через
 * `createPortal` в узел из `topbarSlot.tsx` (см. `AppShell.tsx`,
 * `CalcPage.tsx`): без своей рамки и фона, занимает пустующее место рядом с
 * заголовком. `variant="page"` — запасной инлайн-вид на самой странице (нет
 * слота — например, до его монтирования или вне `AppShell`), со своей
 * рамкой и фоном, как до переноса в шапку.
 *
 * Ошибка рабочего пространства и предупреждения справочников сюда не
 * входят ни в одном варианте — их рисует `CalcWorkspaceNotices` отдельно на
 * странице: по высоте им нет места в верхней панели.
 */
export function CalcTopStrip({
  variant,
  teamName,
  objectName,
  objects,
  onObjectChange,
  autosaveStatus,
  metrics,
  workspaceLoading,
}: {
  variant: "topbar" | "page";
  teamName: string;
  objectName: string;
  objects: { id?: string; name: string }[];
  onObjectChange: (name: string) => void;
  autosaveStatus: AutosaveStatus;
  metrics: CalcTopStripMetrics;
  /** Рабочее пространство ещё загружается — список объектов неполон. */
  workspaceLoading: boolean;
}) {
  const statusText = autosaveStatusText(autosaveStatus);

  return (
    <div className={`calc-top-strip${variant === "topbar" ? " in-topbar" : ""}`}>
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
  );
}

/**
 * Ошибка рабочего пространства (неудачная загрузка или смена объекта) и
 * предупреждения справочников для листа «Расчёт».
 *
 * Отдельно от `CalcTopStrip`, потому что теперь полоса живёт в верхней
 * панели приложения, а этому блоку там не место по высоте — он остаётся на
 * странице под заголовком, независимо от того, куда встала полоса.
 */
export function CalcWorkspaceNotices({
  workspaceError,
  warnings,
}: {
  workspaceError: string;
  warnings: string[];
}) {
  if (!workspaceError && !warnings.length) return null;
  return (
    <>
      {workspaceError && <div className="page-error" role="alert">{workspaceError}</div>}
      {warnings.length > 0 && (
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
