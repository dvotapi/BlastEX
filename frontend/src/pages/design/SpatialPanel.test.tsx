// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { SpatialModel, SpatialSummary } from "../../types/design";
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
  base_label: "Старая база (Kuz-Ram (старая) 1.0.0) — только для старых моделей",
} as SpatialSummary;

const noop = () => undefined;

function renderPanel(selected: SpatialModel | null) {
  render(
    <SpatialPanel
      siteId="quarry-1"
      datasetId="snap"
      datasetLabel="снимок v2"
      models={[summary]}
      selected={selected}
      overlay={null}
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

  it("в карточке — подпись базы", () => {
    const selected = { ...summary, base_label: "База: Kuz-Ram 2.0.0" } as unknown as SpatialModel;
    renderPanel(selected);
    expect(screen.getByText("База: Kuz-Ram 2.0.0")).toBeTruthy();
  });
});
