import { useId } from "react";
import type { AutosaveStatus } from "./useCalcInputsAutosave";
import { filterObjectsByUnit, type ObjectOption, type UnitOption } from "./unitSelection";

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

/**
 * Полоса листа «Расчёт» в шапке приложения: юнит, объект работ и статус
 * автосохранения — одной строкой между заголовком и кнопкой «Выйти».
 *
 * `variant="topbar"` — полоса встроена в верхнюю панель через `createPortal`
 * в узел из `topbarSlot.tsx` (см. `AppShell.tsx`, `CalcPage.tsx`): без своей
 * рамки и фона. `variant="page"` — запасной вид на самой странице, когда
 * слота нет (до его монтирования или вне `AppShell`).
 *
 * Юнит — фильтр списка объектов (см. `unitSelection.ts`); поле не рисуется,
 * если в опубликованной ревизии нет ни одного действующего юнита. Показатели
 * выбранного варианта живут в панели «Варианты сетки» (`MetricChips`), ошибка
 * рабочего пространства и предупреждения — в `CalcWorkspaceNotices`.
 */
export function CalcTopStrip({
  variant,
  objectName,
  objects,
  units,
  unitCode,
  onUnitChange,
  onObjectChange,
  autosaveStatus,
  workspaceLoading,
  sheetReady = true,
}: {
  variant: "topbar" | "page";
  objectName: string;
  objects: ObjectOption[];
  units: UnitOption[];
  /** Выбранный юнит, уже сверенный со справочником; `""` — все юниты. */
  unitCode: string;
  onUnitChange: (code: string) => void;
  onObjectChange: (name: string) => void;
  autosaveStatus: AutosaveStatus;
  /** Рабочее пространство ещё загружается — список объектов неполон. */
  workspaceLoading: boolean;
  /** Настройки объекта загружены. До этого выбор юнита перезаписала бы загрузка. */
  sheetReady?: boolean;
}) {
  const unitId = useId();
  const objectId = useId();
  const statusText = autosaveStatusText(autosaveStatus);
  const visibleObjects = filterObjectsByUnit(objects, unitCode, objectName);

  return (
    <div className={`calc-top-strip${variant === "topbar" ? " in-topbar" : ""}`}>
      {units.length > 0 && (
        <div className="topbar-field topbar-field-unit">
          <label htmlFor={unitId}>Юнит</label>
          <select id={unitId} value={unitCode} onChange={(e) => onUnitChange(e.target.value)} disabled={workspaceLoading || !sheetReady}>
            <option value="">Все юниты</option>
            {units.map((unit) => (
              <option key={unit.code} value={unit.code}>{unit.name}</option>
            ))}
          </select>
        </div>
      )}
      <div className="topbar-field topbar-field-object">
        <label htmlFor={objectId}>Объект</label>
        <select
          id={objectId}
          value={objectName}
          onChange={(e) => onObjectChange(e.target.value)}
          disabled={workspaceLoading || !visibleObjects.length}
        >
          {visibleObjects.map((o) => (
            <option key={o.id || o.name} value={o.name}>{o.name}</option>
          ))}
        </select>
      </div>
      {workspaceLoading && <span className="calc-autosave-status">рабочее пространство загружается…</span>}
      {statusText && (
        <span className="calc-autosave-status" data-status={autosaveStatus}>{statusText}</span>
      )}
    </div>
  );
}

/**
 * Ошибка рабочего пространства (неудачная загрузка или смена объекта) и
 * предупреждения справочников для листа «Расчёт».
 *
 * Отдельно от `CalcTopStrip`: полоса живёт в верхней панели приложения, а
 * этому блоку там не место по высоте.
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
