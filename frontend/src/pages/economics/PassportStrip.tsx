import { useMemo, useState } from "react";
import { passportCreatedAtLabel, passportMetrics, passportRows } from "./passportSummary";
import type { TechnicalPassport } from "../../types/blockEconomics";

/**
 * Карточка показателей блока: объём, погонаж, скважины, расход ВВ — одной
 * строкой через разделители, справа дата паспорта и кнопка, раскрывающая
 * полную таблицу величин с источником каждой.
 *
 * Выбор объекта, паспорта и ревизии переехал в шапку приложения
 * (`TopbarSelectors`): это контекст всей страницы, а не её содержимое.
 * Карточка вместе с ними перестала быть липкой — она уходит из вида при
 * прокрутке, а к верху окна липнет шапка колонок сметы.
 */
export function PassportStrip({
  passport,
}: {
  /** Паспорт, по которому считается модель; null — ещё не загружен. */
  passport: TechnicalPassport | null;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const metrics = useMemo(() => (passport ? passportMetrics(passport.physical) : []), [passport]);
  const rows = useMemo(
    () => (passport ? passportRows(passport.physical, passport.lineage) : []),
    [passport],
  );
  const createdAtLabel = passport ? passportCreatedAtLabel(passport.created_at) : "";

  if (!passport) return null;

  return (
    <section className="passport-card" aria-label="Показатели блока">
      <div className="passport-card-metrics">
        {metrics.map((metric) => (
          <div className="passport-card-metric" key={metric.key}>
            <span>{metric.label}</span>
            <b>
              {metric.value} <small>{metric.unit}</small>
            </b>
          </div>
        ))}
        {createdAtLabel && (
          <div className="passport-card-metric passport-card-date">
            <span>Результаты по паспорту</span>
            <b>{createdAtLabel}</b>
          </div>
        )}
        <button
          type="button"
          className="passport-card-details-toggle"
          aria-label="Все показатели паспорта и источники"
          title="Все показатели паспорта и источники"
          aria-expanded={detailsOpen}
          aria-controls="passport-card-details"
          onClick={() => setDetailsOpen((open) => !open)}
        >
          ▤
        </button>
      </div>
      <div id="passport-card-details" className="passport-card-details" hidden={!detailsOpen}>
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
      </div>
    </section>
  );
}
