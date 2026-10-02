// Шаг «Итог» окна «Импорт чертежа» (TASK-013, PR 3): площади обоих контуров,
// средняя высота уступа, объём между кровлей и подошвой, S ср × H (способ
// горизонтальных сечений) и сверка с блоковой картой. Высота уступа вне
// 2–25 м строится только после подтверждения.
import { ruNumber } from "../../../lib/format";
import type { CadContourResult, CadSurfaceResult } from "../../../types/cad";
import { parseNumber } from "./contourState";
import { percentDiff, type SurfaceState } from "./surfaceState";

export type SummaryStepProps = {
  contour: CadContourResult | null;
  surface: CadSurfaceResult | null;
  state: SurfaceState;
  onChange: (next: SurfaceState) => void;
  /** S с карты шага «Контур». */
  mapArea: number | null;
  disabled: boolean;
};

function withDiff(text: string, value: number | null | undefined, reference: number | null): string {
  if (text === "—") return text;
  const diff = percentDiff(value, reference);
  return diff === null ? text : `${text} (${diff > 0 ? "+" : ""}${ruNumber(diff, 2)} %)`;
}

function area(value: number | null | undefined, map: number | null): string {
  return withDiff(value == null ? "—" : `${ruNumber(value, 1)} м²`, value, map);
}

function volume(value: number | null | undefined, map: number | null): string {
  return withDiff(value == null ? "—" : `${ruNumber(value, 0)} м³`, value, map);
}

export function SummaryStep({ contour, surface, state, onChange, mapArea, disabled }: SummaryStepProps) {
  const mapVolume = parseNumber(state.mapVolume);
  const height = surface?.bench.mean_height_m ?? null;
  const basis = surface?.volume.basis === "bottom" ? "в контуре по нижней бровке" : "в контуре по верхней бровке";
  return (
    <div className="cad-summary">
      <dl className="cad-areas" role="group" aria-label="Итоги блока">
        <dt>S верх</dt>
        <dd>{area(contour?.top?.area_m2, mapArea)}</dd>
        <dt>S низ</dt>
        <dd>{area(contour?.bottom?.area_m2, mapArea)}</dd>
        <dt>S ср</dt>
        <dd>{area(contour?.mean_area_m2, mapArea)}</dd>
        <dt>Средняя высота</dt>
        <dd>{height === null ? "—" : `${ruNumber(height, 2)} м`}</dd>
        <dt>Объём по поверхностям</dt>
        <dd>{volume(surface?.volume.volume_m3, mapVolume)}</dd>
        <dt>S ср × H</dt>
        <dd>{volume(surface?.volume.mean_area_volume_m3, mapVolume)}</dd>
        <dt>
          <label htmlFor="cad-map-volume">Объём с карты, м³</label>
        </dt>
        <dd>
          <input
            id="cad-map-volume"
            inputMode="decimal"
            placeholder="с блоковой карты"
            value={state.mapVolume}
            disabled={disabled}
            onChange={(event) => onChange({ ...state, mapVolume: event.target.value })}
          />
        </dd>
      </dl>
      <p className="cad-hint">
        Объём по поверхностям — между кровлей и подошвой {basis}; S ср × H — способ горизонтальных сечений по средней
        площади.
      </p>
      {surface?.bench.needs_confirmation && height !== null && (
        <label className="cad-confirm-height">
          <input
            type="checkbox"
            checked={state.confirmHeight}
            disabled={disabled}
            onChange={(event) => onChange({ ...state, confirmHeight: event.target.checked })}
          />
          Подтверждаю высоту уступа {ruNumber(height, 1)} м
        </label>
      )}
      <p className="cad-hint">
        «Построить блок» ставит контур, свободную поверхность, отметки уступа и кровлю из чертежа; поверхность подошвы
        снимается — подошва становится проектной отметкой. Скважины пересчитываются по кровле и подошве.
      </p>
    </div>
  );
}
