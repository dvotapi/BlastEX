// @vitest-environment jsdom
// Панель «Тайминг»: сводка темпа отбойки (мс/м) после расчёта — медиана,
// доля вне коридора, устойчивый разброс и легенда зон.
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
    render(<TimingPanel {...props} analysis={{ ...analysis, relief: { triangles: [], converging: [], stats: { triangles: 12, median_ms_m: 15.33, mean_ms_m: 15.4, min_ms_m: 14, max_ms_m: 17, cv: 0.55, outside_share: 0.05, robust_spread: 0.0712, min_bound_ms_m: 3, max_bound_ms_m: null, fast_share: 0, slow_share: 0, converging_length_m: 0 } } }} />);
    expect(screen.getByText("Темп отбойки, мс/м (медиана)")).toBeInTheDocument();
    expect(screen.getByText("15,3")).toBeInTheDocument();
    const outside = screen.getByText("Вне коридора ±25 %");
    const robust = screen.getByText("Устойчивый разброс");
    // Главный показатель ровности — доля вне коридора, он идёт раньше разброса.
    expect(outside.compareDocumentPosition(robust) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText("5 %")).toBeInTheDocument();
    expect(screen.getByText("7 %")).toBeInTheDocument();
    // cv раздувают выбросы — в панели его нет.
    expect(screen.queryByText("55 %")).not.toBeInTheDocument();
    expect(screen.getByText("13,8–16,9")).toBeInTheDocument();
  });

  it("explains missing relief", () => {
    render(<TimingPanel {...props} analysis={{ ...analysis, relief: null }} />);
    expect(screen.getByText("Темп отбойки: треугольники не построены — мало скважин или они слишком далеко друг от друга")).toBeInTheDocument();
  });

  it("says all holes fire together instead of the legend when every triangle is zero", () => {
    render(<TimingPanel {...props} analysis={{ ...analysis, relief: { triangles: [], converging: [], stats: { triangles: 4, median_ms_m: 0, mean_ms_m: 0, min_ms_m: 0, max_ms_m: 0, cv: null, outside_share: 0, robust_spread: null, min_bound_ms_m: 3, max_bound_ms_m: null, fast_share: 0, slow_share: 0, converging_length_m: 0 } } }} />);
    expect(screen.getByText("Все скважины срабатывают одновременно — темп 0 мс/м")).toBeInTheDocument();
    expect(screen.queryByText(/^до /)).not.toBeInTheDocument();
    expect(screen.queryByText(/^больше /)).not.toBeInTheDocument();
  });

  it("says most of the area fires together when median is zero but some triangles are not", () => {
    render(<TimingPanel {...props} analysis={{ ...analysis, relief: { triangles: [], converging: [], stats: { triangles: 6, median_ms_m: 0, mean_ms_m: 4, min_ms_m: 0, max_ms_m: 12, cv: 1.4, outside_share: 0.4, robust_spread: null, min_bound_ms_m: 3, max_bound_ms_m: null, fast_share: 0, slow_share: 0, converging_length_m: 0 } } }} />);
    expect(screen.getByText("Темп отбойки, мс/м (медиана)")).toBeInTheDocument();
    expect(screen.getByText("40 %")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("Больше половины площади срабатывает одновременно — темп 0 мс/м")).toBeInTheDocument();
    expect(screen.queryByText(/Все скважины срабатывают одновременно/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^до /)).not.toBeInTheDocument();
    expect(screen.queryByText(/^больше /)).not.toBeInTheDocument();
  });

  it("shows fast share and converging fronts, no upper bound row", () => {
    const stats = { triangles: 12, median_ms_m: 15, mean_ms_m: 15, min_ms_m: 2, max_ms_m: 17, cv: 0.2, outside_share: 0.05, robust_spread: 0.07, min_bound_ms_m: 3, max_bound_ms_m: null, fast_share: 0.12, slow_share: 0, converging_length_m: 7.5 };
    render(<TimingPanel {...props} analysis={{ ...analysis, relief: { triangles: [], converging: [], stats } }} />);
    expect(screen.getByText("Быстрее 3 мс/м")).toBeInTheDocument();
    expect(screen.getByText("12 %")).toBeInTheDocument();
    expect(screen.getByText("Стыки фронтов")).toBeInTheDocument();
    expect(screen.getByText("7,5")).toBeInTheDocument();
    expect(screen.queryByText(/Медленнее/)).not.toBeInTheDocument();
    const order = ["Быстрее 3 мс/м", "Стыки фронтов", "Вне коридора ±25 %", "Устойчивый разброс"].map((t) => screen.getByText(t));
    for (let i = 0; i < order.length - 1; i++) {
      expect(order[i].compareDocumentPosition(order[i + 1]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  it("shows upper bound row and «нет» for zero converging length", () => {
    const stats = { triangles: 12, median_ms_m: 15, mean_ms_m: 15, min_ms_m: 2, max_ms_m: 17, cv: 0.2, outside_share: 0.05, robust_spread: 0.07, min_bound_ms_m: 3, max_bound_ms_m: 12, fast_share: 0, slow_share: 0.3, converging_length_m: 0 };
    render(<TimingPanel {...props} analysis={{ ...analysis, relief: { triangles: [], converging: [], stats } }} />);
    expect(screen.getByText("Медленнее 12 мс/м")).toBeInTheDocument();
    expect(screen.getByText("30 %")).toBeInTheDocument();
    expect(screen.getByText("нет")).toBeInTheDocument();
  });
});
