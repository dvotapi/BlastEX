import { describe, expect, it } from "vitest";
import type { FragmentationPredictResponse } from "../../types/design";
import { calibrationBaseline } from "./calibrationBaseline";

const fragmentation = {
  model: "kuzram",
  model_version: "2.0.0",
  site: { prediction: { x50_mm: 210, oversize_pct: 7.5 } },
} as unknown as FragmentationPredictResponse;

describe("calibrationBaseline", () => {
  it("x50 несёт модель и версию прогноза", () => {
    expect(calibrationBaseline("kuzram_residual", fragmentation, null)).toEqual({
      baseline: 210,
      baseline_model: "kuzram",
      baseline_model_version: "2.0.0",
    });
  });

  it("негабарит — тоже с моделью", () => {
    expect(calibrationBaseline("oversize_residual", fragmentation, null)).toEqual({
      baseline: 7.5,
      baseline_model: "kuzram",
      baseline_model_version: "2.0.0",
    });
  });

  it("без прогноза кусковатости baseline пустой", () => {
    expect(calibrationBaseline("kuzram_residual", null, null)).toEqual({ baseline: null });
  });

  it("ответ есть, а прогноза площадки в нём нет — baseline пустой, без модели", () => {
    const withoutPrediction = {
      model: "kuzram",
      model_version: "2.0.0",
      site: {},
    } as unknown as FragmentationPredictResponse;

    expect(calibrationBaseline("kuzram_residual", withoutPrediction, null)).toEqual({ baseline: null });
  });

  it("PPV — максимум по приёмникам, без модели", () => {
    const vibration = { predictions: [{ ppv_mm_s: 3 }, { ppv_mm_s: null }, { ppv_mm_s: 5 }] };
    expect(calibrationBaseline("ppv_residual", fragmentation, vibration)).toEqual({ baseline: 5 });
  });
});
