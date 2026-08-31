import { useState } from "react";
import type { ScenarioCalcProfile } from "../../types";

export function ManualScenarioPage({ profile }: { profile: ScenarioCalcProfile }) {
  const [pvvMassKg, setPvvMassKg] = useState(10_000);
  const [pvvHoles, setPvvHoles] = useState(100);
  const [pvvVolume, setPvvVolume] = useState(30_000);
  const [rcFootageM, setRcFootageM] = useState(1000);

  let variantTitle = "Сценарий";
  let blockVolumeM3 = 0;
  let totalHoles = 0;
  let drillingFootageM = 0;
  let totalChargeMassKg = 0;

  if (profile.manual_type === "pvv") {
    variantTitle = "Поставка ПВВ";
    blockVolumeM3 = pvvVolume;
    totalHoles = pvvHoles;
    totalChargeMassKg = pvvMassKg;
  } else if (profile.manual_type === "evv") {
    variantTitle = "Производство ЭВВ";
  } else if (profile.manual_type === "rc") {
    variantTitle = "RC-бурение";
    drillingFootageM = rcFootageM;
  }

  return (
    <div className="page-content">
      <h2>Входные данные</h2>
      {profile.manual_type === "pvv" && (
        <div className="calc-inputs-grid">
          <label>Масса ВВ, кг<input type="number" min={0} step={100} value={pvvMassKg} onChange={(e) => setPvvMassKg(Number(e.target.value))} /></label>
          <label>Число скважин<input type="number" min={0} step={1} value={pvvHoles} onChange={(e) => setPvvHoles(Number(e.target.value))} /></label>
          <label>Объём блока, м³ (для руб/м³)<input type="number" min={0} step={1000} value={pvvVolume} onChange={(e) => setPvvVolume(Number(e.target.value))} /></label>
        </div>
      )}
      {profile.manual_type === "evv" && <p className="cost-caption">Объём производства задаётся в блоке сметы ниже.</p>}
      {profile.manual_type === "rc" && (
        <label className="field-inline">Погонаж RC-бурения, п.м.
          <input type="number" min={0} step={50} value={rcFootageM} onChange={(e) => setRcFootageM(Number(e.target.value))} />
        </label>
      )}

      <section className="panel technical-summary-panel">
        <header><b>Технические драйверы</b><span>{variantTitle}</span></header>
        <div className="metrics-grid">
          <div><span>Объём блока</span><strong>{blockVolumeM3.toLocaleString("ru-RU")}</strong><small>м³</small></div>
          <div><span>Скважины</span><strong>{totalHoles.toLocaleString("ru-RU")}</strong><small>шт.</small></div>
          <div><span>Бурение</span><strong>{drillingFootageM.toLocaleString("ru-RU")}</strong><small>м</small></div>
          <div><span>ВМ</span><strong>{totalChargeMassKg.toLocaleString("ru-RU")}</strong><small>кг</small></div>
        </div>
        <p className="page-caption">Себестоимость операции рассчитывается на вкладке «Экономика».</p>
      </section>
    </div>
  );
}
