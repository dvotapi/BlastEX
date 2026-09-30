// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { FragmentationPredictResponse, FragmentationRegion } from "../../types/design";
import { FragmentationPanel } from "./FragmentationPanel";
import { settingsSourceLabel } from "./fragmentationSettings";

afterEach(cleanup);

function region(): FragmentationRegion {
  return {
    id: "site",
    kind: "site",
    hole_ids: [],
    x: 0,
    y: 0,
    hole_kind: "site",
    inputs: {
      burden_m: 4,
      spacing_m: 5,
      bench_height_m: 10,
      diameter_mm: 152,
      charge_mass_kg: 131,
      powder_factor_kg_m3: 0.656,
      stemming_m: 3,
      explosive_name: "АНФО",
      explosive_density_t_m3: 0.82,
      explosive_energy_mj_kg: 3.8,
      rock_name: "Гранит",
      rock_density_t_m3: 2.65,
      rock_ucs_mpa: 150,
      rock_fissuring: 2,
      lump_size_mm: 400,
      hole_oversize_coeff: 1.05,
      influence_volume_m3: 200,
      charge_length_m: 8,
      hole_length_m: 11,
    },
    prediction: {
      role: "predicted",
      x20_mm: 60,
      x50_mm: 200,
      x80_mm: 420,
      oversize_pct: 15.9,
      powder_factor_kg_m3: 0.656,
      curve: [
        { size_mm: 100, passing_pct: 20 },
        { size_mm: 400, passing_pct: 84 },
      ],
      provenance: { model: "kuzram", model_version: "2.0.0", inputs: {}, parameters: {}, calibration: {} },
      warnings: [],
    },
    warnings: [],
  };
}

function result(overrides: Partial<FragmentationPredictResponse> = {}): FragmentationPredictResponse {
  return {
    model: "kuzram",
    model_version: "2.0.0",
    target: { role: "designed", lump_size_mm: 400, max_oversize_pct: 5 },
    site: region(),
    holes: [],
    regions: [],
    maps: { metrics: [], holes: [], stats: {} },
    warnings: [],
    measured: [],
    calibration: {},
    settings: { source: "work_object", work_object_name: "Карьер-1", values: {}, warnings: [] },
    ...overrides,
  };
}

const noop = () => undefined;

function renderPanel(value: FragmentationPredictResponse | null) {
  render(
    <FragmentationPanel
      model="kuzram"
      onModelChange={noop}
      lumpSizeMm={400}
      onLumpSizeChange={noop}
      onPredict={noop}
      busy={false}
      result={value}
      selectedHoleId={null}
    />,
  );
}

describe("FragmentationPanel", () => {
  it("шесть моделей в списке, старые подписаны", () => {
    renderPanel(null);
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Кузнецов",
      "Kuz-Ram",
      "Swebrec",
      "Кузнецов (старая)",
      "Kuz-Ram (старая)",
      "Swebrec (старая)",
    ]);
  });

  it("строка источника настроек рядом с моделью", () => {
    renderPanel(result());
    expect(screen.getByText("Настройки модели: объект работ «Карьер-1»")).toBeTruthy();
  });
});

describe("settingsSourceLabel", () => {
  it.each([
    [result(), "Настройки модели: объект работ «Карьер-1»"],
    [
      result({ settings: { source: "request", work_object_name: "", values: {}, warnings: [] } }),
      "Настройки модели: заданы в запросе",
    ],
    [
      result({ settings: { source: "defaults", work_object_name: "", values: {}, warnings: [] } }),
      "Настройки модели: умолчания",
    ],
    [
      result({ settings: { source: "defaults", work_object_name: "Карьер-2", values: {}, warnings: [] } }),
      "Настройки модели: умолчания — у объекта «Карьер-2» они не сохранены",
    ],
    [
      result({ settings: { source: "defaults", work_object_name: "Карьер-3", values: {}, warnings: ["x"] } }),
      "Настройки модели: умолчания — настройки объекта «Карьер-3» не прочитаны",
    ],
    [result({ model: "kuzram_legacy", model_version: "1.0.0" }), "Старая модель: настройки объекта не применяются"],
  ])("вариант %#", (value, label) => {
    expect(settingsSourceLabel(value)).toBe(label);
  });
});
