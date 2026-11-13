// Клиентские времена срабатывания (TASK-017, PR 4) совпадают с серверными
// `design/timing.py::resolve_network` на общей фикстуре
// (`tests/test_network_times_fixture.py` её пишет и сверяет с сервером).
import { describe, expect, it } from "vitest";
import { emptyNetwork, normalizeNetwork, type Hole, type InitiationNetwork } from "../../types/design";
import { resolveNetworkTimes } from "./networkTimes";
import fixture from "./testing/networkTimesFixture.json";

type Case = {
  name: string;
  holes: { id: string; collar: { x: number; y: number; z: number }; enabled: boolean }[];
  network: Partial<InitiationNetwork>;
  times: Record<string, number>;
  unsignaled: string[];
};

const cases = (fixture as unknown as { cases: Case[] }).cases;

function hole(id: string, x: number, y: number, enabled = true): Hole {
  return { id, collar: { x, y, z: 0 }, enabled } as unknown as Hole;
}

describe("клиентские времена = resolve_network", () => {
  it.each(cases.map((item) => [item.name, item] as const))("%s", (_name, item) => {
    const holes = item.holes as unknown as Hole[];
    const result = resolveNetworkTimes(normalizeNetwork(item.network), holes, 7000);
    expect(Object.keys(result.times).sort()).toEqual(Object.keys(item.times).sort());
    for (const [id, value] of Object.entries(item.times)) expect(result.times[id]).toBeCloseTo(value, 6);
    expect(result.unsignaled).toEqual(item.unsignaled);
  });

  it("пустая сеть — все включённые без сигнала, исключённые — нет", () => {
    const result = resolveNetworkTimes(emptyNetwork(), [hole("a", 0, 0), hole("b", 5, 0, false)]);
    expect(result.times).toEqual({});
    expect(result.unsignaled).toEqual(["a"]);
  });

  it("сигнал идёт через исключённую скважину, как на сервере", () => {
    const network = normalizeNetwork({
      starters: ["a"],
      connectors: [
        { from_hole: "a", to_hole: "b", delay_ms: 17, kind: "surface_nsi" },
        { from_hole: "b", to_hole: "c", delay_ms: 25, kind: "surface_nsi" },
      ],
    });
    const result = resolveNetworkTimes(network, [hole("a", 0, 0), hole("b", 5, 0, false), hole("c", 10, 0)]);
    expect(result.times).toEqual({ a: 0, c: 42 });
    expect(result.unsignaled).toEqual([]);
  });
});
