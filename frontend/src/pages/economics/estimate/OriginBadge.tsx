import { ORIGIN_LABELS } from "../origin";
import type { ValueOrigin } from "../../../types/blockEconomics";

/** Бейдж происхождения величины. `label` переопределяет текст: «Расчёт бурения». */
export function OriginBadge({ origin, label }: { origin: ValueOrigin; label?: string }) {
  if (!origin) return null;
  const meta = ORIGIN_LABELS[origin];
  return (
    <span className={`origin-badge origin-${origin.toLowerCase()}`} title={meta.title}>
      {label ?? meta.label}
    </span>
  );
}
