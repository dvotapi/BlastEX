import { ORIGIN_LABELS } from "../origin";
import type { ValueOrigin } from "../../../types/blockEconomics";

/**
 * Бейдж происхождения величины. `label` переопределяет текст: «Расчёт
 * бурения»; `title` переопределяет подсказку — например, конкретным условием
 * бурения (`natural.lineage[...]`), а не общим объяснением кода `CALC`.
 */
export function OriginBadge({
  origin,
  label,
  title,
}: {
  origin: ValueOrigin;
  label?: string;
  title?: string;
}) {
  if (!origin) return null;
  const meta = ORIGIN_LABELS[origin];
  return (
    <span className={`origin-badge origin-${origin.toLowerCase()}`} title={title ?? meta.title}>
      {label ?? meta.label}
    </span>
  );
}
