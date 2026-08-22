import { ruNumber } from "../../lib/format";
import type { AnalyzeResponse, PpvRequest } from "../../types/design";

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
  const warnings = analysis ? [...analysis.timing_warnings.map((m) => ({ message: m })), ...analysis.validation_warnings] : [];

  return (
    <section className="panel">
      <header><b>Тайминг</b><span>05</span></header>
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
            <small>Коэффициенты K и n сильно зависят от массива — значения ориентировочные, не норматив.</small>

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
              <span>{ruNumber(currentMs, 0)} мс</span>
            </div>

            {warnings.length > 0 && (
              <div className="warnings-list">
                {warnings.map((w, i) => <div key={i} className="warning-item">{w.message}</div>)}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
