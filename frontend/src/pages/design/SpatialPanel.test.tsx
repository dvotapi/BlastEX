// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { SpatialModel, SpatialOverlay, SpatialSummary } from "../../types/design";
import { SpatialPanel } from "./SpatialPanel";

afterEach(cleanup);

const summary = {
  model_id: "sp-1",
  team_id: "team",
  site_id: "quarry-1",
  model_version: 2,
  training_dataset_id: "snap",
  training_dataset_version: 2,
  feature_schema_version: "spatial-1.0.0",
  training_date: "",
  metrics: {},
  status: "production",
  algorithm: "random_forest",
  class_name: "SpatialHoleModel",
  hole_count: 40,
  sample_count: 40,
  baseline_model: "",
  baseline_model_version: "",
  base_label: "Старая база (Kuz-Ram (старая) 1.0.0) — физика считается старой моделью",
} as SpatialSummary;

function overlayWith(baseLabel: string): SpatialOverlay {
  return {
    holes: [],
    neighborhoods: [],
    maps: {},
    block: { x50_mm: 150, oversize_pct: 4, toe_probability: 0.1 },
    model_id: "sp-1",
    team_id: "team",
    site_id: "quarry-1",
    model_version: 2,
    training_dataset_version: 2,
    feature_schema_version: "spatial-1.0.0",
    algorithm: "random_forest",
    status: "production",
    hole_count: 6,
    applied_as: "recommendation_overlay",
    modifies_design: false,
    prediction_applied: true,
    warnings: [],
    role: "predicted",
    data_roles: {},
    physics_model: "kuzram_legacy",
    physics_model_version: "1.0.0",
    base_label: baseLabel,
  } as unknown as SpatialOverlay;
}

const noop = () => undefined;

function renderPanel(
  selected: SpatialModel | null,
  overlay: SpatialOverlay | null = null,
  models: SpatialSummary[] = [summary],
) {
  return render(
    <SpatialPanel
      siteId="quarry-1"
      datasetId="snap"
      datasetLabel="снимок v2"
      models={models}
      selected={selected}
      overlay={overlay}
      busy={false}
      onRefresh={noop}
      onTrain={noop}
      onOpen={noop}
      onMarkProduction={noop}
      onPredict={noop}
    />,
  );
}

describe("SpatialPanel — база пространственной модели", () => {
  it("в списке видна старая база", () => {
    renderPanel(null);
    expect(screen.getByText(/Старая база/)).toBeTruthy();
  });

  it("в результате прогноза видна база модели, выбранной сервером", () => {
    // Production-модель выбрана сервером (use_production): ни списка, ни карточки нет.
    renderPanel(null, overlayWith(summary.base_label), []);
    expect(screen.getByText(/Старая база/)).toBeTruthy();
  });

  it("пустая подпись базы в результате не рисуется", () => {
    // Без модели сервер отдаёт пустую подпись.
    const { container } = renderPanel(null, overlayWith(""), []);
    expect(container.querySelector(".frag-settings")).toBeNull();
  });

  it("в карточке — подпись базы", () => {
    const selected = { ...summary, base_label: "База: Kuz-Ram 2.0.0" } as unknown as SpatialModel;
    renderPanel(selected);
    expect(screen.getByText("База: Kuz-Ram 2.0.0")).toBeTruthy();
  });
});
