import { ruNumber } from "../../lib/format";
import type { CadContourInfo, Hole, HoleLoad, SurfaceModel } from "../../types/design";

/**
 * Подробности объёма блока из чертежа (TASK-013, PR 3) — подсказка по
 * наведению: площади, S ср × H (способ горизонтальных сечений), объём с
 * блоковой карты и расхождение.
 */
export function volumeDetails(
  cad: CadContourInfo | null | undefined,
  meanHeightM: number | null,
  volumeM3: number | null,
  roof: SurfaceModel | null | undefined,
): string | null {
  if (!cad) return null;
  const lines = [
    `S верх ${ruNumber(cad.area_top_m2, 1)} м² · S низ ${ruNumber(cad.area_bottom_m2, 1)} м² · S ср ${ruNumber(cad.area_mean_m2, 1)} м²`,
  ];
  if (cad.area_mean_m2 !== null && meanHeightM !== null) {
    lines.push(`S ср × H = ${ruNumber(cad.area_mean_m2, 1)} × ${ruNumber(meanHeightM, 2)} = ${ruNumber(cad.area_mean_m2 * meanHeightM, 0)} м³`);
  }
  const map = cad.map_volume_m3 ?? null;
  if (map !== null && map > 0 && volumeM3 !== null) {
    const diff = ((volumeM3 - map) / map) * 100;
    lines.push(`Объём с карты ${ruNumber(map, 0)} м³: расхождение ${diff > 0 ? "+" : ""}${ruNumber(diff, 1)} %`);
  }
  // Как считает `geometry.block_volume`: нижний контур — только с кровлей, описывающей откос.
  if (!roof || !roof.tin?.triangles?.length) {
    lines.push("Объём — в контуре паспорта: кровли нет");
  } else if (cad.edited || (cad.bottom?.length ?? 0) < 3) {
    lines.push("Объём — в контуре паспорта (контур правили после построения)");
  } else if (roof.cad?.plane) {
    lines.push("Объём — S ср × H: кровля — плоскость, откос не описан");
  } else {
    lines.push("Объём — в контуре по нижней бровке");
  }
  return lines.join("\n");
}

export function SummaryPanel({
  holes,
  blockVolumeM3,
  loads,
  holesSource,
  volumeSource,
  volumeTitle,
}: {
  holes: Hole[];
  blockVolumeM3: number | null;
  loads?: HoleLoad[];
  holesSource: string;
  volumeSource: string;
  /** Подробности объёма по наведению. */
  volumeTitle?: string | null;
}) {
  const production = holes.filter((h) => h.kind === "production" && h.enabled);
  const contourHoles = holes.filter((h) => (h.kind === "contour" || h.kind === "presplit" || h.kind === "trim") && h.enabled);
  const extraHoles = holes.filter((h) => ["buffer", "stab", "satellite", "infill"].includes(h.kind) && h.enabled);
  const footage = holes.filter((h) => h.enabled).reduce((sum, h) => sum + Math.sqrt(
    (h.toe.x - h.collar.x) ** 2 + (h.toe.y - h.collar.y) ** 2 + (h.toe.z - h.collar.z) ** 2,
  ), 0);

  const totalChargeKg = loads?.reduce((sum, ld) => sum + ld.total_charge_kg, 0) ?? 0;
  const chargedHoles = loads?.filter((ld) => ld.total_charge_kg > 0) ?? [];
  const avgQ = chargedHoles.length
    ? chargedHoles.reduce((sum, ld) => sum + ld.specific_q_kg_m3, 0) / chargedHoles.length
    : null;

  return (
    <div className="metrics-strip">
      <div><span>Рабочих скважин</span><strong>{production.length}</strong><small>{holesSource}</small></div>
      <div><span>Контурные скважины</span><strong>{contourHoles.length}</strong><small>шт.</small></div>
      {extraHoles.length > 0 && <div><span>Буфер / добор</span><strong>{extraHoles.length}</strong><small>шт.</small></div>}
      <div><span>Погонаж бурения</span><strong>{ruNumber(footage, 1)} м</strong><small>{holesSource}</small></div>
      <div title={volumeTitle ?? undefined}>
        <span>Объём блока</span>
        <strong>{blockVolumeM3 !== null ? `${ruNumber(blockVolumeM3, 0)} м³` : "—"}</strong>
        <small>{volumeSource}</small>
      </div>
      {loads !== undefined && (
        <>
          <div><span>Масса ВВ</span><strong>{ruNumber(totalChargeKg, 0)} кг</strong><small>проектное</small></div>
          <div><span>Средний q</span><strong>{avgQ !== null ? ruNumber(avgQ, 3) : "—"}</strong><small>кг/м³</small></div>
        </>
      )}
    </div>
  );
}
