import { describe, expect, it } from "vitest";
import { chartGeometry, labelLevels, shareView } from "./payrollModel";
import { economicsFixture, payrollFixture } from "./testFixtures";

const SIZE = { width: 400, height: 200, padding: 20 };

describe("economicsFixture", () => {
  it("по умолчанию без блока payroll", () => {
    expect(economicsFixture().payroll).toBeNull();
    expect(economicsFixture({ payroll: payrollFixture() }).payroll?.main_position_code).toBe("DRILLER");
  });
});

describe("shareView", () => {
  it("на потолке выше порога — warn", () => {
    const margin = payrollFixture().margin;
    margin.ceiling!.crew_share = 1.043;
    const view = shareView(margin);
    expect(view.value).toBe("104,3 %");
    expect(view.label).toBe("на потолке");
    expect(view.tone).toBe("warn");
  });

  it("ниже порога — ok", () => {
    const margin = payrollFixture().margin;
    margin.ceiling!.crew_share = 0.25;
    expect(shareView(margin)).toMatchObject({ value: "25 %", tone: "ok" });
  });

  it.each(["NOT_CHECKED", "NO_MARGIN", "NOT_APPLICABLE"] as const)("статус %s — пояснение без NaN", (status) => {
    const margin = { ...payrollFixture().margin, status, plan: null, ceiling: null };
    const view = shareView(margin);
    expect(view.tone).toBe("muted");
    expect(view.value).not.toMatch(/NaN/);
    expect(view.label).not.toMatch(/NaN/);
    expect(view.value.length).toBeGreaterThan(5);
  });

  it("ступени: берёт плановый темп", () => {
    const margin = payrollFixture({ scale: "STEP" }).margin;
    expect(margin.ceiling).toBeNull();
    expect(shareView(margin)).toEqual({ label: "при плановом темпе", value: "42 %", tone: "warn" });
  });

  it("порог выше 100 % не режет значение", () => {
    const margin = payrollFixture().margin;
    margin.threshold = 10;
    margin.ceiling!.crew_share = 9.5;
    expect(shareView(margin)).toMatchObject({ value: "950 %", tone: "ok" });
  });
});

describe("chartGeometry", () => {
  const inside = (x: number, y: number) =>
    x >= SIZE.padding && x <= SIZE.width - SIZE.padding && y >= SIZE.padding && y <= SIZE.height - SIZE.padding;

  it("узлы нормы и потолка внутри области", () => {
    const payroll = payrollFixture();
    const geometry = chartGeometry(payroll.series, payroll.scale!, payroll.pace.m_plan, SIZE)!;
    expect(geometry.ratePath.startsWith("M")).toBe(true);
    expect(geometry.perShiftPath.startsWith("M")).toBe(true);
    for (const marker of [geometry.markers.norm!, geometry.markers.ceiling!, geometry.markers.pace]) {
      expect(inside(marker.x, marker.y)).toBe(true);
    }
    expect(geometry.markers.norm!.x).toBeLessThan(geometry.markers.ceiling!.x);
  });

  it("темп выше потолка расширяет ось", () => {
    const payroll = payrollFixture();
    const geometry = chartGeometry(payroll.series, payroll.scale!, 236, SIZE)!;
    expect(inside(geometry.markers.pace.x, geometry.markers.pace.y)).toBe(true);
    expect(geometry.markers.pace.x).toBeGreaterThan(geometry.markers.ceiling!.x);
    const last = geometry.xAxis[geometry.xAxis.length - 1];
    expect(last.value).toBeGreaterThanOrEqual(236);
  });

  it("ступени: маркеров нормы и потолка нет, темп есть", () => {
    const payroll = payrollFixture({ scale: "STEP" });
    const geometry = chartGeometry(payroll.series, payroll.scale!, payroll.pace.m_plan, SIZE)!;
    expect(geometry.markers.norm).toBeNull();
    expect(geometry.markers.ceiling).toBeNull();
    expect(inside(geometry.markers.pace.x, geometry.markers.pace.y)).toBe(true);
  });

  it("пустой или короткий ряд — null", () => {
    const payroll = payrollFixture();
    expect(chartGeometry([], payroll.scale!, 120, SIZE)).toBeNull();
    expect(chartGeometry(payroll.series.slice(0, 1), payroll.scale!, 120, SIZE)).toBeNull();
  });

  it("x растёт вдоль отсортированного ряда, оси внутри области", () => {
    const payroll = payrollFixture();
    const geometry = chartGeometry([...payroll.series].reverse(), payroll.scale!, 120, SIZE)!;
    const xs = [...geometry.ratePath.matchAll(/[ML]\s*(-?[\d.]+)[ ,]/g)].map((m) => Number(m[1]));
    expect(xs.length).toBe(payroll.series.length);
    expect([...xs].sort((a, b) => a - b)).toEqual(xs);
    for (const tick of [...geometry.xAxis, ...geometry.yAxis]) expect(tick.label).toBeTruthy();
  });
});

describe("chartGeometry: нулевые ряды", () => {
  it("все значения нулевые — оси [0, 1], без NaN", () => {
    const series = [
      { pace: 0, rate: 0, per_shift: 0 },
      { pace: 0, rate: 0, per_shift: 0 },
    ];
    const scale = { scale_type: "STEP", gamma: null, norm_per_shift: null, rate_norm: null, ceiling_per_shift: null, rate_ceiling: null };
    const geometry = chartGeometry(series, scale, 0, SIZE)!;
    expect(geometry.xAxis.map((t) => t.value)).toEqual([0, 1]);
    expect(geometry.yAxis.map((t) => t.value)).toEqual([0, 1]);
    expect(geometry.ratePath).not.toContain("NaN");
  });
});

describe("labelLevels", () => {
  it("далёкие отметки на одном ярусе, близкие — выше", () => {
    expect(labelLevels([10, 300, 600], 100)).toEqual([0, 0, 0]);
    expect(labelLevels([100, 120, 130], 100)).toEqual([0, 1, 2]);
    expect(labelLevels([300, 100, 320], 100)).toEqual([0, 0, 1]);
  });
});
