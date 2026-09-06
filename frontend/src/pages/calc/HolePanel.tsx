import { useEffect, useState } from "react";
import { api } from "../../api/endpoints";
import { useWorkspace } from "../../app/useWorkspace";
import { MetricsTable } from "../../components/MetricsTable";
import type { BlastGeometryResponse } from "../../types";
import { defaultPanelInputs, maxUnderchargeM, type PanelInputs } from "./calcInputs";
import { CostPanel } from "./CostPanel";
import { HoleSchemeView } from "./HoleSchemeView";

export function HolePanel({
  panelKey,
  variantLabel,
  gridAM,
  gridBM,
  depthM,
  overdrillM,
  crownMm,
  holeOversizeCoeff,
  blockVolumeM3,
  additionalHolesPct,
  defaultExplosiveKey,
  defaultUnderchargeM,
  showChargeDesign,
  explosiveBasis,
  // Смета Cost V1 больше не показывается на вкладке «Расчёт».
  showCostPanel = false,
  isBlastContextSource = true,
  nsiLengthOptions,
  detonatorDelayOptions,
  initialInputs,
  onInputsChange,
  onGeometry,
}: {
  panelKey: string;
  variantLabel: string;
  gridAM: number;
  gridBM: number;
  depthM: number;
  overdrillM: number;
  crownMm: number;
  holeOversizeCoeff: number;
  blockVolumeM3: number;
  additionalHolesPct: number;
  defaultExplosiveKey: string;
  defaultUnderchargeM: number;
  showChargeDesign: boolean;
  explosiveBasis: "per_m3" | "per_m" | "none";
  showCostPanel?: boolean;
  isBlastContextSource?: boolean;
  nsiLengthOptions: number[];
  detonatorDelayOptions: number[];
  /** Значения полей при появлении панели: настройки листа за объектом работ.
   * Читаются один раз — чтобы панель приняла новые, её пересоздают через `key`. */
  initialInputs?: PanelInputs;
  /** Любое изменение полей наружу: лист собирает из этого свои настройки. */
  onInputsChange?: (inputs: PanelInputs) => void;
  /** Рассчитанный блок наружу: по нему сохраняется технический паспорт. */
  onGeometry?: (geometry: BlastGeometryResponse) => void;
}) {
  const { state } = useWorkspace();
  const explosiveList = state?.references.explosive_records ?? [];

  // Начальные значения панели: сохранённые настройки листа, иначе умолчания
  // варианта. Дальше поля живут своим состоянием, а наверх уходит `onInputsChange`.
  const seed = initialInputs ?? defaultPanelInputs(defaultExplosiveKey, defaultUnderchargeM);
  const [explosiveKey, setExplosiveKey] = useState(seed.explosive_key);
  const [underchargeM, setUnderchargeM] = useState(Math.min(seed.undercharge_m, maxUnderchargeM(depthM)));
  const [intermediateDetonatorsPerHole, setIntermediateDetonatorsPerHole] = useState(seed.intermediate_detonators_per_hole);
  const [nsiPerHole, setNsiPerHole] = useState(seed.nsi_per_hole);
  const [nsiLength1M, setNsiLength1M] = useState(seed.nsi_length_1_m);
  const [nsiLength2M, setNsiLength2M] = useState(seed.nsi_length_2_m);
  const [detonatorDelayMs, setDetonatorDelayMs] = useState(seed.detonator_delay_ms);
  const [geometry, setGeometry] = useState<BlastGeometryResponse | null>(null);
  const [error, setError] = useState("");

  const effectiveUnderchargeM = showChargeDesign ? underchargeM : Math.max(0, depthM - 0.5);
  const view = explosiveBasis === "per_m" ? "contour" : showChargeDesign ? "charge" : "drilling";

  const payload = {
    grid_a_m: gridAM,
    grid_b_m: gridBM,
    depth_m: depthM,
    overdrill_m: overdrillM,
    undercharge_m: effectiveUnderchargeM,
    crown_mm: crownMm,
    hole_oversize_coeff: holeOversizeCoeff,
    explosive_key: explosiveKey || defaultExplosiveKey,
    block_volume_m3: blockVolumeM3,
    additional_holes_pct: additionalHolesPct,
    intermediate_detonators_per_hole: intermediateDetonatorsPerHole,
    nsi_per_hole: nsiPerHole,
    nsi_length_1_m: nsiLength1M,
    nsi_length_2_m: nsiLength2M,
    detonator_delay_ms: detonatorDelayMs,
    view: view as "charge" | "contour" | "drilling",
  };

  // Поля панели наверх: лист складывает из них свои настройки и сохраняет их
  // за объектом работ. Первый вызов на монтировании отдаёт начальные значения —
  // так у листа и панели одна правда о том, что сейчас в полях.
  useEffect(() => {
    onInputsChange?.({
      explosive_key: explosiveKey,
      undercharge_m: underchargeM,
      intermediate_detonators_per_hole: intermediateDetonatorsPerHole,
      nsi_per_hole: nsiPerHole,
      nsi_length_1_m: nsiLength1M,
      nsi_length_2_m: nsiLength2M,
      detonator_delay_ms: detonatorDelayMs,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    explosiveKey, underchargeM, intermediateDetonatorsPerHole, nsiPerHole,
    nsiLength1M, nsiLength2M, detonatorDelayMs,
  ]);

  useEffect(() => {
    let cancelled = false;
    api.geometry(payload).then((res) => { if (!cancelled) { setGeometry(res); setError(""); onGeometry?.(res); } })
      .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Ошибка расчёта геометрии."); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    gridAM, gridBM, depthM, overdrillM, effectiveUnderchargeM, crownMm, holeOversizeCoeff,
    explosiveKey, blockVolumeM3, additionalHolesPct, intermediateDetonatorsPerHole, nsiPerHole,
    nsiLength1M, nsiLength2M, detonatorDelayMs, view,
  ]);

  return (
    <div className="hole-panel">
      <h3>{variantLabel}</h3>
      {showChargeDesign && (
        <div className="hole-panel-controls">
          <label>Тип ВВ
            <select value={explosiveKey} onChange={(e) => setExplosiveKey(e.target.value)}>
              {explosiveList.map((e) => <option key={e.id || e.key} value={e.key}>{e.name}</option>)}
            </select>
          </label>
          <label className="range-label">
            <span>Недозаряд (верх скважины), м <b>{underchargeM.toFixed(1)}</b></span>
            <input type="range" min={0} max={maxUnderchargeM(depthM)} step={0.1} value={underchargeM}
              onChange={(e) => setUnderchargeM(Number(e.target.value))} />
          </label>
          <div className="field-pair">
            <label>Пром. детонаторы, шт/скв
              <select value={intermediateDetonatorsPerHole} onChange={(e) => setIntermediateDetonatorsPerHole(Number(e.target.value))}>
                <option value={1}>1</option><option value={2}>2</option>
              </select>
            </label>
            <label>Скважинное НСИ
              <select value={nsiPerHole} onChange={(e) => setNsiPerHole(Number(e.target.value))}>
                <option value={1}>1 устройство/скв</option>
                <option value={2}>2 устройства/скв (дублирование)</option>
              </select>
            </label>
          </div>
          <div className="field-pair">
            <label>Длина НСИ-1, м
              <select value={nsiLength1M} onChange={(e) => setNsiLength1M(Number(e.target.value))}>
                {nsiLengthOptions.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </label>
            {nsiPerHole === 2 && (
              <label>Длина НСИ-2, м
                <select value={nsiLength2M} onChange={(e) => setNsiLength2M(Number(e.target.value))}>
                  {nsiLengthOptions.map((v) => <option key={v} value={v}>{v}</option>)}
                </select>
              </label>
            )}
          </div>
          <label>Замедление, мс
            <select value={detonatorDelayMs} onChange={(e) => setDetonatorDelayMs(Number(e.target.value))}>
              {detonatorDelayOptions.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </label>
        </div>
      )}

      {error && <div className="page-error">{error}</div>}

      {geometry && (
        <div className="hole-viz-row">
          {showChargeDesign && (
            <HoleSchemeView
              hole={geometry.hole}
              initiation={geometry.initiation}
              crownMm={crownMm}
              title={geometry.label}
            />
          )}
          <div className="hole-viz-tables">
            <MetricsTable title="Скважина" rows={geometry.hole_rows} />
            <MetricsTable title="Блок" rows={geometry.block_rows} />
          </div>
        </div>
      )}

      {showCostPanel && geometry && (
        <CostPanel
          panelKey={panelKey}
          variantTitle={showChargeDesign ? geometry.label : "Бурение"}
          explosiveKey={explosiveKey || defaultExplosiveKey}
          hole={geometry.hole}
          block={geometry.block}
          initiation={geometry.initiation}
          holeDepthM={depthM}
          holeOversizeCoeff={holeOversizeCoeff}
          isBlastContextSource={isBlastContextSource}
        />
      )}
    </div>
  );
}
