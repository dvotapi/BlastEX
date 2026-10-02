// Подвал окна «Импорт чертежа» (TASK-013, PR 2–3): площади и объём коротко,
// ошибки и предупреждения контура и кровли у кнопки «Построить блок». Кнопка
// неактивна, пока у контура есть ошибка, кровля не построена, высота уступа
// не подтверждена или предпросмотр ещё считается: ничего не строится молча.
import { ruNumber } from "../../../lib/format";
import type { CadContourResult, CadSurfaceResult } from "../../../types/cad";

function area(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${ruNumber(value, 1)} м²`;
}

export function BuildFooter({
  result,
  pending,
  error,
  busy = false,
  areaLabel = "",
  roof = null,
  roofError = "",
  blocker = null,
  onCancel,
  onBuild,
}: {
  result: CadContourResult | null;
  /** Предпросмотр кровли: объём и высота уступа у кнопки. */
  roof?: CadSurfaceResult | null;
  /** Ошибка запроса кровли (сеть, 422). */
  roofError?: string;
  /** Почему блок пока не строится по кровле (`surfaceState.buildBlocker`). */
  blocker?: string | null;
  pending: boolean;
  /** Сохраняются роли или идёт повторный разбор (контур вот-вот сменится), или
   * выбор площади блока ещё не сохранён на объекте (паспорт с объектом разошлись бы). */
  busy?: boolean;
  /** Какая из площадей — площадь блока (соглашение маркшейдера объекта). */
  areaLabel?: string;
  /** Ошибка запроса предпросмотра (сеть, 422). */
  error: string;
  onCancel: () => void;
  onBuild: (result: CadContourResult) => void;
}) {
  const ready = Boolean(result?.ok) && !pending && !busy && !error && !roofError && !blocker;
  const height = roof?.bench.mean_height_m ?? result?.bench.height_m ?? null;
  const volume = roof?.volume.volume_m3 ?? null;
  return (
    <footer className="cad-build">
      {result?.top ? (
        <p className="cad-build-summary">
          S верх {area(result.top.area_m2)} · S низ {area(result.bottom?.area_m2)} · S ср {area(result.mean_area_m2)}
          {height !== null && ` · уступ ${ruNumber(height, 1)} м`}
          {volume !== null && ` · V ${ruNumber(volume, 0)} м³`}
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
      {result?.ok && (roofError || blocker) && (
        <p className="cad-build-blocker" role="status">
          {roofError || blocker}
        </p>
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
