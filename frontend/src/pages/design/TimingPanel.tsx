import { ruNumber } from "../../lib/format";
import type { AnalyzeResponse, PpvRequest } from "../../types/design";
import { formatSpread, reliefLegend } from "./relief";
import { RoleBadge } from "./RoleBadge";

const LEVEL_LABELS: Record<string, string> = {
  hole: "скважина",
  deck: "дека",
  primer: "боевик",
};

const DIAGNOSTIC_LABELS: Record<string, string> = {
  unconnected_holes: "Нет связи",
  hole_disconnected: "Нет связи",
  duplicate_times: "Одинаковое время",
  unexpected_firing_order: "Порядок взрыва",
  high_mic: "Высокий MIC",
  insufficient_delays: "Малая задержка",
  relief_direction: "Направление выброса",
  isolated_network_branches: "Изолированная ветвь",
};

export function TimingPanel({
  analysis,
  busy,
  onAnalyze,
  isolineStepMs,
  onIsolineStepChange,
  showIsolines,
  onToggleIsolines,
  ppv,
  onPpvChange,
  playing,
  onPlayToggle,
  currentMs,
  maxMs,
  onScrub,
}: {
  analysis: AnalyzeResponse | null;
  busy: boolean;
  onAnalyze: () => void;
  isolineStepMs: number;
  onIsolineStepChange: (value: number) => void;
  showIsolines: boolean;
  onToggleIsolines: () => void;
  ppv: PpvRequest;
  onPpvChange: (patch: Partial<PpvRequest>) => void;
  playing: boolean;
  onPlayToggle: () => void;
  currentMs: number;
  maxMs: number;
  onScrub: (ms: number) => void;
}) {
  const warnings = analysis
    ? [...analysis.timing_warnings.map((m) => ({ code: "unconnected_holes", message: m })), ...analysis.validation_warnings]
    : [];
  const timingCodes = new Set(Object.keys(DIAGNOSTIC_LABELS));
  const timingWarnings = warnings.filter((item) => !item.code || timingCodes.has(item.code));
  const otherWarnings = warnings.filter((item) => item.code && !timingCodes.has(item.code));
  const events = analysis?.firing_events ?? [];
  const fired = events.filter((item) => item.time_ms <= currentMs).length;

  return (
    <section className="panel">
      <header><b>Тайминг</b><RoleBadge role="designed" /></header>
      <div className="panel-body">
        <div className="field-pair">
          <label>Шаг изолиний, мс<input type="number" min="5" step="5" value={isolineStepMs} onChange={(e) => onIsolineStepChange(Number(e.target.value))} /></label>
          <label className="checkbox-row" style={{ alignSelf: "end", paddingBottom: 10 }}>
            <input type="checkbox" checked={showIsolines} onChange={onToggleIsolines} />
            Показать изолинии
          </label>
        </div>

        <button className="calculate-button" onClick={onAnalyze} disabled={busy}>
          {busy ? "Считаем…" : "Рассчитать тайминг"}
        </button>

        {analysis && (
          <>
            <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <div><span>Макс. заряд на ступень (MIC)</span><strong>{ruNumber(analysis.mic.mic_kg, 0)}</strong><small>кг</small></div>
              <div><span>Скважин в схеме</span><strong>{Object.keys(analysis.times_ms).length}</strong><small>шт.</small></div>
            </div>

            <ReliefSummary relief={analysis.relief ?? null} />

            <div className="field-pair">
              <label>Расстояние до объекта, м<input type="number" min="1" step="1" value={ppv.distance_m} onChange={(e) => onPpvChange({ distance_m: Number(e.target.value) })} /></label>
              <label>K / n<span className="ppv-kn">
                <input type="number" step="1" value={ppv.k} onChange={(e) => onPpvChange({ k: Number(e.target.value) })} />
                <input type="number" step="0.1" value={ppv.n} onChange={(e) => onPpvChange({ n: Number(e.target.value) })} />
              </span></label>
            </div>
            {analysis.ppv_mm_s !== null && (
              <div className="metrics-grid" style={{ gridTemplateColumns: "1fr" }}>
                <div><span>Ориентировочная скорость колебаний</span><strong>{ruNumber(analysis.ppv_mm_s, 2)}</strong><small>мм/с</small></div>
              </div>
            )}
            <small>
              Быстрая оценка в конвенции Q⅓/R. Калиброванный закон площадки, рецепторы и замеры —
              в панели «Сейсмика».
            </small>

            <small>
              Направление выброса и изолинии — на плане (пресет «Тайминг»). Анимация ниже синхронизирована с картой.
            </small>

            <div className="animation-controls">
              <button className="secondary-button" onClick={onPlayToggle} disabled={maxMs <= 0}>
                {playing ? "⏸ Пауза" : "▶ Анимация взрыва"}
              </button>
              <input
                type="range"
                min="0"
                max={Math.max(1, maxMs)}
                step="1"
                value={Math.min(currentMs, maxMs)}
                onChange={(e) => onScrub(Number(e.target.value))}
              />
              <span>{ruNumber(currentMs, 0)} / {ruNumber(maxMs, 0)} мс</span>
            </div>
            <small>Сработало событий: {fired} из {events.length || Object.keys(analysis.times_ms).length}. Изолиния фронта подсвечивается на плане.</small>

            {events.length > 0 && (
              <div className="firing-table">
                {events.slice(0, 24).map((event) => (
                  <div key={event.id} className={`firing-row${event.time_ms <= currentMs ? " fired" : ""}`}>
                    <span>{event.hole_id}</span>
                    <small>{LEVEL_LABELS[event.level] ?? event.level}{event.deck_index != null ? ` ${event.deck_index + 1}` : ""}{event.primer_index != null ? ` ${event.primer_index + 1}` : ""}</small>
                    <b>{ruNumber(event.time_ms, 0)} мс</b>
                  </div>
                ))}
                {events.length > 24 && <small>Показаны первые 24 из {events.length} событий.</small>}
              </div>
            )}

            {timingWarnings.length > 0 && (
              <div className="warnings-list">
                {timingWarnings.map((w, i) => (
                  <div key={`t-${i}`} className="warning-item">
                    {w.code && DIAGNOSTIC_LABELS[w.code] ? <b>{DIAGNOSTIC_LABELS[w.code]}. </b> : null}
                    {w.message}
                  </div>
                ))}
              </div>
            )}
            {otherWarnings.length > 0 && (
              <div className="warnings-list">
                {otherWarnings.map((w, i) => <div key={`o-${i}`} className="warning-item">{w.message}</div>)}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}

/** Граница темпа: целое без дробной части («3»), иначе одна цифра («2,5»). */
function boundLabel(value: number): string {
  return Number.isInteger(value) ? ruNumber(value, 0) : ruNumber(value, 1);
}

/** Сводка темпа отбойки: медиана, доля вне коридора (главный показатель ровности),
 *  устойчивый разброс и легенда зон плана. */
function ReliefSummary({ relief }: { relief: AnalyzeResponse["relief"] }) {
  const stats = relief?.stats ?? null;
  if (!stats) {
    return <small>Темп отбойки: треугольники не построены — мало скважин или они слишком далеко друг от друга</small>;
  }
  return (
    <>
      <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
        <div><span>Темп отбойки, мс/м (медиана)</span><strong>{ruNumber(stats.median_ms_m, 1)}</strong><small>мс/м</small></div>
        <div><span>{`Быстрее ${boundLabel(stats.min_bound_ms_m)} мс/м`}</span><strong>{`${Math.round(stats.fast_share * 100)} %`}</strong><small>площади</small></div>
        {stats.max_bound_ms_m != null && (
          <div><span>{`Медленнее ${boundLabel(stats.max_bound_ms_m)} мс/м`}</span><strong>{`${Math.round(stats.slow_share * 100)} %`}</strong><small>площади</small></div>
        )}
        <div><span>Стыки фронтов</span><strong>{stats.converging_length_m > 0 ? ruNumber(stats.converging_length_m, 1) : "нет"}</strong>{stats.converging_length_m > 0 && <small>м</small>}</div>
        <div><span>Вне коридора ±25 %</span><strong>{`${Math.round(stats.outside_share * 100)} %`}</strong><small>площади</small></div>
        <div><span>Устойчивый разброс</span><strong>{formatSpread(stats.robust_spread)}</strong><small>межквартильный</small></div>
      </div>
      {stats.max_ms_m === 0 ? (
        // Темп 0 во всех треугольниках: зоны по отклонению от медианы не определены.
        <small>Все скважины срабатывают одновременно — темп 0 мс/м</small>
      ) : stats.median_ms_m === 0 ? (
        // Нулевая медиана при ненулевых треугольниках: подписи легенды вырождаются в 0;
        // ненулевые треугольники на плане красные и выделяются на фоне одновременных.
        <small>Больше половины площади срабатывает одновременно — темп 0 мс/м</small>
      ) : (
        <div className="relief-legend">
          {reliefLegend(stats.median_ms_m).map((item) => (
            <span key={item.band} className="relief-legend-item">
              <i className="legend-swatch relief-band" style={{ background: item.color }} />
              <span>{item.label}</span>
            </span>
          ))}
          <small>мс/м</small>
        </div>
      )}
    </>
  );
}
