import { ruNumber } from "../../lib/format";
import type { Hole, HoleLoad } from "../../types/design";

export function SummaryPanel({
  holes,
  blockVolumeM3,
  loads,
  holesSource,
  volumeSource,
}: {
  holes: Hole[];
  blockVolumeM3: number | null;
  loads?: HoleLoad[];
  holesSource: string;
  volumeSource: string;
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
      <div>
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
