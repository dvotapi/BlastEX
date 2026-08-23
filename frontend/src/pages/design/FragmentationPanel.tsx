import { ruNumber } from "../../lib/format";
import {
  FRAGMENTATION_MODELS,
  type FragmentationModelId,
  type FragmentationPredictResponse,
  type FragmentationRegion,
} from "../../types/design";

function curvePath(region: FragmentationRegion): string {
  const curve = region.prediction.curve.filter((point) => point.size_mm > 0);
  if (curve.length < 2) return "";
  const minX = Math.log10(curve[0].size_mm);
  const maxX = Math.log10(curve[curve.length - 1].size_mm);
  const span = Math.max(1e-6, maxX - minX);
  return curve
    .map((point, index) => {
      const x = ((Math.log10(point.size_mm) - minX) / span) * 220;
      const y = 88 - (point.passing_pct / 100) * 80;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
}

function Metric({ label, value, unit, digits }: { label: string; value: number; unit: string; digits: number }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{ruNumber(value, digits)}</strong>
      <small>{unit}</small>
    </div>
  );
}

export function FragmentationPanel({
  model,
  onModelChange,
  lumpSizeMm,
  onLumpSizeChange,
  onPredict,
  busy,
  result,
  selectedHoleId,
}: {
  model: FragmentationModelId;
  onModelChange: (value: FragmentationModelId) => void;
  lumpSizeMm: number;
  onLumpSizeChange: (value: number) => void;
  onPredict: () => void;
  busy: boolean;
  result: FragmentationPredictResponse | null;
  selectedHoleId: string | null;
}) {
  const holeRow = selectedHoleId ? result?.holes.find((row) => row.hole_ids.includes(selectedHoleId)) : undefined;
  const view = holeRow ?? result?.site ?? null;
  const viewLabel = holeRow ? `Скважина ${holeRow.hole_ids[0]}` : "Блок";

  return (
    <section className="panel">
      <header><b>Дробление</b><span>08</span></header>
      <div className="panel-body">
        <label>Модель
          <select value={model} onChange={(e) => onModelChange(e.target.value as FragmentationModelId)}>
            {FRAGMENTATION_MODELS.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
        </label>
        <label>Кондиционный кусок, мм
          <input
            type="number"
            min="1"
            step="10"
            value={lumpSizeMm}
            onChange={(e) => onLumpSizeChange(Number(e.target.value))}
          />
        </label>
        <button className="calculate-button" onClick={onPredict} disabled={busy}>
          {busy ? "Считаем прогноз…" : "Рассчитать дробление"}
        </button>
        <small>Прогноз по проекту (роль predicted). Измеренная кусковатость сюда не записывается.</small>

        {result && view && (
          <>
            <div className="frag-caption">
              <b>{viewLabel}</b>
              <span>{result.model} v{result.model_version}</span>
            </div>
            <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <Metric label="X20" value={view.prediction.x20_mm} unit="мм" digits={0} />
              <Metric label="X50" value={view.prediction.x50_mm} unit="мм" digits={0} />
              <Metric label="X80" value={view.prediction.x80_mm} unit="мм" digits={0} />
              <Metric label="Негабарит" value={view.prediction.oversize_pct} unit="%" digits={1} />
              <Metric label="Уд. расход" value={view.prediction.powder_factor_kg_m3} unit="кг/м³" digits={3} />
              <Metric label="Масса заряда" value={view.inputs.charge_mass_kg} unit="кг" digits={0} />
            </div>
            <svg className="frag-curve" viewBox="0 0 220 100" role="img" aria-label="Кривая прохождения">
              <line x1="0" y1="88" x2="220" y2="88" />
              <line x1="0" y1="8" x2="0" y2="88" />
              <path d={curvePath(view)} />
              <text x="4" y="12">100%</text>
              <text x="168" y="98">размер, мм</text>
            </svg>
            {result.warnings.length > 0 && (
              <small className="frag-warnings">{result.warnings.slice(0, 3).join(" ")}</small>
            )}
          </>
        )}
      </div>
    </section>
  );
}
