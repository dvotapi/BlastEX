import type { CalibrationModelType, FragmentationPredictResponse } from "../../types/design";

type VibrationLike = { predictions?: { ppv_mm_s: number | null }[] } | null | undefined;

export type CalibrationBaseline = {
  baseline: number | null;
  baseline_model?: string;
  baseline_model_version?: string;
};

/**
 * Baseline для калибровки. Для кусковатости — вместе с моделью и версией
 * прогноза: сервер накладывает поправку, только если она обучена на той же базе.
 */
export function calibrationBaseline(
  type: CalibrationModelType | string,
  fragmentation: FragmentationPredictResponse | null | undefined,
  vibration: VibrationLike,
): CalibrationBaseline {
  if (type === "ppv_residual") {
    const values = (vibration?.predictions ?? [])
      .map((item) => item.ppv_mm_s)
      .filter((value): value is number => value != null);
    return { baseline: values.length ? Math.max(...values) : null };
  }
  const prediction = fragmentation?.site.prediction;
  if (!fragmentation || !prediction) return { baseline: null };
  return {
    baseline: type === "oversize_residual" ? prediction.oversize_pct : prediction.x50_mm,
    baseline_model: fragmentation.model,
    baseline_model_version: fragmentation.model_version,
  };
}
