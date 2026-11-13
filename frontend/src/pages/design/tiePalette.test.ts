import { describe, expect, it } from "vitest";
import { emptyNetwork, type TieCatalog } from "../../types/design";
import { defaultActiveStep, defaultDownhole, nearestNominal, OFF_NOMINAL_COLOR, STEP_COLORS, stepColor, systemCatalog } from "./tiePalette";

const CATALOG: TieCatalog = {
  systems: {
    nonel: { surface_ms: [17, 25, 42, 67, 109], downhole_ms: [450, 500, 550], downhole_default_ms: 500, custom_surface: false },
    detcord: { surface_ms: [10, 20, 25, 35, 42], downhole_ms: [], downhole_default_ms: 0, custom_surface: false },
    electronic: { surface_ms: [17, 25, 42, 67, 109], downhole_ms: [], downhole_default_ms: 0, custom_surface: true },
  },
  detcord_velocity_m_s: 7000,
};

describe("палитра ступеней", () => {
  it("цвет — по номиналу системы, не номинал — серый", () => {
    expect(stepColor(17, CATALOG.systems.nonel.surface_ms)).toBe(STEP_COLORS[0]);
    expect(stepColor(42, CATALOG.systems.nonel.surface_ms)).toBe(STEP_COLORS[2]);
    expect(stepColor(42, CATALOG.systems.detcord.surface_ms)).toBe(STEP_COLORS[4]);
    expect(stepColor(30, CATALOG.systems.nonel.surface_ms)).toBe(OFF_NOMINAL_COLOR);
  });

  it("активная ступень при открытии — trunk_ms сети, иначе 25 мс", () => {
    expect(defaultActiveStep(emptyNetwork())).toBe(25);
    expect(defaultActiveStep({ ...emptyNetwork(), timing_params: { trunk_ms: 42 } })).toBe(42);
    expect(defaultActiveStep({ ...emptyNetwork(), timing_params: { trunk_ms: "x" } })).toBe(25);
  });

  it("замедление в скважине — из сети, иначе умолчание системы", () => {
    expect(defaultDownhole(emptyNetwork(), CATALOG.systems.nonel)).toBe(500);
    expect(defaultDownhole({ ...emptyNetwork(), timing_params: { downhole_delay_ms: 700 } }, CATALOG.systems.nonel)).toBe(700);
    expect(defaultDownhole(emptyNetwork(), CATALOG.systems.detcord)).toBe(0);
  });

  it("ближайший номинал: при равенстве — меньший", () => {
    expect(nearestNominal(30, [25, 35])).toBe(25);
    expect(nearestNominal(41, [17, 25, 42])).toBe(42);
  });

  it("каталог системы; нет каталога — null", () => {
    expect(systemCatalog(CATALOG, "detcord")?.surface_ms[0]).toBe(10);
    expect(systemCatalog(null, "nonel")).toBeNull();
  });
});
