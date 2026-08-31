import { useEffect, useState } from "react";
import { api } from "../../api/endpoints";
import { useWorkspace } from "../../app/useWorkspace";
import { MetricsTable } from "../../components/MetricsTable";
import type { BlastGeometryResponse } from "../../types";
import { CostPanel } from "./CostPanel";
import { HoleSchemeView } from "./HoleSchemeView";

const NSI_LENGTH_DEFAULT_1 = 12.0;
const NSI_LENGTH_DEFAULT_2 = 6.0;
const DETONATOR_DELAY_DEFAULT = 500;

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
}) {
  const { state } = useWorkspace();
  const explosiveList = state?.references.explosive_records ?? [];

  const [explosiveKey, setExplosiveKey] = useState(defaultExplosiveKey);
  const [underchargeM, setUnderchargeM] = useState(Math.min(defaultUnderchargeM, Math.max(0, depthM - 0.5)));
  const [intermediateDetonatorsPerHole, setIntermediateDetonatorsPerHole] = useState(1);
  const [nsiPerHole, setNsiPerHole] = useState(1);
  const [nsiLength1M, setNsiLength1M] = useState(NSI_LENGTH_DEFAULT_1);
  const [nsiLength2M, setNsiLength2M] = useState(NSI_LENGTH_DEFAULT_2);
  const [detonatorDelayMs, setDetonatorDelayMs] = useState(DETONATOR_DELAY_DEFAULT);
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

  useEffect(() => {
    let cancelled = false;
    api.geometry(payload).then((res) => { if (!cancelled) { setGeometry(res); setError(""); } })
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
              {explosiveList.map((e) => <option key={e.key} value={e.key}>{e.name}</option>)}
            </select>
          </label>
          <label className="range-label">
            <span>Недозаряд (верх скважины), м <b>{underchargeM.toFixed(1)}</b></span>
            <input type="range" min={0} max={Math.max(0, depthM - 0.5)} step={0.1} value={underchargeM}
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
