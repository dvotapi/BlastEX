import { ruNumber } from "../../lib/format";
import type { MovementPredictResponse } from "../../types/design";
import { RoleBadge } from "./RoleBadge";

function Metric({ label, value, unit, digits }: { label: string; value: number; unit: string; digits: number }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{ruNumber(value, digits)}</strong>
      <small>{unit}</small>
    </div>
  );
}

export function MovementPanel({
  onPredict,
  busy,
  result,
  selectedHoleId,
  showVectors,
  onToggleVectors,
}: {
  onPredict: () => void;
  busy: boolean;
  result: MovementPredictResponse | null;
  selectedHoleId: string | null;
  showVectors: boolean;
  onToggleVectors: () => void;
}) {
  const holeRow = selectedHoleId ? result?.holes.find((row) => row.hole_id === selectedHoleId) : undefined;
  const pile = result?.muckpile;

  return (
    <section className="panel">
      <header><b>Развал и вывал</b><RoleBadge role="predicted" /></header>
      <div className="panel-body">
        <small className="movement-disclaimer">
          оценка / estimate — эмпирическая кинематическая модель. Это не физическая симуляция.
          Слой только predicted: проектная сетка и заряды не перезаписываются.
        </small>
        <button className="calculate-button" onClick={onPredict} disabled={busy}>
          {busy ? "Считаем оценку…" : "Оценить развал и вывал"}
        </button>
        <label className="check-row">
          <input type="checkbox" checked={showVectors} onChange={onToggleVectors} />
          Показать векторы оценки на плане
        </label>

        {result && pile && (
          <>
            <div className="frag-caption">
              <b>{holeRow ? `Скважина ${holeRow.hole_id}` : "Блок (оценка)"}</b>
              <span>{result.model} v{result.model_version}</span>
            </div>
            <small>роль predicted · {result.kind} · паспорт не изменён</small>
            <div className="metrics-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <Metric label="Отброс" value={holeRow?.throw_m ?? pile.throw_m} unit="м" digits={2} />
              <Metric label="Вывал" value={holeRow?.heave_m ?? pile.heave_m} unit="м" digits={2} />
              <Metric label="Разрыхление" value={holeRow?.swell_factor ?? pile.swell_factor} unit="" digits={2} />
              <Metric label="Объём развала" value={pile.volume_m3} unit="м³" digits={0} />
              <Metric label="Длина" value={pile.length_m} unit="м" digits={1} />
              <Metric label="Ширина" value={pile.width_m} unit="м" digits={1} />
              <Metric label="Высота" value={pile.height_m} unit="м" digits={1} />
              <Metric label="Объём in situ" value={pile.in_situ_volume_m3} unit="м³" digits={0} />
            </div>
            {holeRow && (
              <small>
                Вектор {ruNumber(holeRow.dx_m, 2)} / {ruNumber(holeRow.dy_m, 2)} м
                {" · "}азимут {ruNumber(holeRow.direction_deg, 0)}°
                {" · "}q {ruNumber(holeRow.inputs.powder_factor_kg_m3, 3)} кг/м³
              </small>
            )}
            <small className="movement-disclaimer">{result.disclaimer}</small>
            {result.warnings[0] && <small className="frag-warnings">{result.warnings[0]}</small>}
          </>
        )}
      </div>
    </section>
  );
}
