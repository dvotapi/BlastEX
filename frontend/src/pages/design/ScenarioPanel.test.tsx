// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ScenarioCompareResponse } from "../../types/design";
import { ScenarioPanel } from "./ScenarioPanel";

afterEach(cleanup);

const noop = () => undefined;

function compare(warnings: string[]): ScenarioCompareResponse {
  return {
    metrics: [],
    scenarios: [{ scenario_id: "a", name: "Старый", kind: "overlay", design_id: "d" }],
    rows: [],
    cells: {},
    applied_as: "scenario_overlay",
    modifies_design: false,
    is_optimiser: false,
    approved_unchanged: true,
    warnings,
  };
}

function renderPanel(value: ScenarioCompareResponse) {
  render(
    <ScenarioPanel
      name="A"
      onNameChange={noop}
      diameterMm={165}
      onDiameterChange={noop}
      spacingM={6}
      onSpacingChange={noop}
      burdenM={5}
      onBurdenChange={noop}
      powderFactor={0.6}
      onPowderFactorChange={noop}
      useOverlays={false}
      onUseOverlaysChange={noop}
      items={[]}
      compare={value}
      busy={false}
      onCreate={noop}
      onCompare={noop}
    />,
  );
}

describe("ScenarioPanel", () => {
  it("предупреждения сравнения показаны текстом", () => {
    const warning =
      "Сценарий «Старый» посчитан до перевода модели кусковатости (Kuz-Ram 1.0.0) — пересоздайте его для сравнения.";
    renderPanel(compare([warning]));
    expect(screen.getByText(warning)).toBeTruthy();
  });

  it("без предупреждений строки нет", () => {
    renderPanel(compare([]));
    expect(screen.queryByText(/пересоздайте/)).toBeNull();
  });
});
