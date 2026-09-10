import { useMemo, type Ref } from "react";
import { passportCreatedAtLabel, passportMetrics, passportRows } from "./passportSummary";
import type { TechnicalPassport } from "../../types/blockEconomics";

/**
 * Компактная полоса паспорта под шапкой сценариев: объект, технический
 * паспорт и ревизия справочников — одной строкой; ниже — плашки геометрии и
 * дата паспорта, а остальные величины с источниками — под раскрывашкой.
 * Имя сценария и «Сохранить» переехали в `EconomicsHeader` — полоса больше
 * не знает о сценарии, только о паспорте.
 * Полоса закреплена при прокрутке (`.passport-strip` в styles.css), поэтому
 * страница меряет её высоту через `ref` и на неё отступает липкую колонку
 * параметров.
 */
export function PassportStrip({
  ref,
  passports,
  selectedId,
  onSelect,
  passport,
  siteLabel,
  revisionLabel,
}: {
  /** React 19: ref — обычный проп функционального компонента, forwardRef не нужен. */
  ref?: Ref<HTMLElement>;
  passports: TechnicalPassport[];
  selectedId: string;
  onSelect: (id: string) => void;
  /** Паспорт, по которому считается модель; null — ещё не загружен. */
  passport: TechnicalPassport | null;
  siteLabel: string;
  revisionLabel: string;
}) {
  const metrics = useMemo(() => (passport ? passportMetrics(passport.physical) : []), [passport]);
  const rows = useMemo(
    () => (passport ? passportRows(passport.physical, passport.lineage) : []),
    [passport],
  );
  const createdAtLabel = passport ? passportCreatedAtLabel(passport.created_at) : "";

  return (
    <section className="passport-strip" aria-label="Паспорт блока" ref={ref}>
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
          Ревизия справочников паспорта
          <input value={revisionLabel} title={passport?.reference_revision_id ?? ""} disabled />
        </label>
      </div>
      {passport && (
        <>
          <div className="passport-strip-metrics">
            {metrics.map((metric) => (
              <div className="metric-chip" key={metric.key}>
                <span>{metric.label}</span>
                <strong>{metric.value}</strong>
                <small>{metric.unit}</small>
              </div>
            ))}
            {createdAtLabel && <span className="passport-strip-date">{createdAtLabel}</span>}
          </div>
          <details className="passport-strip-details">
            <summary>Все показатели паспорта и источники</summary>
            <div className="table-scroll geometry-readonly">
              <table>
                <thead>
                  <tr><th>Показатель</th><th>Значение</th><th>Ед.</th><th>Источник</th></tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
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
    </section>
  );
}
