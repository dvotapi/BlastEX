// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { CalibrationModel, CalibrationSummary } from "../../types/design";
import { CalibrationPanel } from "./CalibrationPanel";

afterEach(cleanup);

const summary = {
  model_id: "cal-1",
  site_id: "quarry-1",
  model_type: "kuzram_residual",
  model_version: 3,
  training_dataset_id: "snap",
  training_dataset_version: 2,
  feature_schema_version: "1",
  training_date: "",
  metrics: {},
  status: "production",
  algorithm: "random_forest",
  sample_count: 8,
  baseline_model: "",
  baseline_model_version: "",
  base_label: "Старая база (Kuz-Ram (старая) 1.0.0) — только для старых моделей",
} as CalibrationSummary;

const noop = () => undefined;

function renderPanel(selected: CalibrationModel | null) {
  render(
    <CalibrationPanel
      siteId="quarry-1"
      datasetId="snap"
      datasetLabel="снимок v2"
      modelType="kuzram_residual"
      onModelTypeChange={noop}
      algorithm="random_forest"
      onAlgorithmChange={noop}
      algorithms={[]}
      models={[summary]}
      selected={selected}
      overlay={null}
      busy={false}
      onRefresh={noop}
      onTrain={noop}
      onOpen={noop}
      onMarkProduction={noop}
      onApplyOverlay={noop}
    />,
  );
}

describe("CalibrationPanel — база калибровки", () => {
  it("в списке видна старая база", () => {
    renderPanel(null);
    expect(screen.getByText(/Старая база/)).toBeTruthy();
  });

  it("в карточке — подпись базы", () => {
    const selected = { ...summary, base_label: "База: Kuz-Ram 2.0.0" } as unknown as CalibrationModel;
    renderPanel(selected);
    expect(screen.getByText("База: Kuz-Ram 2.0.0")).toBeTruthy();
  });
});
