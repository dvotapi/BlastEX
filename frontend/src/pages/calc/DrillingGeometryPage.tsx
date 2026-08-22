import { useEffect, useState } from "react";
import { api } from "../../api/endpoints";
import { HolePanel } from "./HolePanel";

const DEFAULT_EXPLOSIVE_KEY = "ПВВ Гранулит-РП";

export function DrillingGeometryPage() {
  const [gridA, setGridA] = useState(5.0);
  const [gridB, setGridB] = useState(4.0);
  const [benchHeight, setBenchHeight] = useState(10.0);
  const [overdrill, setOverdrill] = useState(1.0);
  const [crownMm, setCrownMm] = useState(152);
  const [oversizeCoeff, setOversizeCoeff] = useState(1.05);
  const [blockVolume, setBlockVolume] = useState(30_000);
  const [additionalHolesPct, setAdditionalHolesPct] = useState(3.0);
  const [crowns, setCrowns] = useState<number[]>([]);
  const [nsiLengthOptions, setNsiLengthOptions] = useState<number[]>([12]);
  const [detonatorDelayOptions, setDetonatorDelayOptions] = useState<number[]>([500]);

  useEffect(() => {
    api.blastOptions().then((opts) => {
      setCrowns(opts.crown_diameters_mm);
      setNsiLengthOptions(opts.nsi_length_options_m);
      setDetonatorDelayOptions(opts.detonator_delay_ms_options);
      if (opts.crown_diameters_mm.includes(152)) setCrownMm(152);
    }).catch(() => undefined);
  }, []);

  return (
    <div className="page-content">
      <h2>Параметры сетки бурения</h2>
      <div className="calc-inputs-grid">
        <label>Шаг a, м<input type="number" min={1} max={20} step={0.25} value={gridA} onChange={(e) => setGridA(Number(e.target.value))} /></label>
        <label>Шаг b, м<input type="number" min={1} max={20} step={0.25} value={gridB} onChange={(e) => setGridB(Number(e.target.value))} /></label>
        <label>Высота уступа, м<input type="number" min={5} max={25} step={0.5} value={benchHeight} onChange={(e) => setBenchHeight(Number(e.target.value))} /></label>
        <label>Перебур, м<input type="number" min={0} max={3} step={0.1} value={overdrill} onChange={(e) => setOverdrill(Number(e.target.value))} /></label>
        <label>Коронка, мм
          <select value={crownMm} onChange={(e) => setCrownMm(Number(e.target.value))}>
            {crowns.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <label>Коэфф. разбуривания<input type="number" min={1} max={1.15} step={0.01} value={oversizeCoeff} onChange={(e) => setOversizeCoeff(Number(e.target.value))} /></label>
        <label>Объём блока, м³<input type="number" min={1000} step={1000} value={blockVolume} onChange={(e) => setBlockVolume(Number(e.target.value))} /></label>
        <label>Доп. скважины, %<input type="number" min={0} max={20} step={0.5} value={additionalHolesPct} onChange={(e) => setAdditionalHolesPct(Number(e.target.value))} /></label>
      </div>
      <HolePanel
        panelKey="drilling"
        variantLabel="Геометрия и погонаж"
        gridAM={gridA}
        gridBM={gridB}
        depthM={benchHeight + overdrill}
        overdrillM={overdrill}
        crownMm={crownMm}
        holeOversizeCoeff={oversizeCoeff}
        blockVolumeM3={blockVolume}
        additionalHolesPct={additionalHolesPct / 100}
        defaultExplosiveKey={DEFAULT_EXPLOSIVE_KEY}
        defaultUnderchargeM={0}
        showChargeDesign={false}
        explosiveBasis="none"
        nsiLengthOptions={nsiLengthOptions}
        detonatorDelayOptions={detonatorDelayOptions}
      />
    </div>
  );
}
