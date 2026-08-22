import { useState } from "react";
import type { HoleGeometry, InitiationConfig, ScenarioCalcProfile } from "../../types";
import { CostPanel } from "./CostPanel";

const ZERO_HOLE: HoleGeometry = {
  grid_a_m: 0, grid_b_m: 0, depth_m: 0, overdrill_m: 0, undercharge_m: 0,
  charge_length_m: 0, charge_diameter_m: 0, capacity_kg_per_m: 0, charge_mass_kg: 0,
  yield_m3: 0, specific_q_kg_m3: 0, explosive_name: "", explosive_label: "",
};
const ZERO_INITIATION: InitiationConfig = {
  intermediate_detonators_per_hole: 0, nsi_per_hole: 0, nsi_length_1_m: 0, nsi_length_2_m: 0, detonator_delay_ms: 0,
};

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

      <CostPanel
        panelKey={`manual_${profile.manual_type}`}
        variantTitle={variantTitle}
        explosiveKey="ПВВ Гранулит-РП"
        hole={ZERO_HOLE}
        block={{
          block_volume_m3: blockVolumeM3, yield_per_hole_m3: 0, hole_count: totalHoles,
          additional_holes_pct: 0, additional_holes: 0, total_holes: totalHoles,
          drilling_footage_m: drillingFootageM, total_charge_mass_kg: totalChargeMassKg,
          specific_q_kg_m3: blockVolumeM3 > 0 ? totalChargeMassKg / blockVolumeM3 : 0,
          intermediate_detonators_per_hole: 0, nsi_per_hole: 0, nsi_length_1_m: 0, nsi_length_2_m: 0,
          detonator_delay_ms: 0, total_intermediate_detonators: 0, total_downhole_nsi: 0,
          total_nsi_length_m: 0, total_boosters: 0, total_surface_nsi: 0, total_start_nsi: 0,
        }}
        initiation={ZERO_INITIATION}
        holeDepthM={0}
        blockDataOverride={{
          hole: ZERO_HOLE,
          block: {
            block_volume_m3: blockVolumeM3, yield_per_hole_m3: 0, hole_count: totalHoles,
            additional_holes_pct: 0, additional_holes: 0, total_holes: totalHoles,
            drilling_footage_m: drillingFootageM, total_charge_mass_kg: totalChargeMassKg,
            specific_q_kg_m3: blockVolumeM3 > 0 ? totalChargeMassKg / blockVolumeM3 : 0,
            intermediate_detonators_per_hole: 0, nsi_per_hole: 0, nsi_length_1_m: 0, nsi_length_2_m: 0,
            detonator_delay_ms: 0, total_intermediate_detonators: 0, total_downhole_nsi: 0,
            total_nsi_length_m: 0, total_boosters: 0, total_surface_nsi: 0, total_start_nsi: 0,
          },
          initiation: ZERO_INITIATION,
          explosiveKey: "ПВВ Гранулит-РП",
          holeDepthM: 0,
        }}
      />
    </div>
  );
}
