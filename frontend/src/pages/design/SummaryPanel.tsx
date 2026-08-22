import { ruNumber } from "../../lib/format";
import type { Hole } from "../../types/design";

export function SummaryPanel({ holes, blockVolumeM3 }: { holes: Hole[]; blockVolumeM3: number | null }) {
  const production = holes.filter((h) => h.kind === "production" && h.enabled);
  const contourHoles = holes.filter((h) => h.kind === "contour" && h.enabled);
  const footage = holes.filter((h) => h.enabled).reduce((sum, h) => sum + Math.sqrt(
    (h.toe.x - h.collar.x) ** 2 + (h.toe.y - h.collar.y) ** 2 + (h.toe.z - h.collar.z) ** 2,
  ), 0);

  return (
    <div className="metrics-grid">
      <div><span>Рабочих скважин</span><strong>{production.length}</strong><small>шт.</small></div>
      <div><span>Контурных скважин</span><strong>{contourHoles.length}</strong><small>шт.</small></div>
      <div><span>Погонаж бурения</span><strong>{ruNumber(footage, 1)}</strong><small>м</small></div>
      <div><span>Объём блока</span><strong>{blockVolumeM3 !== null ? ruNumber(blockVolumeM3, 0) : "—"}</strong><small>м³</small></div>
    </div>
  );
}
