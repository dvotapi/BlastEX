// Шаг «Поверхность» окна «Импорт чертежа» (TASK-013, PR 3): какие линии и
// отметки входят в кровлю, проектная подошва, перебур паспорта, качество
// кровли, выбросы с исключением, конфликты отметок и возможные пороги. Кровлю
// строит сервер; наведение на строку списка подсвечивает место на чертеже.
import { ruNumber } from "../../../lib/format";
import type { CadContourResult, CadMeta, CadSource, CadSurfaceResult } from "../../../types/cad";
import { excludePoint, restorePoint, SURFACE_ROLES, toggleSurfaceRole, type SurfaceState } from "./surfaceState";

/** Место на чертеже, которое подсвечивает наведённая строка списка. */
export type SurfaceFocus = { points: number[][]; segments: number[][][] };

export type SurfaceStepProps = {
  source: CadSource;
  meta: CadMeta;
  state: SurfaceState;
  onChange: (next: SurfaceState) => void;
  result: CadSurfaceResult | null;
  pending: boolean;
  error: string;
  /** Предпросмотр контура: без него кровлю строить не по чему. */
  contour: CadContourResult | null;
  /** Перебур паспорта — только показывается: длины считает страница. */
  subdrill: number | null;
  disabled: boolean;
  onFocus: (focus: SurfaceFocus | null) => void;
};

const BUILDERS: Record<string, string> = { cdt: "CDT", scipy: "scipy (запасной путь)" };

function signed(value: number, digits = 1): string {
  return `${value > 0 ? "+" : ""}${ruNumber(value, digits)}`;
}

export function SurfaceStep(props: SurfaceStepProps) {
  const { source, meta, state, onChange, result, pending, error, contour, subdrill, disabled, onFocus } = props;
  const labels = new Map<string, string>(meta.roles.map((role) => [role.code, role.label]));
  const counts = new Map<string, number>();
  for (const entity of source.entities) counts.set(entity.role, (counts.get(entity.role) ?? 0) + 1);
  const autoFloor = contour?.bench.toe_z_m ?? null;
  const quality = result?.quality;
  const focus = (points: number[][], segments: number[][][] = []) => ({
    onMouseEnter: () => onFocus({ points, segments }),
    onMouseLeave: () => onFocus(null),
  });

  if (!contour?.ok) {
    return <p className="cad-hint">Сначала постройте контур блока на шаге «Контур»: кровля строится вокруг него.</p>;
  }

  return (
    <div className="cad-surface">
      <fieldset className="cad-surface-roles" disabled={disabled}>
        <legend>Линии в кровле</legend>
        {SURFACE_ROLES.map((role) => (
          <label key={role.code}>
            <input
              type="checkbox"
              checked={state.roles.includes(role.code)}
              onChange={() => onChange(toggleSurfaceRole(state, role.code))}
            />
            <span>
              {labels.get(role.code) ?? role.code} · {counts.get(role.code) ?? 0}
              <small>{role.hint}</small>
            </span>
          </label>
        ))}
      </fieldset>

      <div className="cad-surface-levels">
        <label className="cad-contour-field">
          <span>Подошва, м</span>
          <input
            inputMode="decimal"
            value={state.floor}
            placeholder={autoFloor !== null ? `из контура: ${ruNumber(autoFloor, 1)}` : "проектная отметка"}
            disabled={disabled}
            onChange={(event) => onChange({ ...state, floor: event.target.value })}
          />
        </label>
        <label className="cad-contour-field">
          <span>Перебур паспорта, м</span>
          <input readOnly value={subdrill !== null ? ruNumber(subdrill, 1) : "—"} />
        </label>
      </div>

      {result && result.issues.length > 0 && (
        <div className="cad-request-error" role="alert">
          {result.issues.map((issue) => (
            <p key={`${issue.code}:${issue.message}`}>{issue.message}</p>
          ))}
        </div>
      )}
      {result && result.warnings.length > 0 && (
        <ul className="cad-warnings">
          {result.warnings.map((warning) => (
            <li key={`${warning.code}:${warning.message}`} className={`cad-warning level-${warning.level}`}>
              {warning.message}
            </li>
          ))}
        </ul>
      )}

      <dl className="cad-areas" role="group" aria-label="Качество кровли">
        <dt>Отметок</dt>
        <dd>{quality ? String(quality.spot_count) : "—"}</dd>
        <dt>Покрытие контура</dt>
        <dd>{quality ? `${ruNumber(quality.coverage_pct, 1)} %` : "—"}</dd>
        <dt>До ближайшей отметки</dt>
        <dd {...(quality?.max_gap_point ? focus([quality.max_gap_point]) : {})}>
          {quality?.max_gap_m != null ? `до ${ruNumber(quality.max_gap_m, 1)} м` : "—"}
        </dd>
        <dt>Средняя высота уступа</dt>
        <dd>{result?.bench.mean_height_m != null ? `${ruNumber(result.bench.mean_height_m, 1)} м` : "—"}</dd>
        <dt>Точек у ограничителей</dt>
        <dd>{quality ? String(quality.snapped_count) : "—"}</dd>
        <dt>Построение</dt>
        <dd>{result ? BUILDERS[result.builder] ?? result.builder : "—"}</dd>
      </dl>
      {result?.plane && <p className="cad-hint">Кровля — плоскость: отметок нет.</p>}

      {result && result.outliers.length > 0 && (
        <section className="cad-surface-list">
          <h4>Выбросы — отклонение от соседей больше 1,5 м</h4>
          <ul aria-label="Выбросы">
            {result.outliers.map((item) => (
              <li key={item.id} {...focus([item.point])}>
                <span>
                  {item.id} · {signed(item.deviation_m)} м
                </span>
                <button type="button" className="secondary-button" disabled={disabled} onClick={() => onChange(excludePoint(state, item.id))}>
                  Исключить
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {result && result.excluded_points.length > 0 && (
        <section className="cad-surface-list">
          <h4>Исключённые отметки</h4>
          <ul aria-label="Исключённые отметки">
            {result.excluded_points.map((item) => (
              <li key={item.id} {...focus([item.point])}>
                <span>
                  {item.id} · {ruNumber(item.point[2], 2)} м
                </span>
                <button type="button" className="secondary-button" disabled={disabled} onClick={() => onChange(restorePoint(state, item.id))}>
                  Вернуть
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {result && result.conflicts.length > 0 && (
        <section className="cad-surface-list">
          <h4>Конфликты отметок — расхождение больше 0,2 м</h4>
          <ul aria-label="Конфликты отметок">
            {result.conflicts.map((item, index) => (
              <li key={`conflict:${index}`} {...focus([item.point])}>
                <span>
                  {item.values.map((value) => `${labels.get(value.role) ?? value.role} ${ruNumber(value.z, 2)}`).join(" / ")}
                  {` → принята ${ruNumber(item.accepted_z, 2)}`}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {result && result.thresholds.length > 0 && (
        <section className="cad-surface-list">
          <h4>Возможные пороги — нижняя бровка выше подошвы больше 0,5 м</h4>
          <ul aria-label="Возможные пороги">
            {result.thresholds.map((item, index) => (
              <li key={`threshold:${index}`} {...focus([], item.segments)}>
                <span>Порог {signed(item.excess_m)} м над подошвой</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {pending && <p className="cad-hint">Строю кровлю…</p>}
      {error && (
        <p className="cad-request-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
