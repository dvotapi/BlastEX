const DEFAULT_TITLE =
  "Порог негабарита не достигнут: q на верхней границе перебора. " +
  "Поднимите границу в окне «Модель Kuz-Ram» или возьмите меньшую коронку.";

/** Значок «!» у q: порог негабарита не достигнут даже на верхней границе перебора. */
export function ThresholdFlag({ title = DEFAULT_TITLE }: { title?: string }) {
  return (
    <span className="threshold-flag" role="img" aria-label="Порог негабарита не достигнут" title={title}>
      !
    </span>
  );
}
