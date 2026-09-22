import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./endpoints";
import { KUZRAM_DEFAULTS } from "../pages/calc/kuzram/kuzramSettings";
import type { Explosive, Rock } from "../types";

const ROCK = { name: "Гранит", density_t_m3: 2.65, ucs_mpa: 150, fissuring_ff: 2 } as Rock;
const EXPLOSIVE = { key: "Э-100", name: "ЭВЕРСИН Э-100", density_t_m3: 1.12, power_mj_kg: 2.99 } as Explosive;
const SHEET = { rock: ROCK, explosive: EXPLOSIVE, lumpSize: 400, benchHeight: 10, overdrill: 1, oversizeCoeff: 1.05, spacing: 1.25 };
const TARGET = {
  lump_size_mm: 400,
  hole_diameter_mm: 0,
  overdrill_m: 1,
  hole_oversize_coeff: 1.05,
  spacing_coeff_m: 1.25,
  bench_height_m: 10,
};

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation(async () => new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function lastRequest(): { path: string; body: Record<string, unknown> } {
  const [path, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
  return { path, body: JSON.parse(String(init.body)) };
}

describe("api: подбор q и подбор C(A)", () => {
  it("optimize передаёт настройки модели; без них ключа kuzram нет", async () => {
    await api.optimize({ ...SHEET, threshold: 5, crownDiametersMm: [152], kuzram: KUZRAM_DEFAULTS });
    expect(lastRequest()).toEqual({
      path: "/api/v1/blast/optimize",
      body: {
        rock: ROCK,
        explosive: { name: "ЭВЕРСИН Э-100", density_t_m3: 1.12, power_mj_kg: 2.99 },
        target: TARGET,
        crown_diameters_mm: [152],
        max_oversize_threshold_pct: 5,
        kuzram: KUZRAM_DEFAULTS,
      },
    });
    await api.optimize({ ...SHEET, threshold: 5, crownDiametersMm: [152] });
    expect(lastRequest().body).not.toHaveProperty("kuzram");
  });

  it("calibrateKuzram шлёт породу, ВВ, уступ, настройки и факты", async () => {
    const facts = [{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 }];
    await api.calibrateKuzram({ ...SHEET, kuzram: KUZRAM_DEFAULTS, facts });
    expect(lastRequest()).toEqual({
      path: "/api/v1/blast/kuzram/calibrate",
      body: {
        rock: ROCK,
        explosive: { name: "ЭВЕРСИН Э-100", density_t_m3: 1.12, power_mj_kg: 2.99 },
        target: TARGET,
        kuzram: KUZRAM_DEFAULTS,
        facts,
      },
    });
  });
});
