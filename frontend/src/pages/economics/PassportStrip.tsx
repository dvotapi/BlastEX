import type { Ref } from "react";
import { passportMetrics, passportRows } from "./passportSummary";
import type { TechnicalPassport } from "../../types/blockEconomics";

/**
 * Полоса паспорта под шапкой приложения: объект, паспорт, ревизия, имя
 * сценария и «Сохранить сценарий» одной строкой; ниже — четыре плашки
 * геометрии, а остальные величины паспорта с источниками — под
 * раскрывашкой. Полоса закреплена при прокрутке (`.passport-strip` в
 * styles.css), поэтому страница меряет её высоту через `ref` и на неё
 * отступает липкую колонку параметров.
 */
export function PassportStrip({
  ref,
  passports,
  selectedId,
  onSelect,
  passport,
  siteLabel,
  revisionLabel,
  runName,
  runPlaceholder,
  onRunName,
  onSave,
  saveDisabled,
  status,
}: {
  /** React 19: ref — обычный проп функционального компонента, forwardRef не нужен. */
  ref?: Ref<HTMLDivElement>;
  passports: TechnicalPassport[];
  selectedId: string;
  onSelect: (id: string) => void;
  /** Паспорт, по которому считается модель; null — ещё не загружен. */
  passport: TechnicalPassport | null;
  siteLabel: string;
  revisionLabel: string;
  runName: string;
  runPlaceholder: string;
  onRunName: (name: string) => void;
  onSave: () => void;
  saveDisabled: boolean;
  /** Сообщение о сохранении или переносе услуги; пусто — не показывать. */
  status: string;
}) {
  return (
    <div className="passport-strip" ref={ref}>
      <div className="passport-strip-fields">
        <label>
          Объект работ
          <input value={siteLabel} title={passport?.site_code ?? ""} disabled />
        </label>
        <label>
          Технический паспорт
          <select value={selectedId} onChange={(event) => onSelect(event.target.value)}>
            {passports.map((item) => (
              <option key={item.id} value={item.id}>
                {item.object_name} · вер. {item.version_no}
              </option>
            ))}
          </select>
        </label>
        <label>
          Ревизия справочников
          <input value={revisionLabel} title={passport?.reference_revision_id ?? ""} disabled />
        </label>
        <label>
          Имя сценария
          <input
            value={runName}
            placeholder={runPlaceholder}
            onChange={(event) => onRunName(event.target.value)}
          />
        </label>
        <div className="passport-strip-actions">
          <button type="button" onClick={onSave} disabled={saveDisabled}>
            Сохранить сценарий
          </button>
        </div>
      </div>
      {passport && (
        <>
          <div className="passport-strip-metrics">
            {passportMetrics(passport.physical).map((metric) => (
              <div className="metric-chip" key={metric.key}>
                <span>{metric.label}</span>
                <strong>{metric.value}</strong>
                <small>{metric.unit}</small>
              </div>
            ))}
            {status && <span className="save-status">{status}</span>}
          </div>
          <details className="passport-strip-details">
            <summary>Все показатели паспорта и источники</summary>
            <div className="table-scroll geometry-readonly">
              <table>
                <thead>
                  <tr><th>Показатель</th><th>Значение</th><th>Ед.</th><th>Источник</th></tr>
                </thead>
                <tbody>
                  {passportRows(passport.physical, passport.lineage).map((row) => (
                    <tr key={row.key}>
                      <td>{row.label}</td>
                      <td>{row.value}</td>
                      <td>{row.unit}</td>
                      <td><small>{row.source}</small></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </div>
  );
}
