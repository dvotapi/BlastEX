import type { GeometryRequest } from "../../api/endpoints";
import { maxUnderchargeM, type PanelInputs } from "./calcInputs";

/** Общее для обоих вариантов заряда: выбранная сетка и блок. */
export type VariantContext = {
  gridAM: number;
  gridBM: number;
  /** Глубина скважины: высота уступа с перебуром. */
  depthM: number;
  overdrillM: number;
  crownMm: number;
  holeOversizeCoeff: number;
  blockVolumeM3: number;
  /** Доля дополнительных скважин (0.03, а не 3 %). */
  additionalHolesPct: number;
};

/**
 * Запрос схемы заряда одного варианта. Недозаряд обрезается по глубине: поле
 * варианта хранит значение, введённое при прежней высоте уступа, а скважина
 * могла стать мельче.
 */
export function geometryPayload(inputs: PanelInputs, context: VariantContext): GeometryRequest {
  return {
    grid_a_m: context.gridAM,
    grid_b_m: context.gridBM,
    depth_m: context.depthM,
    overdrill_m: context.overdrillM,
    undercharge_m: Math.min(inputs.undercharge_m, maxUnderchargeM(context.depthM)),
    crown_mm: context.crownMm,
    hole_oversize_coeff: context.holeOversizeCoeff,
    explosive_key: inputs.explosive_key,
    block_volume_m3: context.blockVolumeM3,
    additional_holes_pct: context.additionalHolesPct,
    intermediate_detonators_per_hole: inputs.intermediate_detonators_per_hole,
    nsi_per_hole: inputs.nsi_per_hole,
    nsi_length_1_m: inputs.nsi_length_1_m,
    nsi_length_2_m: inputs.nsi_length_2_m,
    detonator_delay_ms: inputs.detonator_delay_ms,
    view: "charge",
  };
}
