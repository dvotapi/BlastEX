// @vitest-environment jsdom
// Панель «Тайминг»: сводка темпа отбойки (мс/м) после расчёта — медиана,
// разброс, доля вне коридора и легенда зон.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { AnalyzeResponse } from "../../types/design";
import { TimingPanel } from "./TimingPanel";

afterEach(cleanup);

const noop = () => {};

const props = {
  analysis: null,
  busy: false,
  onAnalyze: noop,
  isolineStepMs: 25,
  onIsolineStepChange: noop,
  showIsolines: true,
  onToggleIsolines: noop,
  ppv: { distance_m: 500, k: 1140, n: 1.6 },
  onPpvChange: noop,
  playing: false,
  onPlayToggle: noop,
  currentMs: 0,
  maxMs: 0,
  onScrub: noop,
} as unknown as Parameters<typeof TimingPanel>[0];

const analysis: AnalyzeResponse = {
  times_ms: { "1": 0, "2": 42, "3": 84 },
  timing_warnings: [],
  validation_warnings: [],
  summary: {} as AnalyzeResponse["summary"],
  mic: { mic_kg: 120, window_start_ms: 0, hole_ids: ["1"] },
  isolines: [],
  ppv_mm_s: null,
};

describe("TimingPanel relief summary", () => {
  it("shows relief median, spread and legend after analysis", () => {
    render(<TimingPanel {...props} analysis={{ ...analysis, relief: { triangles: [], stats: { triangles: 12, median_ms_m: 15.33, mean_ms_m: 15.4, min_ms_m: 14, max_ms_m: 17, cv: 0.0712, outside_share: 0.05 } } }} />);
    expect(screen.getByText("Темп отбойки, мс/м (медиана)")).toBeInTheDocument();
    expect(screen.getByText("15,3")).toBeInTheDocument();
    expect(screen.getByText("Разброс темпа")).toBeInTheDocument();
    expect(screen.getByText("7 %")).toBeInTheDocument();
    expect(screen.getByText("Вне коридора ±25 %")).toBeInTheDocument();
    expect(screen.getByText("5 %")).toBeInTheDocument();
    expect(screen.getByText("13,8–16,9")).toBeInTheDocument();
  });

  it("explains missing relief", () => {
    render(<TimingPanel {...props} analysis={{ ...analysis, relief: null }} />);
    expect(screen.getByText(/нет треугольников/)).toBeInTheDocument();
  });

  it("says all holes fire together instead of the legend when median is zero", () => {
    render(<TimingPanel {...props} analysis={{ ...analysis, relief: { triangles: [], stats: { triangles: 4, median_ms_m: 0, mean_ms_m: 0, min_ms_m: 0, max_ms_m: 0, cv: null, outside_share: 0 } } }} />);
    expect(screen.getByText("Все скважины срабатывают одновременно — темп 0 мс/м")).toBeInTheDocument();
    expect(screen.queryByText(/^до /)).not.toBeInTheDocument();
    expect(screen.queryByText(/^больше /)).not.toBeInTheDocument();
  });
});
