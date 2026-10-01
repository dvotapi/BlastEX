// Подвал окна «Импорт чертежа» (TASK-013, PR 2): площади коротко, ошибки и
// предупреждения контура у кнопки «Построить блок». Кнопка неактивна, пока у
// контура есть ошибка или предпросмотр ещё считается: ничего не строится молча.
import { ruNumber } from "../../../lib/format";
import type { CadContourResult } from "../../../types/cad";

function area(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${ruNumber(value, 1)} м²`;
}

export function BuildFooter({
  result,
  pending,
  error,
  busy = false,
  areaLabel = "",
  onCancel,
  onBuild,
}: {
  result: CadContourResult | null;
  pending: boolean;
  /** Сохраняются роли или идёт повторный разбор: контур вот-вот сменится. */
  busy?: boolean;
  /** Какая из площадей — площадь блока (соглашение маркшейдера объекта). */
  areaLabel?: string;
  /** Ошибка запроса предпросмотра (сеть, 422). */
  error: string;
  onCancel: () => void;
  onBuild: (result: CadContourResult) => void;
}) {
  const ready = Boolean(result?.ok) && !pending && !busy && !error;
  const height = result?.bench.height_m ?? null;
  return (
    <footer className="cad-build">
      {result?.top ? (
        <p className="cad-build-summary">
          S верх {area(result.top.area_m2)} · S низ {area(result.bottom?.area_m2)} · S ср {area(result.mean_area_m2)}
          {height !== null && ` · уступ ${ruNumber(height, 1)} м`}
          {areaLabel && ` · площадь блока — ${areaLabel}`}
        </p>
      ) : (
        <p className="cad-build-summary">{pending ? "Считаю контур…" : "Контур не задан — шаг «Контур»."}</p>
      )}
      {(error || (result && result.issues.length > 0)) && (
        <div className="cad-build-error" role="alert">
          {error || result?.issues.map((issue) => <p key={`${issue.code}:${issue.message}`}>{issue.message}</p>)}
        </div>
      )}
      {result && result.warnings.length > 0 && (
        <ul className="cad-build-warnings">
          {result.warnings.map((warning) => (
            <li key={`${warning.code}:${warning.message}`}>{warning.message}</li>
          ))}
        </ul>
      )}
      <div className="cad-build-actions">
        <button type="button" className="secondary-button" onClick={onCancel}>
          Отмена
        </button>
        <button type="button" className="primary-button" disabled={!ready} onClick={() => result && onBuild(result)}>
          Построить блок
        </button>
      </div>
    </footer>
  );
}
