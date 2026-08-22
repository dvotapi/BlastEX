import { ruNumber } from "../../lib/format";
import type { Hole, HoleLoad } from "../../types/design";

export function SummaryPanel({
  holes,
  blockVolumeM3,
  loads,
}: {
  holes: Hole[];
  blockVolumeM3: number | null;
  loads?: HoleLoad[];
}) {
  const production = holes.filter((h) => h.kind === "production" && h.enabled);
  const contourHoles = holes.filter((h) => h.kind === "contour" && h.enabled);
  const footage = holes.filter((h) => h.enabled).reduce((sum, h) => sum + Math.sqrt(
    (h.toe.x - h.collar.x) ** 2 + (h.toe.y - h.collar.y) ** 2 + (h.toe.z - h.collar.z) ** 2,
  ), 0);

  const totalChargeKg = loads?.reduce((sum, ld) => sum + ld.total_charge_kg, 0) ?? 0;
  const chargedHoles = loads?.filter((ld) => ld.total_charge_kg > 0) ?? [];
  const avgQ = chargedHoles.length
    ? chargedHoles.reduce((sum, ld) => sum + ld.specific_q_kg_m3, 0) / chargedHoles.length
    : null;

  return (
    <div className="metrics-grid">
      <div><span>Рабочих скважин</span><strong>{production.length}</strong><small>шт.</small></div>
      <div><span>Контурных скважин</span><strong>{contourHoles.length}</strong><small>шт.</small></div>
      <div><span>Погонаж бурения</span><strong>{ruNumber(footage, 1)}</strong><small>м</small></div>
      <div><span>Объём блока</span><strong>{blockVolumeM3 !== null ? ruNumber(blockVolumeM3, 0) : "—"}</strong><small>м³</small></div>
      {loads !== undefined && (
        <>
          <div><span>Масса ВВ на блок</span><strong>{ruNumber(totalChargeKg, 0)}</strong><small>кг</small></div>
          <div><span>Средний уд. расход</span><strong>{avgQ !== null ? ruNumber(avgQ, 3) : "—"}</strong><small>кг/м³</small></div>
        </>
      )}
    </div>
  );
}
